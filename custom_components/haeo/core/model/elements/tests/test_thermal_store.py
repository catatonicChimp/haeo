"""Offline two-stage thermal-store solves using real HAEO electrical connections."""

import numpy as np
import pytest

from custom_components.haeo.core.model import Network
from custom_components.haeo.core.model.elements.connection import Connection
from custom_components.haeo.core.model.elements.thermal_store import ThermalStore
from custom_components.haeo.core.model.infeasibility import InfeasibleError
from custom_components.haeo.core.model.solver import Solver


def make_network(*, periods: tuple[float, ...] = (1.0, 1.0), prices: tuple[float, ...] = (0.1, 0.3)) -> Network:
    """Create a priced bus with two connections to a common tank sink node."""
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
    return network


def make_store(
    network: Network,
    *,
    name: str = "tank",
    initial: float = 50.0,
    target: float = 60.0,
    maximum: float = 75.0,
    hp_ceiling: float = 65.0,
    hp_max_power: float = 0.8,
    element_max_power: float = 0.8,
    hp_cop: float = 3.0,
    element_cop: float = 1.0,
    draw: float = 0.0,
    loss: float = 0.0,
) -> ThermalStore:
    """Add a two-stage thermal store to a network created by make_network."""
    n = network.n_periods
    network.add(
        {
            "element_type": "connection",
            "name": f"{name}:heat_pump",
            "source": "bus",
            "target": "tank_load",
            "tags": {1},
            "segments": {"limit": {"segment_type": "power_limit", "max_power": hp_max_power}},
        }
    )
    network.add(
        {
            "element_type": "connection",
            "name": f"{name}:element",
            "source": "bus",
            "target": "tank_load",
            "tags": {1},
            "segments": {"limit": {"segment_type": "power_limit", "max_power": element_max_power}},
        }
    )
    return network.add(
        {
            "element_type": "thermal_store",
            "name": name,
            "heat_pump_connection": f"{name}:heat_pump",
            "element_connection": f"{name}:element",
            "capacity_per_degree": 0.1,
            "initial_temperature": initial,
            "reference_temperature": 0.0,
            "maximum_temperature": maximum,
            "hp_ceiling_temperature": hp_ceiling,
            "loss_power": np.full(n, loss),
            "draw_energy": np.full(n, draw),
            "target_temperature": np.array([initial] * n + [target]),
            "shortfall_price": np.full(n + 1, 10.0),
            "hp_cop": np.full(n, hp_cop),
            "hp_max_power": np.full(n, hp_max_power),
            "element_cop": np.full(n, element_cop),
            "element_max_power": np.full(n, element_max_power),
        }
    )


def test_cheapest_heating_and_terminal_readiness() -> None:
    """One thermal kWh requires 1/3 electrical kWh via HP; bought cheaply."""
    network = make_network()
    store = make_store(network)
    assert network.optimize() == pytest.approx(0.033333, abs=1e-6)
    assert store.temperatures() == pytest.approx((50.0, 60.0, 60.0))


def test_simultaneous_stages_below_ceiling_use_both_maxima() -> None:
    """Below the ceiling the heat pump is capped by the ceiling lift; the element fills the rest."""
    network = make_network(periods=(1.0,), prices=(0.1,))
    store = make_store(network, initial=50.0, target=75.0, hp_max_power=0.8, element_max_power=0.8)
    network.optimize()
    hp = store.outputs()["thermal_store_power_hp"].values[0]
    element = store.outputs()["thermal_store_power_element"].values[0]
    # COP3 HP can lift at most from 50 C to the 65 C ceiling in one hour
    assert hp == pytest.approx(0.5)
    assert element == pytest.approx(0.8)
    assert hp + element == pytest.approx(1.3)


def test_hp_cannot_lift_above_ceiling_when_element_disabled() -> None:
    """The heat pump is capped so a single interval cannot push energy past the ceiling."""
    network = make_network(periods=(1.0,), prices=(0.1,))
    store = make_store(
        network, initial=50.0, target=75.0, hp_ceiling=65.0, element_max_power=0.0, hp_max_power=10.0, hp_cop=3.0
    )
    network.optimize()
    # HP can only lift to the ceiling; the unreachable target becomes shortfall
    assert store.temperatures()[1] <= 65.0 + 1e-9
    assert store.outputs()["thermal_store_power_hp"].values[0] == pytest.approx(0.5)


