"""Prove an armed appliance's committed run and the two-stage tank share one published plan."""

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
import time

from highspy import HighsStatus, HighsVarType
import numpy as np
from numpy.typing import NDArray
import pytest

from custom_components.haeo.coordinator.coordinator import commit_appliance_runs
from custom_components.haeo.core.adapters.elements.appliance import adapter as appliance_adapter
from custom_components.haeo.core.adapters.elements.thermal_store import adapter as thermal_adapter
from custom_components.haeo.core.adapters.network_builder import build_element_updaters, build_network
from custom_components.haeo.core.model.infeasibility import InfeasibleError
from custom_components.haeo.core.model.solver import Solver
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.appliance import ApplianceConfigData
from custom_components.haeo.core.schema.elements.battery import BatteryConfigData
from custom_components.haeo.core.schema.elements.grid import GridConfigData
from custom_components.haeo.core.schema.elements.load import LoadConfigData
from custom_components.haeo.core.schema.elements.solar import SolarConfigData
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


_PRODUCTION_INTERVALS = 73
_PRODUCTION_WIDTHS_SECONDS: NDArray[np.float64] = np.array([60.0] * 12 + [300.0] * 12 + [900.0] * 12 + [1800.0] * 37)


@dataclass(frozen=True, slots=True)
class _SolverRun:
    """One HiGHS run, sampled before the fixed LP can overwrite MIP telemetry."""

    duration: float
    status: str
    node_count: int
    gap: float
    dual_bound: float
    objective: float


@dataclass(frozen=True, slots=True)
class _Stage:
    """The two MIPs and the LP runs of one production solve."""

    primary: _SolverRun
    secondary: _SolverRun
    lp_duration: float
    lp_runs: int


def _record_solver_runs(monkeypatch: pytest.MonkeyPatch) -> list[_SolverRun]:
    """Record every HiGHS run's timing and MIP telemetry through the solver's public surface."""
    runs: list[_SolverRun] = []
    original_run = Solver.run

    def run(solver: Solver) -> HighsStatus:
        started = time.perf_counter()
        status = original_run(solver)
        duration = time.perf_counter() - started
        runs.append(
            _SolverRun(
                duration=duration,
                status=solver.modelStatusToString(solver.getModelStatus()),
                node_count=int(solver.getInfoValue("mip_node_count")[1]),
                gap=float(solver.getInfoValue("mip_gap")[1]),
                dual_bound=float(solver.getInfoValue("mip_dual_bound")[1]),
                objective=solver.getObjectiveValue(),
            )
        )
        return status

    monkeypatch.setattr(Solver, "run", run)
    return runs


def _stage(runs: Sequence[_SolverRun]) -> _Stage:
    """Split one solve's runs into its primary MIP, secondary MIP, and fixed-LP remainder."""
    mip_runs = [run for run in runs if run.node_count >= 0]
    assert len(mip_runs) == 2, "a production solve runs exactly a primary and a secondary MIP"
    lp_runs = [run for run in runs if run.node_count < 0]
    return _Stage(
        primary=mip_runs[0],
        secondary=mip_runs[1],
        lp_duration=sum(run.duration for run in lp_runs),
        lp_runs=len(lp_runs),
    )


def _stage_line(label: str, stage: _Stage, duration: float) -> str:
    """Return one benchmark line with the stage's wall time and MIP telemetry."""
    return (
        f"  {label:<9} {duration:6.3f} s | "
        f"primary {stage.primary.duration:6.3f} s nodes {stage.primary.node_count} "
        f"gap {stage.primary.gap:.1e} bound {stage.primary.dual_bound:.4f} | "
        f"secondary {stage.secondary.duration:6.3f} s nodes {stage.secondary.node_count} "
        f"gap {stage.secondary.gap:.1e} bound {stage.secondary.dual_bound:.4f} | "
        f"LP {stage.lp_duration:6.3f} s ({stage.lp_runs} runs)"
    )


