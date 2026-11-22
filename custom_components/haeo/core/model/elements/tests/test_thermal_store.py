"""Offline thermal-store solves using real HAEO electrical connections."""

import numpy as np
import pytest

from custom_components.haeo.core.model import Network
from custom_components.haeo.core.model.elements.thermal_store import ThermalStore
from custom_components.haeo.core.model.infeasibility import InfeasibleError
from custom_components.haeo.core.model.solver import Solver


def make_store(
    *,
    periods: tuple[float, ...] = (1.0, 1.0),
    prices: tuple[float, ...] = (0.1, 0.3),
    initial: float = 50.0,
    target: float = 60.0,
    maximum: float = 75.0,
    max_power: float = 1.0,
    draw: float = 0.0,
    loss: float = 0.0,
) -> tuple[Network, ThermalStore]:
    """Create a 0.1 kWh/K thermal store supplied through a priced connection."""
    network = Network(name="thermal_research", periods=np.array(periods))
    network.add({"element_type": "node", "name": "grid", "is_source": True, "is_sink": False})
    network.add({"element_type": "node", "name": "bus", "is_source": False, "is_sink": False})
    network.add(
        {
            "element_type": "connection",
            "name": "import",
            "source": "grid",
            "target": "bus",
            "tags": {1},
            "segments": {"price": {"segment_type": "pricing", "price": np.array(prices)}},
        }
    )
    network.add({"element_type": "node", "name": "tank_load", "is_source": False, "is_sink": True})
    network.add(
        {
            "element_type": "connection",
            "name": "heater",
            "source": "bus",
            "target": "tank_load",
            "tags": {1},
            "segments": {
                "limit": {"segment_type": "power_limit", "max_power": max_power},
            },
        }
    )
    n = len(periods)
    store = network.add(
        {
            "element_type": "thermal_store",
            "name": "tank",
            "connection": "heater",
            "capacity_per_degree": 0.1,
            "initial_temperature": initial,
            "reference_temperature": 10.0,
            "maximum_temperature": maximum,
            "cop": np.full(n, 2.0),
            "loss_power": np.full(n, loss),
            "draw_energy": np.full(n, draw),
            "target_temperature": np.array([initial] * n + [target]),
            "shortfall_price": np.full(n + 1, 10.0),
        }
    )
    return network, store


def test_cheapest_heating_and_terminal_readiness() -> None:
    """One thermal kWh requires 0.5 electrical kWh at COP 2, bought cheaply."""
    network, store = make_store()
    assert network.optimize() == pytest.approx(0.05)
    assert store.temperatures() == pytest.approx((50.0, 60.0, 60.0))


def test_above_comfort_target_does_not_require_cooling() -> None:
    """An already-hot heating-only store remains feasible and consumes nothing."""
    network, store = make_store(initial=65.0)
    assert network.optimize() == pytest.approx(0.0)
    assert store.temperatures() == pytest.approx((65.0, 65.0, 65.0))


def test_unreachable_target_exposes_shortfall() -> None:
    """Power capacity stays hard while readiness can be missed."""
    network, store = make_store(max_power=0.1)
    network.optimize()
    assert store.temperatures()[-1] == pytest.approx(54.0)
    assert store.outputs()["thermal_store_shortfall"].values[-1] == pytest.approx(0.6)


def test_variable_period_loss_and_draw_units() -> None:
    """Loss scales with hours; draw is already energy per interval."""
    network, store = make_store(periods=(0.25, 0.75), initial=60.0, target=10.0, max_power=0.0, draw=0.1, loss=0.2)
    network.optimize()
    assert store.temperatures() == pytest.approx((60.0, 58.5, 56.0))


def test_reactive_initial_temperature_update() -> None:
    """Changing measured state updates the same network without stale constraints."""
    network, store = make_store()
    network.optimize()
    store.initial_temperature = 55.0
    assert network.optimize() == pytest.approx(0.025)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_reactive_cop_update() -> None:
    """A changed efficiency forecast updates heat balance without rebuilding."""
    network, store = make_store()
    network.optimize()
    store.cop = np.ones(2)
    assert network.optimize() == pytest.approx(0.1)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_period_duration_update() -> None:
    """Changing interval widths updates both electrical and thermal balance."""
    network, store = make_store()
    network.optimize()
    network.update_periods(np.array([0.25, 0.75]))
    assert network.optimize() == pytest.approx(0.1)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_physical_maximum_is_not_relaxed() -> None:
    """An inconsistent measured state fails rather than hiding a physical conflict."""
    network, _ = make_store(initial=80.0)
    with pytest.raises(InfeasibleError):
        network.optimize()


