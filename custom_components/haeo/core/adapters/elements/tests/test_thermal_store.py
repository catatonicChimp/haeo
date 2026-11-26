"""Exercise a configured thermal device through HAEO's normal build lifecycle."""

from collections.abc import Mapping
from copy import deepcopy

import numpy as np
from numpy.typing import NDArray
import pytest

from custom_components.haeo.core.adapters.elements.thermal_store import ThermalOutputName, adapter
from custom_components.haeo.core.adapters.network_builder import build_element_updaters, build_network
from custom_components.haeo.core.model import Network
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData


def test_configured_thermal_store_build_update_and_outputs() -> None:
    """Use compiled electrical tags and tracked inputs, not a private live network."""
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("bus"),
        thermal={
            "initial_temperature": 50.0,
            "target_temperature": np.array([50.0, 50.0, 60.0]),
            "maximum_temperature": 75.0,
            "capacity_per_degree": 0.1,
            "loss_power": np.zeros(2),
            "draw_power": np.zeros(2),
            "shortfall_price": np.array([10.0, 10.0, 10.0]),
        },
        heat_pump={
            "hp_ceiling_temperature": 75.0,
            "hp_max_power": np.ones(2),
            "hp_cop": np.full(2, 2.0),
        },
        element={
            "element_max_power": np.zeros(2),
            "element_cop": np.ones(2),
        },
    )
    participants: dict[str, ElementConfigData] = {
        "bus": {"element_type": ElementType.JUNCTION, "name": "bus"},
        "grid": {
            "element_type": ElementType.GRID,
            "name": "grid",
            "connection": as_connection_target("bus"),
            "pricing": {"price_source_target": np.array([0.1, 0.3]), "price_target_source": np.zeros(2)},
            "power_limits": {},
        },
        "tank": tank,
    }
    network = build_network("shadow", participants, [3600.0, 3600.0])
    assert network.optimize() == pytest.approx(0.05)
    outputs = {name: element.outputs() for name, element in network.elements.items()}
    result = adapter.outputs("tank", outputs, config=tank)
    assert result[ElementType.THERMAL_STORE]["thermal_store_temperature"].values[-1] == pytest.approx(60.0)
    assert result[ElementType.THERMAL_STORE]["thermal_store_power_element"].values == pytest.approx((0.0, 0.0))
    updater = build_element_updaters(network, participants)["tank"]
    tank["thermal"]["initial_temperature"] = 55.0
    updater(tank)
    assert network.optimize() == pytest.approx(0.025)


def _two_stage_participants(
    *,
    periods: int,
    prices: NDArray[np.float64],
    initial_temperature: float,
    target_temperature: float,
    hp_ceiling_temperature: float = 65.0,
    maximum_temperature: float = 75.0,
    capacity_per_degree: float = 0.314,
    loss_power: float = 0.05,
    draw_power: float = 0.02,
    hp_max_power: float = 0.8,
    hp_cop: float = 3.0,
    element_max_power: float = 0.7,
    element_cop: float = 1.0,
    base_load: float = 0.5,
) -> tuple[dict[str, ElementConfigData], ThermalStoreConfigData]:
    """Return a grid-fed switchboard with a base load and a two-stage tank."""
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("switchboard"),
        thermal={
            "initial_temperature": initial_temperature,
            "target_temperature": np.array([initial_temperature] * periods + [target_temperature]),
            "maximum_temperature": maximum_temperature,
            "capacity_per_degree": capacity_per_degree,
            "loss_power": np.full(periods, loss_power),
            "draw_power": np.full(periods, draw_power),
            "shortfall_price": np.full(periods + 1, 10.0),
        },
        heat_pump={
            "hp_ceiling_temperature": hp_ceiling_temperature,
            "hp_max_power": np.full(periods, hp_max_power),
            "hp_cop": np.full(periods, hp_cop),
        },
        element={
            "element_max_power": np.full(periods, element_max_power),
            "element_cop": np.full(periods, element_cop),
        },
    )
    participants: dict[str, ElementConfigData] = {
        "switchboard": {"name": "switchboard", "element_type": ElementType.JUNCTION},
        "grid": {
            "name": "grid",
            "element_type": ElementType.GRID,
            "connection": as_connection_target("switchboard"),
            "pricing": {"price_source_target": prices, "price_target_source": np.zeros(periods)},
            "power_limits": {},
        },
        "base": {
            "name": "base",
            "element_type": ElementType.LOAD,
            "connection": as_connection_target("switchboard"),
            "forecast": {"forecast": np.full(periods, base_load)},
            "curtailment": {},
        },
        "tank": tank,
    }
    return participants, tank