def _production_participants() -> tuple[dict[str, ElementConfigData], ThermalStoreConfigData, ApplianceConfigData]:
    """Return a sanitized production network: battery, solar, load, grid, tank, and an armed appliance."""
    intervals = _PRODUCTION_INTERVALS
    boundaries_hours = np.cumsum(np.concatenate(([0.0], _PRODUCTION_WIDTHS_SECONDS))) / 3600.0
    phase = boundaries_hours[:-1] / boundaries_hours[-1] * 2.0 * np.pi
    solar = np.maximum(0.0, 1.5 * np.sin(phase) + 0.2)
    load = 1.5 + 0.4 * np.cos(2.0 * phase) * 0.5
    prices = np.where(
        (boundaries_hours[:-1] < 6.0) | ((boundaries_hours[:-1] > 14.0) & (boundaries_hours[:-1] < 15.5)),
        0.0,
        0.25 + 0.1 * np.sin(phase),
    )

    battery = BatteryConfigData(
        element_type=ElementType.BATTERY,
        name="battery",
        connection=as_connection_target("switchboard"),
        storage={"capacity": np.full(intervals + 1, 13.2), "initial_charge_percentage": 0.3},
        limits={"min_charge_percentage": 0.2, "max_charge_percentage": 1.0},
        power_limits={
            "max_power_source_target": np.full(intervals, 7.6),
            "max_power_target_source": np.full(intervals, 7.6),
        },
        pricing={"salvage_value": 0.0},
        efficiency={
            "efficiency_source_target": np.full(intervals, 0.95),
            "efficiency_target_source": np.full(intervals, 0.95),
        },
        advanced={"charge_limit_cost": 100.0},
    )
    solar_config = SolarConfigData(
        element_type=ElementType.SOLAR,
        name="solar",
        connection=as_connection_target("switchboard"),
        forecast={"forecast": solar},
        curtailment={"curtailment": True},
    )
    load_config = LoadConfigData(
        element_type=ElementType.LOAD,
        name="base",
        connection=as_connection_target("switchboard"),
        forecast={"forecast": load},
        curtailment={"curtailment": False},
    )
    grid = GridConfigData(
        element_type=ElementType.GRID,
        name="grid",
        connection=as_connection_target("switchboard"),
        pricing={"price_source_target": prices, "price_target_source": np.zeros(intervals)},
        power_limits={"max_power_source_target": 11.0, "max_power_target_source": 10.0},
    )
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("switchboard"),
        thermal={
            "initial_temperature": 55.0,
            "target_temperature": np.array([55.0] * intervals + [60.0]),
            "maximum_temperature": 75.0,
            "capacity_per_degree": 0.314,
            "loss_power": np.full(intervals, 0.12),
            "draw_power": np.full(intervals, 0.2),
            "shortfall_price": np.full(intervals + 1, 10.0),
        },
        heat_pump={
            "hp_ceiling_temperature": 70.0,
            "hp_max_power": np.full(intervals, 0.8),
            "hp_cop": np.full(intervals, 3.0),
        },
        element={
            "element_max_power": np.full(intervals, 0.87),
            "element_cop": np.full(intervals, 1.0),
        },
    )
    dishwasher = ApplianceConfigData(
        name="dishwasher",
        element_type=ElementType.APPLIANCE,
        connection=as_connection_target("switchboard"),
        schedule={"armed": True, "energy": 0.945, "duration": 2.5},
        window={"earliest_start": 0.0, "latest_finish": 24.0, "in_window": np.ones(intervals)},
    )
    participants: dict[str, ElementConfigData] = {
        "switchboard": {"name": "switchboard", "element_type": ElementType.JUNCTION},
        "grid": grid,
        "battery": battery,
        "solar": solar_config,
        "base": load_config,
        "tank": tank,
        "dishwasher": dishwasher,
    }
    return participants, tank, dishwasher