def test_battery_and_tank_share_the_same_solve() -> None:
    """Stored electrical energy can meet the tank target without importing."""
    network, store = make_store()
    network.add({"element_type": "battery", "name": "battery", "capacity": 1.0, "initial_charge": 0.5})
    network.add(
        {
            "element_type": "connection",
            "name": "battery_to_tank",
            "source": "battery",
            "target": "bus",
            "tags": {1},
        }
    )
    assert network.optimize() == pytest.approx(0.0)
    assert store.temperatures()[-1] == pytest.approx(60.0)


@pytest.mark.parametrize(("export_price", "expected_cost", "expected_midpoint"), [(0.05, 0.0, 60.0), (0.5, -0.1, 50.0)])
def test_solar_surplus_competes_with_export(
    export_price: float, expected_cost: float, expected_midpoint: float
) -> None:
    """Heat from surplus only when avoided imports exceed the forgone export value."""
    network, store = make_store(prices=(0.6, 0.3))
    network.add({"element_type": "node", "name": "pv", "is_source": True, "is_sink": False})
    network.add({"element_type": "node", "name": "house", "is_source": False, "is_sink": True})
    network.add({"element_type": "node", "name": "export_grid", "is_source": False, "is_sink": True})
    for name, source, target, profile in (
        ("solar", "pv", "bus", np.array([1.0, 0.0])),
        ("baseline", "bus", "house", np.array([0.5, 0.0])),
    ):
        network.add(
            {
                "element_type": "connection",
                "name": name,
                "source": source,
                "target": target,
                "tags": {1},
                "segments": {"limit": {"segment_type": "power_limit", "max_power": profile, "fixed": True}},
            }
        )
    network.add(
        {
            "element_type": "connection",
            "name": "export",
            "source": "bus",
            "target": "export_grid",
            "tags": {1},
            "segments": {
                "limit": {"segment_type": "power_limit", "max_power": np.array([1.0, 0.0])},
                "price": {"segment_type": "pricing", "price": -export_price},
            },
        }
    )
    assert network.optimize() == pytest.approx(expected_cost)
    assert store.temperatures()[1] == pytest.approx(expected_midpoint)
    assert store.temperatures()[-1] == pytest.approx(60.0)


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        ("cop", np.array([0.0, 2.0]), "cop"),
        ("cop", np.array([np.nan, 2.0]), "cop"),
        ("cop", np.ones(3), "cop"),
        ("loss_power", np.array([-0.1, 0.0]), "loss_power"),
        ("draw_energy", np.array([np.inf, 0.0]), "draw_energy"),
        ("shortfall_price", np.zeros(3), "shortfall_price"),
        ("target_temperature", np.ones(2), "Target temperatures"),
        ("initial_temperature", float("nan"), "Initial temperature"),
    ],
)
def test_invalid_reactive_inputs_fail_before_solving(field: str, values: object, message: str) -> None:
    """An updated forecast cannot bypass the thermal input contract."""
    network, store = make_store()
    network.optimize()
    store[field] = values
    with pytest.raises(ValueError, match="Failed to apply constraints") as error:
        network.optimize()
    assert message in str(error.value.__cause__)


def test_average_power_is_not_an_executable_on_off_command() -> None:
    """A feasible LP can need less run time than a compressor's minimum cycle."""
    network, store = make_store(periods=(0.5, 0.5), initial=59.0, max_power=0.8)
    network.optimize()
    thermal_gain = 0.1 * (store.temperatures()[-1] - 59.0)
    electrical_kwh = thermal_gain / 2.0
    required_on_minutes = electrical_kwh / 0.8 * 60.0
    assert required_on_minutes == pytest.approx(3.75)
    minimum_cycle_minutes = 10.0
    assert required_on_minutes < minimum_cycle_minutes


@pytest.mark.parametrize(("field", "value"), [("capacity_per_degree", 0.0), ("reference_temperature", float("nan"))])
def test_invalid_structural_inputs(field: str, value: float) -> None:
    """Reject invalid capacity and reference units before allocating states."""
    network, store = make_store()
    with pytest.raises(ValueError, match="Thermal capacity"):
        ThermalStore(
            "invalid",
            network.periods,
            solver=Solver(),
            connection=store.connection,
            capacity_per_degree=value if field == "capacity_per_degree" else 0.1,
            initial_temperature=50.0,
            reference_temperature=value if field == "reference_temperature" else 10.0,
            maximum_temperature=75.0,
            cop=np.full(2, 2.0),
            loss_power=np.zeros(2),
            draw_energy=np.zeros(2),
            target_temperature=np.full(3, 60.0),
            shortfall_price=np.full(3, 10.0),
        )
