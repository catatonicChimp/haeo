"""Appliance element adapter for the relaxed plan and the run an actuator follows."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final, Literal

from custom_components.haeo.core.adapters.output_utils import expect_output_data
from custom_components.haeo.core.const import ConnectivityLevel
from custom_components.haeo.core.model import ModelElementConfig, ModelOutputName, ModelOutputValue
from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.model.element import ELEMENT_POWER_BALANCE
from custom_components.haeo.core.model.elements import MODEL_ELEMENT_TYPE_APPLIANCE, MODEL_ELEMENT_TYPE_CONNECTION
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.schema import extract_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.appliance import (
    CONF_ARMED,
    CONF_DURATION,
    CONF_ENERGY,
    CONF_IN_WINDOW,
    ELEMENT_TYPE,
    SECTION_SCHEDULE,
    SECTION_WINDOW,
    ApplianceConfigData,
)
from custom_components.haeo.core.schema.elements.buffer import CONF_LOADS, BufferRole
from custom_components.haeo.core.schema.sections import CONF_CONNECTION

type ApplianceElementOutputName = Literal["appliance_power", "appliance_planned_start"]

APPLIANCE_ELEMENT_OUTPUT_NAMES: Final[frozenset[ApplianceElementOutputName]] = frozenset(
    (
        APPLIANCE_POWER := "appliance_power",
        APPLIANCE_PLANNED_START := "appliance_planned_start",
    )
)

type ApplianceDeviceName = Literal[ElementType.APPLIANCE]

APPLIANCE_DEVICE_NAMES: Final[frozenset[ApplianceDeviceName]] = frozenset(
    (APPLIANCE_DEVICE := ElementType.APPLIANCE,),
)

# Runs that end within this many hours of the window's edge are treated as fitting
_FIT_EPSILON: Final = 1e-9
# Window masks hold 1 inside the allowed hours and 0 outside, so a period is open above this
_WINDOW_OPEN: Final = 0.5


class ApplianceAdapter:
    """Adapter for appliance elements."""

    element_type: str = ELEMENT_TYPE
    advanced: bool = False
    connectivity: ConnectivityLevel = ConnectivityLevel.NEVER
    can_source: bool = False
    can_sink: bool = True
    switchboard: bool = False
    device_names: frozenset[ApplianceDeviceName] = APPLIANCE_DEVICE_NAMES
    buffer_roles: frozenset[BufferRole] = frozenset({CONF_LOADS})

    def model_elements(self, config: ApplianceConfigData) -> list[ModelElementConfig]:
        """Create the appliance and the connection that supplies it from the configured node.

        The model plans a relaxed run: power may fill any allowed period up to
        the run's energy over its duration. Which single contiguous block of
        that length actually runs is decided from the plan in ``outputs``.
        """
        name = config["name"]
        schedule = config[SECTION_SCHEDULE]
        window = config[SECTION_WINDOW]
        return [
            {
                "element_type": MODEL_ELEMENT_TYPE_APPLIANCE,
                "name": name,
                "is_source": False,
                "is_sink": True,
                "in_window": window[CONF_IN_WINDOW],
                "energy": float(schedule[CONF_ENERGY]),
                "duration": float(schedule[CONF_DURATION]),
                "armed": bool(schedule[CONF_ARMED]),
            },
            {
                "element_type": MODEL_ELEMENT_TYPE_CONNECTION,
                "name": f"{name}:connection",
                "source": extract_connection_target(config[CONF_CONNECTION]),
                "target": name,
            },
        ]

    def outputs(
        self,
        name: str,
        model_outputs: Mapping[str, Mapping[ModelOutputName, ModelOutputValue]],
        *,
        config: ApplianceConfigData,
        periods: Sequence[float] = (),
        forecast_times: Sequence[datetime] | None = None,
        **_kwargs: object,
    ) -> Mapping[ApplianceDeviceName, Mapping[ApplianceElementOutputName, OutputData]]:
        """Expose the committed run as planned power and its start.

        The optimization is a continuous relaxation and may spread the run
        across the window. An actuator can only run one uninterrupted block of
        the configured length, so the block that runs is chosen here: each
        candidate start is the earliest period boundary whose block of the
        configured length stays inside the allowed hours, and the cheapest one
        wins, with the earliest breaking ties.

        Cost is the per-period energy of the block times the configured node's
        power-balance shadow price. That price is the marginal value of one
        more kWh at the connection point, which is the grid's import price when
        the node draws from the grid and its export price when the node
        exports. The node's balance is formulated in energy, so the price is
        already in $/kWh. When the node reports no price, such as an unpriced
        node, every candidate costs the same and the earliest that fits wins,
        which is the same placement as a zero import-minus-export price.

        A run that cannot fit its window, or is disarmed, commits no power and
        reports its start as unavailable.
        """
        name_values = model_outputs[name]
        schedule = config[SECTION_SCHEDULE]
        window = config[SECTION_WINDOW]

        relaxed = expect_output_data(name_values.get(APPLIANCE_POWER))
        period_count = len(relaxed.values) if relaxed is not None else len(window[CONF_IN_WINDOW])

        widths = tuple(float(width) for width in periods)
        if len(widths) != period_count:
            widths = (1.0,) * period_count

        prices = _node_price(model_outputs, config, period_count)

        armed = bool(schedule[CONF_ARMED])
        energy = float(schedule[CONF_ENERGY]) if armed else 0.0
        committed, start = _commit_run(
            in_window=tuple(float(value) for value in window[CONF_IN_WINDOW]),
            prices=prices,
            widths=widths,
            energy=energy,
            duration=float(schedule[CONF_DURATION]),
        )

        start_at: datetime | None = None
        if start is not None and forecast_times is not None and start < len(forecast_times):
            start_at = forecast_times[start]

        return {
            APPLIANCE_DEVICE: {
                APPLIANCE_POWER: OutputData(
                    type=OutputType.POWER,
                    unit="kW",
                    values=committed,
                    direction="-",
                ),
                APPLIANCE_PLANNED_START: OutputData(
                    type=OutputType.TIMESTAMP,
                    unit=None,
                    values=(start_at,) if start_at is not None else (),
                    state=start_at,
                    available=start_at is not None,
                ),
            }
        }


def _node_price(
    model_outputs: Mapping[str, Mapping[ModelOutputName, ModelOutputValue]],
    config: ApplianceConfigData,
    period_count: int,
) -> tuple[float, ...]:
    """Return the configured node's marginal price in each period, or zeros when it has none."""
    source_name = extract_connection_target(config[CONF_CONNECTION])
    node_price = expect_output_data(model_outputs.get(source_name, {}).get(ELEMENT_POWER_BALANCE))
    if node_price is None:
        return (0.0,) * period_count
    prices = tuple(float(value) for value in node_price.values)
    return prices if len(prices) == period_count else (0.0,) * period_count


