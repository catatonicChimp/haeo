"""Solve a whole appliance network and check the run the adapter commits.

The appliance model is a continuous relaxation, so these tests go through the
normal build lifecycle and assert what the adapter reports to Home Assistant:
one contiguous block of the configured length, in the cheapest periods the
allowed hours leave available.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from custom_components.haeo.core.adapters.elements.appliance import adapter
from custom_components.haeo.core.adapters.network_builder import build_network
from custom_components.haeo.core.data.loader.config_loader import load_element_config_from_values
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementConfigData, ElementType
from custom_components.haeo.core.schema.elements.appliance import ApplianceConfigData

PERIOD_SECONDS = 3600.0


def _forecast_times(count: int) -> list[datetime]:
    """Return one boundary datetime per period start, plus the horizon end."""
    return [datetime(2024, 1, 1, hour, tzinfo=UTC) for hour in range(count + 1)]


def _appliance(
    *,
    prices: list[float],
    in_window: list[float] | None = None,
    energy: float = 1.0,
    duration: float = 1.0,
    armed: bool = True,
) -> tuple[dict[str, ElementConfigData], ApplianceConfigData]:
    """Build a switchboard, a priced grid, and an appliance connected to the switchboard."""
    periods = len(prices)
    appliance = ApplianceConfigData(
        name="Dishwasher",
        element_type=ElementType.APPLIANCE,
        connection=as_connection_target("Switchboard"),
        schedule={"armed": armed, "energy": energy, "duration": duration},
        window={
            "earliest_start": 0.0,
            "latest_finish": 24.0,
            "in_window": np.asarray(in_window if in_window is not None else [1.0] * periods),
        },
    )
    participants: dict[str, ElementConfigData] = {
        "Switchboard": {"element_type": ElementType.JUNCTION, "name": "Switchboard"},
        "Grid": {
            "element_type": ElementType.GRID,
            "name": "Grid",
            "connection": as_connection_target("Switchboard"),
            "pricing": {"price_source_target": np.asarray(prices), "price_target_source": np.zeros(periods)},
            "power_limits": {},
        },
        # A steady base load keeps the switchboard importing, so its power-balance
        # shadow price is the grid's import price in each period.
        "Base": {
            "element_type": ElementType.LOAD,
            "name": "Base",
            "connection": as_connection_target("Switchboard"),
            "forecast": {"forecast": np.ones(periods)},
            "curtailment": {"curtailment": False},
        },
        "Dishwasher": appliance,
    }
    return participants, appliance


def _committed(
    participants: dict[str, ElementConfigData], appliance: ApplianceConfigData, period_count: int
) -> tuple[tuple[float, ...], datetime | None, bool]:
    """Solve the network and return the committed power, the planned start, and its availability."""
    network = build_network("shadow", participants, [PERIOD_SECONDS] * period_count)
    network.optimize()
    outputs = {name: element.outputs() for name, element in network.elements.items()}
    result = adapter.outputs(
        "Dishwasher",
        outputs,
        config=appliance,
        periods=tuple(float(period) for period in network.periods),
        forecast_times=_forecast_times(period_count),
    )
    device = result[ElementType.APPLIANCE]
    start = device["appliance_planned_start"]
    start_at = start.state if isinstance(start.state, datetime) else None
    return device["appliance_power"].values, start_at, start.available


def test_appliance_runs_in_the_cheapest_period() -> None:
    """A one-hour run lands in the cheapest allowed period, not the first one."""
    participants, appliance = _appliance(prices=[0.3, 0.1, 0.2])

    values, start, available = _committed(participants, appliance, 3)

    assert values == pytest.approx((0.0, 1.0, 0.0))
    assert start == datetime(2024, 1, 1, 1, tzinfo=UTC)
    assert available is True


def test_appliance_runs_as_one_contiguous_block() -> None:
    """A two-hour run covers two adjacent periods and never splits around the cheap one."""
    participants, appliance = _appliance(prices=[0.3, 0.1, 0.05], duration=2.0)

    values, start, available = _committed(participants, appliance, 3)

    assert values == pytest.approx((0.0, 0.5, 0.5))
    assert start == datetime(2024, 1, 1, 1, tzinfo=UTC)
    assert available is True


def test_disarmed_appliance_plans_nothing() -> None:
    """A disarmed appliance draws no power and reports no planned start."""
    participants, appliance = _appliance(prices=[0.3, 0.1, 0.2], armed=False)

    values, start, available = _committed(participants, appliance, 3)

    assert values == pytest.approx((0.0, 0.0, 0.0))
    assert start is None
    assert available is False


def test_window_that_cannot_fit_the_run_reports_unavailable() -> None:
    """A window with no allowed periods leaves the solve feasible but commits no run."""
    participants, appliance = _appliance(prices=[0.3, 0.1, 0.2], in_window=[0.0, 0.0, 0.0])

    values, start, available = _committed(participants, appliance, 3)

    assert values == pytest.approx((0.0, 0.0, 0.0))
    assert start is None
    assert available is False


def _window_mask(earliest: float, latest: float, hours: list[int]) -> list[float]:
    """Load an appliance config and return the derived window mask over the given start hours."""
    config = {
        "element_type": ElementType.APPLIANCE,
        "name": "Dishwasher",
        "connection": as_connection_target("Switchboard"),
        "schedule": {},
        "window": {},
    }
    forecast_times = [datetime(2024, 1, 1, hour, tzinfo=UTC).timestamp() for hour in hours] + [
        datetime(2024, 1, 2, tzinfo=UTC).timestamp()
    ]
    loaded = load_element_config_from_values(
        "Dishwasher",
        config,  # type: ignore[arg-type]  # deliberately loose fixture; the loader validates the type
        {
            ("schedule", "armed"): True,
            ("schedule", "energy"): 1.0,
            ("schedule", "duration"): 1.0,
            ("window", "earliest_start"): earliest,
            ("window", "latest_finish"): latest,
        },
        forecast_times,
        time_zone=UTC,
    )
    # The loader returns the union of element configs; the appliance schema fixes this shape.
    loaded_window = loaded["window"]  # type: ignore[reportGeneralTypeIssues]
    assert isinstance(loaded_window, dict)
    mask = loaded_window["in_window"]
    assert isinstance(mask, np.ndarray)
    return [float(value) for value in mask]


def test_same_day_window_keeps_only_its_hours() -> None:
    """A 9 to 17 window keeps the periods that start between those hours."""
    assert _window_mask(9.0, 17.0, [8, 9, 16, 17]) == [0.0, 1.0, 1.0, 0.0]


def test_overnight_window_wraps_past_midnight() -> None:
    """A 22 to 2 window keeps the late evening and the early morning."""
    assert _window_mask(22.0, 2.0, [21, 22, 23, 0, 1, 2]) == [0.0, 1.0, 1.0, 1.0, 1.0, 0.0]


def test_equal_bounds_cover_the_whole_day() -> None:
    """Equal bounds allow every period, so a run can go whenever it is cheapest."""
    assert _window_mask(0.0, 0.0, [0, 6, 12, 18]) == [1.0, 1.0, 1.0, 1.0]


def test_full_day_window_ending_at_24_hours_keeps_every_period() -> None:
    """The default 0 to 24 window does not wrap, and still lets a run start late at night."""
    assert _window_mask(0.0, 24.0, [0, 12, 23]) == [1.0, 1.0, 1.0]