def test_element_only_for_period_starting_above_ceiling() -> None:
    """A period whose starting energy is above the heat-pump ceiling has HP disabled."""
    network = make_network(periods=(1.0, 1.0), prices=(0.1, 0.1))
    store = make_store(network, initial=66.0, target=75.0, maximum=75.0, hp_ceiling=65.0)
    network.optimize()
    hp_values = store.outputs()["thermal_store_power_hp"].values
    assert hp_values[0] == pytest.approx(0.0)
    assert hp_values[1] == pytest.approx(0.0)
    assert store.temperatures()[-1] == pytest.approx(75.0)


def test_free_pre_charge_to_maximum_uses_upper_band_at_element_cop() -> None:
    """When the first period is free the store pre-heats to the physical maximum."""
    network = make_network(periods=(1.0, 1.0), prices=(0.0, 1.0))
    store = make_store(network, initial=50.0, target=75.0, maximum=75.0, hp_ceiling=65.0)
    network.optimize()
    assert store.temperatures()[-1] == pytest.approx(75.0)
    # In the free interval both stages run to reach the target, with the upper band
    # lifted by the element (COP 1) rather than the heat pump.
    hp0 = store.outputs()["thermal_store_power_hp"].values[0]
    element0 = store.outputs()["thermal_store_power_element"].values[0]
    assert hp0 > 0
    assert element0 > 0


def test_import_power_equals_sum_of_stage_powers() -> None:
    """The grid import that feeds the tank equals the two stage powers."""
    network = make_network()
    store = make_store(network, initial=50.0, target=75.0)
    network.optimize()
    hp = store.outputs()["thermal_store_power_hp"].values
    element = store.outputs()["thermal_store_power_element"].values
    total = tuple(h + e for h, e in zip(hp, element, strict=True))
    import_power = network.elements["import"].outputs()["connection_power"].values
    assert import_power == pytest.approx(total)


def test_crossing_intervals_switch_hp_off_above_ceiling() -> None:
    """The first interval may use both stages; the second, starting above the ceiling, uses only element."""
    network = make_network(periods=(1.0, 1.0), prices=(0.1, 0.1))
    store = make_store(network, initial=50.0, target=75.0, maximum=75.0, hp_ceiling=65.0)
    network.optimize()
    hp = store.outputs()["thermal_store_power_hp"].values
    element = store.outputs()["thermal_store_power_element"].values
    assert hp[0] > 0
    assert hp[1] == pytest.approx(0.0)
    assert element[1] > 0


def test_variable_period_loss_and_draw_units() -> None:
    """Loss scales with hours; draw is already energy per interval."""
    network = make_network(periods=(0.25, 0.75))
    store = make_store(network, initial=60.0, target=10.0, hp_max_power=0.0, element_max_power=0.0, draw=0.1, loss=0.2)
    network.optimize()
    assert store.temperatures() == pytest.approx((60.0, 58.5, 56.0))


def test_reactive_initial_temperature_update() -> None:
    """Changing measured state updates the same network without rebuilding."""
    network = make_network()
    store = make_store(network)
    network.optimize()
    store.initial_temperature = 55.0
    assert network.optimize() == pytest.approx(0.016667, abs=1e-6)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_reactive_hp_cop_update() -> None:
    """A changed heat-pump efficiency forecast updates heat balance without rebuilding."""
    network = make_network()
    store = make_store(network)
    network.optimize()
    store.hp_cop = np.ones(2)
    assert network.optimize() == pytest.approx(0.1, abs=1e-6)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_period_duration_update() -> None:
    """Changing interval widths updates both electrical and thermal balance."""
    network = make_network()
    store = make_store(network)
    network.optimize()
    network.update_periods(np.array([0.25, 0.75]))
    assert network.optimize() == pytest.approx(0.06, abs=1e-6)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_physical_maximum_is_not_relaxed() -> None:
    """An inconsistent measured state fails rather than hiding a physical conflict."""
    network = make_network()
    make_store(network, initial=80.0)
    with pytest.raises(InfeasibleError):
        network.optimize()


def test_battery_and_tank_share_the_same_solve() -> None:
    """Stored electrical energy can meet the tank target without importing."""
    network = make_network()
    store = make_store(network)
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
    assert network.optimize() == pytest.approx(0.0, abs=1e-6)
    assert store.temperatures()[-1] == pytest.approx(60.0)


