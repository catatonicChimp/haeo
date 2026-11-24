"""Offline appliance solves using real HAEO electrical connections."""

import numpy as np
import pytest

from custom_components.haeo.core.model import Network
from custom_components.haeo.core.model.elements.appliance import Appliance
from custom_components.haeo.core.model.solver import Solver


def make_appliance(
    *,
    periods: tuple[float, ...] = (1.0, 1.0),
    prices: tuple[float, ...] = (0.3, 0.1),
    in_window: tuple[float, ...] = (1.0, 1.0),
    energy: float = 2.0,
    duration: float = 1.0,
    armed: bool = True,
) -> tuple[Network, Appliance]:
    """Create an appliance supplied through a priced connection from a grid node."""
    network = Network(name="appliance_research", periods=np.array(periods))
    network.add({"element_type": "node", "name": "grid", "is_source": True, "is_sink": False})
    appliance = network.add(
        {
            "element_type": "appliance",
            "name": "dishwasher",
            "in_window": np.asarray(in_window, dtype=np.float64),
            "energy": energy,
            "duration": duration,
            "armed": armed,
            "is_source": False,
            "is_sink": True,
        }
    )
    network.add(
        {
            "element_type": "connection",
            "name": "import",
            "source": "grid",
            "target": "dishwasher",
            "tags": {0},
            "segments": {"price": {"segment_type": "pricing", "price": np.asarray(prices)}},
        }
    )
    return network, appliance


def test_run_takes_the_cheapest_period() -> None:
    """The one-hour run draws its energy where the connection price is lowest."""
    network, appliance = make_appliance()
    assert network.optimize() == pytest.approx(0.2)
    assert appliance.outputs()["appliance_power"].values == pytest.approx((0.0, 2.0))


def test_disarmed_appliance_draws_nothing() -> None:
    """A disarmed appliance has no required run and consumes nothing."""
    network, appliance = make_appliance(armed=False)
    assert network.optimize() == pytest.approx(0.0)
    assert appliance.outputs()["appliance_power"].values == pytest.approx((0.0, 0.0))


def test_window_shorter_than_run_stays_feasible() -> None:
    """A run that does not fit the window reports power up to the window and costs its shortfall."""
    network, appliance = make_appliance(in_window=(1.0, 0.0), energy=4.0, duration=2.0, prices=(0.1, 0.1))
    assert network.optimize() == pytest.approx(200.2)
    assert appliance.outputs()["appliance_power"].values == pytest.approx((2.0, 0.0))


def test_reactive_energy_update() -> None:
    """Changing the run's energy updates the plan without rebuilding the network."""
    network, appliance = make_appliance()
    network.optimize()
    appliance.energy = 1.0
    assert network.optimize() == pytest.approx(0.1)
    assert appliance.outputs()["appliance_power"].values == pytest.approx((0.0, 1.0))


def test_appliance_only_consumes() -> None:
    """An appliance is a sink and never a source, so policies can deliver to it."""
    _, appliance = make_appliance()
    assert isinstance(appliance, Appliance)
    assert appliance.is_sink
    assert not appliance.is_source


def test_run_spreads_over_cheapest_periods_when_power_is_capped() -> None:
    """With a run longer than one period, the relaxation may split it across the cheapest periods."""
    network, appliance = make_appliance(
        periods=(1.0, 1.0, 1.0), prices=(0.1, 0.2, 0.05), in_window=(1.0, 1.0, 1.0), energy=2.0, duration=2.0
    )
    assert network.optimize() == pytest.approx(0.15)
    assert appliance.outputs()["appliance_power"].values == pytest.approx((1.0, 0.0, 1.0))


def test_rejects_a_nonpositive_duration(solver: Solver) -> None:
    """A run needs a positive duration to define its power."""
    with pytest.raises(ValueError, match="positive run duration"):
        Appliance(
            name="dishwasher",
            periods=np.ones(2),
            solver=solver,
            in_window=np.ones(2),
            energy=1.0,
            duration=0.0,
            armed=True,
        )