async def test_production_shaped_network_stays_within_cadence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production network, its pinned appliance solve, and a reactive re-solve fit the cadence budget."""
    participants, tank, _ = _production_participants()
    network = build_network("production", participants, _PRODUCTION_WIDTHS_SECONDS.tolist())
    runs = _record_solver_runs(monkeypatch)

    mark = len(runs)
    started = time.perf_counter()
    cost = network.optimize()
    initial_duration = time.perf_counter() - started
    initial = _stage(runs[mark:])

    relaxed_outputs = {name: element.outputs() for name, element in network.elements.items()}

    async def run_optimize() -> float:
        return network.optimize()

    mark = len(runs)
    started = time.perf_counter()
    _, committed_cost, committed = await commit_appliance_runs(
        network, participants, relaxed_outputs, cost, run_optimize
    )
    pinned_duration = time.perf_counter() - started
    pinned = _stage(runs[mark:])

    updater = build_element_updaters(network, participants)["tank"]
    warmed = deepcopy(tank)
    warmed["thermal"]["initial_temperature"] = 56.0
    updater(warmed)

    mark = len(runs)
    started = time.perf_counter()
    reactive_cost = network.optimize()
    reactive_duration = time.perf_counter() - started
    reactive = _stage(runs[mark:])

    total_duration = initial_duration + pinned_duration + reactive_duration
    report = [
        "Production-shaped MIP benchmark (73 intervals, 1-min widening to 30-min):",
        _stage_line("initial", initial, initial_duration),
        _stage_line("pinned", pinned, pinned_duration),
        _stage_line("reactive", reactive, reactive_duration),
        f"  total     {total_duration:6.3f} s (budget 5.000 s)",
    ]
    print("\n".join(report))  # noqa: T201 (the benchmark timings must reach the CI job log)

    for stage in (initial, pinned, reactive):
        assert stage.primary.status == "Optimal"
        assert stage.secondary.status == "Optimal"
        assert stage.primary.node_count >= 0
        assert stage.secondary.node_count >= 0
        assert stage.primary.gap <= 1e-9
        assert stage.secondary.gap <= 1e-9
        assert np.isfinite(stage.primary.dual_bound)
        assert np.isfinite(stage.secondary.dual_bound)

    assert committed.keys() == {"dishwasher"}
    assert committed["dishwasher"].start is not None
    assert np.isfinite(cost)
    assert np.isfinite(committed_cost)
    assert np.isfinite(reactive_cost)
    assert total_duration < 5.0


async def test_infeasible_pinned_candidate_retries_and_restores_integers() -> None:
    """An unsupplyable cheapest block is skipped, a later block commits, and the MIP columns stay usable."""
    periods = 4
    tank = ThermalStoreConfigData(
        name="tank",
        element_type=ElementType.THERMAL_STORE,
        connection=as_connection_target("switchboard"),
        thermal={
            "initial_temperature": 60.0,
            "target_temperature": np.full(periods + 1, 60.0),
            "maximum_temperature": 75.0,
            "capacity_per_degree": 0.314,
            "loss_power": np.zeros(periods),
            "draw_power": np.zeros(periods),
            "shortfall_price": np.full(periods + 1, 10.0),
        },
        heat_pump={
            "hp_ceiling_temperature": 65.0,
            "hp_max_power": np.full(periods, 0.8),
            "hp_cop": np.full(periods, 3.0),
        },
        element={
            "element_max_power": np.full(periods, 0.87),
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
            "pricing": {"price_source_target": np.zeros(periods), "price_target_source": np.zeros(periods)},
            # The opening period cannot supply a pinned block; the later periods can.
            "power_limits": {
                "max_power_source_target": np.array([0.0, 2.0, 2.0, 2.0]),
                "max_power_target_source": np.zeros(periods),
            },
        },
        "dishwasher": dishwasher,
        "tank": tank,
    }
    network = build_network("retry", participants, [3600.0] * periods)

    relaxed_cost = network.optimize()
    relaxed_outputs = {name: element.outputs() for name, element in network.elements.items()}

    attempts: list[bool] = []

    async def run_optimize() -> float:
        try:
            result = network.optimize()
        except InfeasibleError:
            attempts.append(False)
            raise
        attempts.append(True)
        return result

    outputs, cost, committed = await commit_appliance_runs(
        network, participants, relaxed_outputs, relaxed_cost, run_optimize
    )

    # The cheapest block starts in the blocked period, fails, and a later block succeeds.
    assert attempts[0] is False
    assert attempts[-1] is True
    assert True in attempts
    plan = committed["dishwasher"]
    assert plan.start is not None
    assert plan.start > 0
    assert np.isfinite(cost)

    appliance_outputs = appliance_adapter.outputs(
        "dishwasher",
        outputs,
        config=dishwasher,
        periods=[float(width) for width in network.periods],
        committed=plan,
    )[ElementType.APPLIANCE]
    appliance_power = np.asarray(appliance_outputs["appliance_power"].values, dtype=float)
    np.testing.assert_allclose(appliance_power, np.asarray(plan.power, dtype=float), atol=1e-12)
    assert appliance_power[0] == pytest.approx(0.0, abs=1e-9)

    thermal_outputs = thermal_adapter.outputs("tank", outputs, config=tank)[ElementType.THERMAL_STORE]
    total = np.asarray(thermal_outputs["thermal_store_power"].values, dtype=float)
    hp = np.asarray(thermal_outputs["thermal_store_power_hp"].values, dtype=float)
    element = np.asarray(thermal_outputs["thermal_store_power_element"].values, dtype=float)
    np.testing.assert_allclose(total, hp + element, atol=1e-12)

    solver = network._solver
    assert solver.has_integer_columns is True
    integer_columns = solver.integer_columns
    bounds = solver.getLp()
    for column in integer_columns:
        column_index = int(column)
        assert solver.getColIntegrality(column_index)[1] == HighsVarType.kInteger
        assert bounds.col_lower_[column_index] == 0.0
        assert bounds.col_upper_[column_index] == 1.0

    # A fresh solve after the commit proves the restored binary columns are still usable.
    network.optimize()
    binary_values = solver.column_values()[integer_columns]
    assert np.all(binary_values >= 0.0)
    assert np.all(binary_values <= 1.0)
    np.testing.assert_allclose(binary_values, np.rint(binary_values), atol=1e-9)
