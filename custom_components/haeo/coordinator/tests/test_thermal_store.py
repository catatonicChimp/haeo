"""Prove an armed appliance's committed run and the two-stage tank share one published plan."""

import numpy as np
import pytest

from custom_components.haeo.coordinator.coordinator import commit_appliance_runs
from custom_components.haeo.core.adapters.elements.appliance import adapter as appliance_adapter
from custom_components.haeo.core.adapters.elements.thermal_store import adapter as thermal_adapter
from custom_components.haeo.core.adapters.network_builder import build_network
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.appliance import ApplianceConfigData
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData


async def test_committed_appliance_run_publishes_consistent_thermal_outputs() -> None:
    """Thermal outputs come from the solve that pins the run, not from the relaxed plan."""
    periods = 4
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("switchboard"),
        thermal={
            "initial_temperature": 55.0,
            "target_temperature": np.array([55.0] * periods + [68.0]),
            "maximum_temperature": 75.0,
            "capacity_per_degree": 0.314,
            "loss_power": np.full(periods, 0.05),
            "draw_power": np.full(periods, 0.02),
            "shortfall_price": np.full(periods + 1, 10.0),
        },
        heat_pump={
            "hp_ceiling_temperature": 65.0,
            "hp_max_power": np.full(periods, 0.8),
            "hp_cop": np.full(periods, 3.0),
        },
        element={
            "element_max_power": np.full(periods, 0.7),
            "element_cop": np.full(periods, 1.0),
        },
    )
    dishwasher = ApplianceConfigData(
        name="dishwasher",
        element_type=ElementType.APPLIANCE,
        connection=as_connection_target("switchboard"),
        schedule={"armed": True, "energy": 2.0, "duration": 2.0},
        window={"earliest_start": 0.0, "latest_finish": 24.0, "in_window": np.ones(periods)},
    )
    participants: dict[str, ElementConfigData] = {
        "switchboard": {"name": "switchboard", "element_type": ElementType.JUNCTION},
        "grid": {
            "name": "grid",
            "element_type": ElementType.GRID,
            "connection": as_connection_target("switchboard"),
            "pricing": {
                "price_source_target": np.array([0.0, 0.3, 0.3, 0.0]),
                "price_target_source": np.zeros(periods),
            },
            "power_limits": {"max_power_source_target": 2.0},
        },
        "base": {
            "name": "base",
            "element_type": ElementType.LOAD,
            "connection": as_connection_target("switchboard"),
            "forecast": {"forecast": np.full(periods, 0.4)},
            "curtailment": {},
        },
        "dishwasher": dishwasher,
        "tank": tank,
    }
    network = build_network("shadow", participants, [3600.0] * periods)

    relaxed_cost = network.optimize()
    relaxed_outputs = {name: element.outputs() for name, element in network.elements.items()}
    relaxed_temperatures = np.asarray(
        thermal_adapter.outputs("tank", relaxed_outputs, config=tank)[ElementType.THERMAL_STORE][
            "thermal_store_temperature"
        ].values,
        dtype=float,
    )

    async def run_optimize() -> float:
        return network.optimize()

    outputs, cost, committed = await commit_appliance_runs(
        network, participants, relaxed_outputs, relaxed_cost, run_optimize
    )

    assert committed.keys() == {"dishwasher"}
    plan = committed["dishwasher"]
    assert plan.start is not None
    assert cost > relaxed_cost

    appliance_outputs = appliance_adapter.outputs(
        "dishwasher",
        outputs,
        config=dishwasher,
        periods=[float(width) for width in network.periods],
        committed=plan,
    )[ElementType.APPLIANCE]
    appliance_power = np.asarray(appliance_outputs["appliance_power"].values, dtype=float)
    np.testing.assert_allclose(appliance_power, np.asarray(plan.power, dtype=float), atol=1e-12)

    thermal_outputs = thermal_adapter.outputs("tank", outputs, config=tank)[ElementType.THERMAL_STORE]
    total = np.asarray(thermal_outputs["thermal_store_power"].values, dtype=float)
    hp = np.asarray(thermal_outputs["thermal_store_power_hp"].values, dtype=float)
    element = np.asarray(thermal_outputs["thermal_store_power_element"].values, dtype=float)
    np.testing.assert_allclose(total, hp + element, atol=1e-12)

    temperatures = np.asarray(thermal_outputs["thermal_store_temperature"].values, dtype=float)
    assert not np.allclose(temperatures, relaxed_temperatures)

    base = np.asarray(outputs["base:connection"]["connection_power"].values, dtype=float)
    imported = np.asarray(outputs["grid:import"]["connection_power"].values, dtype=float)
    np.testing.assert_allclose(imported, base + total + appliance_power, atol=1e-12)

    assert float(np.max(thermal_outputs["thermal_store_shortfall"].values)) == pytest.approx(0.0, abs=1e-9)