def test_zero_upper_band_is_pure_lp_and_allows_hp_everywhere() -> None:
    """When the ceiling equals the physical maximum there are no binaries and the heat pump is unrestricted."""
    network = make_network(periods=(1.0,), prices=(0.1,))
    store = make_store(network, initial=70.0, target=75.0, maximum=75.0, hp_ceiling=75.0)
    cost = network.optimize()
    assert cost > 0
    # Solver never allocated binary variables
    assert network._solver.has_integer_columns is False
    # The heat pump still heats even though the period starts near the top
    assert store.outputs()["thermal_store_power_hp"].values[0] > 0


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        ("hp_cop", np.array([0.0, 3.0]), "hp_cop"),
        ("hp_cop", np.array([np.nan, 3.0]), "hp_cop"),
        ("hp_cop", np.ones(3), "hp_cop"),
        ("element_cop", np.array([0.0, 1.0]), "element_cop"),
        ("loss_power", np.array([-0.1, 0.0]), "loss_power"),
        ("draw_energy", np.array([np.inf, 0.0]), "draw_energy"),
        ("shortfall_price", np.zeros(3), "shortfall_price"),
        ("target_temperature", np.ones(2), "Target temperatures"),
        ("initial_temperature", float("nan"), "Initial temperature"),
    ],
)
def test_invalid_reactive_inputs_fail_before_solving(field: str, values: object, message: str) -> None:
    """An updated forecast cannot bypass the thermal input contract."""
    network = make_network()
    store = make_store(network)
    network.optimize()
    store[field] = values
    with pytest.raises(ValueError, match="Failed to apply constraints") as error:
        network.optimize()
    assert message in str(error.value.__cause__)


def test_average_power_is_not_an_executable_on_off_command() -> None:
    """A feasible LP can need less run time than a compressor's minimum cycle."""
    network = make_network(periods=(0.5, 0.5))
    store = make_store(network, initial=59.0, hp_max_power=0.8, element_max_power=0.0)
    network.optimize()
    thermal_gain = 0.1 * (store.temperatures()[-1] - 59.0)
    electrical_kwh = thermal_gain / 3.0
    required_on_minutes = electrical_kwh / 0.8 * 60.0
    assert required_on_minutes == pytest.approx(2.5)
    minimum_cycle_minutes = 10.0
    assert required_on_minutes < minimum_cycle_minutes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capacity_per_degree", 0.0),
        ("reference_temperature", float("nan")),
    ],
)
def test_invalid_structural_inputs(field: str, value: float) -> None:
    """Reject invalid capacity and reference units before allocating states."""
    network = make_network()
    make_store(network)
    hp_conn = network.elements["tank:heat_pump"]
    element_conn = network.elements["tank:element"]
    assert isinstance(hp_conn, Connection)
    assert isinstance(element_conn, Connection)
    with pytest.raises(ValueError, match="Thermal capacity"):
        ThermalStore(
            "invalid",
            network.periods,
            solver=Solver(),
            heat_pump_connection=hp_conn,
            element_connection=element_conn,
            capacity_per_degree=value if field == "capacity_per_degree" else 0.1,
            initial_temperature=50.0,
            reference_temperature=value if field == "reference_temperature" else 0.0,
            maximum_temperature=75.0,
            hp_ceiling_temperature=65.0,
            loss_power=np.zeros(2),
            draw_energy=np.zeros(2),
            target_temperature=np.full(3, 60.0),
            shortfall_price=np.full(3, 10.0),
            hp_cop=np.full(2, 3.0),
            hp_max_power=np.full(2, 0.8),
            element_cop=np.full(2, 1.0),
            element_max_power=np.full(2, 0.8),
        )


def test_invalid_ceiling_above_maximum_rejected() -> None:
    """A ceiling above the physical maximum is a structural error."""
    network = make_network(periods=(1.0,), prices=(0.1,))
    with pytest.raises(ValueError, match="ceiling"):
        make_store(network, maximum=75.0, hp_ceiling=80.0)


def test_malformed_arrays_rejected_before_solving() -> None:
    """Reactive updates with the wrong array shape fail before solving."""
    network = make_network()
    store = make_store(network)
    network.optimize()
    store.hp_max_power = np.array([0.8])
    with pytest.raises(ValueError, match="Failed to apply constraints") as error:
        network.optimize()
    assert "hp_max_power" in str(error.value.__cause__)