def _whole_network() -> tuple[Network, dict[str, ElementConfigData], ThermalStoreConfigData]:
    """Return a solved seven-hour network with a zero-price opening interval."""
    participants, tank = _two_stage_participants(
        periods=7,
        prices=np.array([0.0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
        initial_temperature=56.0,
        target_temperature=75.0,
    )
    network = build_network("shadow", participants, [3600.0] * 7)
    network.optimize()
    return network, participants, tank


def _tank_outputs(network: Network, tank: ThermalStoreConfigData) -> Mapping[ThermalOutputName, OutputData]:
    """Return the tank's adapter outputs from the network's current solution."""
    return adapter.outputs(
        "tank",
        {name: element.outputs() for name, element in network.elements.items()},
        config=tank,
    )[ElementType.THERMAL_STORE]


def _temperatures(outputs: Mapping[ThermalOutputName, OutputData]) -> NDArray[np.float64]:
    """Return the published boundary temperatures as an array."""
    return np.asarray(outputs["thermal_store_temperature"].values, dtype=np.float64)


def _stage_powers(outputs: Mapping[ThermalOutputName, OutputData]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the published heat-pump and element powers as arrays."""
    return (
        np.asarray(outputs["thermal_store_power_hp"].values, dtype=np.float64),
        np.asarray(outputs["thermal_store_power_element"].values, dtype=np.float64),
    )


def test_whole_network_precharges_to_maximum_within_limits() -> None:
    """The free opening interval fills the upper band, and readiness never exceeds the physical maximum."""
    network, _, tank = _whole_network()
    outputs = _tank_outputs(network, tank)
    temperatures = _temperatures(outputs)

    assert temperatures[-1] == pytest.approx(75.0)
    assert np.max(temperatures) <= 75.0 + 1e-9
    assert temperatures[1] > 65.0
    np.testing.assert_allclose(np.asarray(outputs["thermal_store_shortfall"].values, dtype=float), 0.0, atol=1e-9)


def test_whole_network_power_balances_sum_the_stages_and_base_load() -> None:
    """The published tank total is the sum of its stages, and grid import adds the base load."""
    network, _, tank = _whole_network()
    outputs = _tank_outputs(network, tank)
    hp, element = _stage_powers(outputs)
    total = np.asarray(outputs["thermal_store_power"].values, dtype=float)

    np.testing.assert_allclose(total, hp + element, atol=1e-12)

    base = np.asarray(network.elements["base:connection"].outputs()["connection_power"].values, dtype=float)
    imported = np.asarray(network.elements["grid:import"].outputs()["connection_power"].values, dtype=float)
    np.testing.assert_allclose(imported, base + total, atol=1e-12)


def test_whole_network_crossing_interval_runs_both_stages_and_later_periods_only_the_element() -> None:
    """Only a period that starts below the ceiling and ends above it can plan both stages at once."""
    network, _, tank = _whole_network()
    outputs = _tank_outputs(network, tank)
    temperatures = _temperatures(outputs)
    hp, element = _stage_powers(outputs)
    total = np.asarray(outputs["thermal_store_power"].values, dtype=float)

    # The opening interval crosses the heat-pump ceiling, so both stages are compatible
    assert temperatures[0] < 65.0
    assert temperatures[1] > 65.0
    assert hp[0] == pytest.approx(0.8)
    assert element[0] == pytest.approx(0.7)
    assert total[0] == pytest.approx(1.5)

    # Every later period starts above the ceiling: the heat pump is off and only the element heats
    for period in range(1, len(hp)):
        assert temperatures[period] > 65.0
        assert hp[period] == pytest.approx(0.0, abs=1e-9)
        assert element[period] <= 0.8 + 1e-9
    assert element[1] == pytest.approx(0.7)


def test_whole_network_boundaries_follow_stage_heat_and_losses() -> None:
    """Recomputing each boundary from the published stage powers, COPs, losses and interval width matches."""
    network, _, tank = _whole_network()
    outputs = _tank_outputs(network, tank)
    temperatures = _temperatures(outputs)
    hp, element = _stage_powers(outputs)
    periods = network.periods

    heat = (
        hp * np.asarray(tank["heat_pump"]["hp_cop"]) * periods
        + element * np.asarray(tank["element"]["element_cop"]) * periods
    )
    losses = (np.asarray(tank["thermal"]["loss_power"]) + np.asarray(tank["thermal"]["draw_power"])) * periods
    predicted = temperatures[0] + np.cumsum(heat - losses) / tank["thermal"]["capacity_per_degree"]

    np.testing.assert_allclose(temperatures[1:], predicted, atol=1e-9)


def test_reactive_updates_reach_connection_limits_and_thermal_parameters() -> None:
    """Edited config values change the plan on the same network, through both connections and the tank."""
    network, participants, tank = _whole_network()
    updater = build_element_updaters(network, participants)["tank"]
    periods = len(network.periods)

    limited = deepcopy(tank)
    limited["heat_pump"]["hp_max_power"] = np.full(periods, 0.4)
    limited["element"]["element_max_power"] = np.full(periods, 0.8)
    updater(limited)
    network.optimize()
    hp, element = _stage_powers(_tank_outputs(network, limited))

    assert hp[0] == pytest.approx(0.4)
    assert element[0] == pytest.approx(0.8)
    assert np.max(hp) <= 0.4 + 1e-9
    assert np.max(element) <= 0.8 + 1e-9

    retuned = deepcopy(tank)
    retuned["heat_pump"]["hp_cop"] = np.full(periods, 2.0)
    updater(retuned)
    network.optimize()
    outputs = _tank_outputs(network, retuned)
    hp, element = _stage_powers(outputs)

    # The weaker heat pump must run in the second period, which the baseline left to the element
    assert hp[1] > 0.1

    temperatures = _temperatures(outputs)
    heat = (
        hp * np.asarray(retuned["heat_pump"]["hp_cop"]) * network.periods
        + element * np.asarray(retuned["element"]["element_cop"]) * network.periods
    )
    losses = (
        np.asarray(retuned["thermal"]["loss_power"]) + np.asarray(retuned["thermal"]["draw_power"])
    ) * network.periods
    predicted = temperatures[0] + np.cumsum(heat - losses) / retuned["thermal"]["capacity_per_degree"]
    np.testing.assert_allclose(temperatures[1:], predicted, atol=1e-9)