def _commit_run(
    *,
    in_window: Sequence[float],
    prices: Sequence[float],
    widths: Sequence[float],
    energy: float,
    duration: float,
) -> tuple[tuple[float, ...], int | None]:
    """Return the committed per-period power and the start period of the cheapest fitting block."""
    count = len(widths)
    if energy <= 0.0 or duration <= 0.0 or count == 0:
        return (0.0,) * count, None

    power = energy / duration
    best_cost: float | None = None
    best_start: int | None = None
    best_fractions: tuple[float, ...] = (0.0,) * count

    for start in range(count):
        remaining = duration
        fractions = [0.0] * count
        cost = 0.0
        index = start
        while index < count and remaining > _FIT_EPSILON:
            width = widths[index]
            if width <= _FIT_EPSILON or in_window[index] <= _WINDOW_OPEN:
                break
            take = min(remaining, width)
            fractions[index] = take / width
            cost += prices[index] * power * take
            remaining -= take
            index += 1
        if remaining > _FIT_EPSILON:
            continue
        if best_cost is None or cost < best_cost - _FIT_EPSILON:
            best_cost = cost
            best_start = start
            best_fractions = tuple(fractions)

    if best_start is None:
        return (0.0,) * count, None
    return tuple(power * fraction for fraction in best_fractions), best_start


adapter = ApplianceAdapter()
