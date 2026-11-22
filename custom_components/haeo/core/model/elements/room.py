"""Room temperature dynamics driven by one shared whole-house HVAC connection."""

from collections.abc import Mapping
from typing import Final, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.model.element import Element
from custom_components.haeo.core.model.linear import LinearArray, Rows
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.model.reactive import TrackedParam, computed, constraint, cost, output
from custom_components.haeo.core.model.solver import Solver

from .hvac import Hvac

type RoomElementTypeName = Literal["room"]
type RoomOutputName = Literal["room_temperature", "room_cold_shortfall", "room_hot_shortfall"]
ROOM_OUTPUT_NAMES: Final[frozenset[RoomOutputName]] = frozenset(
    ("room_temperature", "room_cold_shortfall", "room_hot_shortfall")
)


class RoomElementConfig(TypedDict):
    """One measured room with a response to the shared HVAC input."""

    element_type: RoomElementTypeName
    name: str
    hvac: str
    initial_temperature: float
    outdoor_temperature: NDArray[np.float64]
    minimum_temperature: NDArray[np.float64]
    maximum_temperature: NDArray[np.float64]
    loss_rate: float
    response: float
    comfort_price: float


def room_arguments(config: RoomElementConfig, elements: Mapping[str, object], /) -> dict[str, object]:
    """Resolve the shared HVAC connection without adding independent room power."""
    hvac = elements[config["hvac"]]
    if not isinstance(hvac, Hvac):
        msg = "Room requires a shared HVAC model"
        raise TypeError(msg)
    return {**{k: v for k, v in config.items() if k not in ("name", "element_type")}, "hvac": hvac}


class Room(Element[RoomOutputName]):
    """First-order room model with soft two-sided comfort and exact passive decay.

    Mode is externally chosen: +1 heating, -1 cooling, 0 idle. All room instances
    must reference the same connection and mode for an unzoned HVAC appliance.
    Response is K per electrical kWh; loss_rate is 1/h. Heating/cooling is assumed
    uniform within each interval. No solar/internal gains or inter-room exchange
    are inferred; these are calibration limitations, not controllable zones.
    """

    dependency_order = 3

    initial_temperature: TrackedParam[float] = TrackedParam()
    outdoor_temperature: TrackedParam[NDArray[np.float64]] = TrackedParam()
    minimum_temperature: TrackedParam[NDArray[np.float64]] = TrackedParam()
    maximum_temperature: TrackedParam[NDArray[np.float64]] = TrackedParam()
    loss_rate: TrackedParam[float] = TrackedParam()
    response: TrackedParam[float] = TrackedParam()
    comfort_price: TrackedParam[float] = TrackedParam()

    def __init__(
        self,
        name: str,
        periods: NDArray[np.float64],
        *,
        solver: Solver,
        hvac: Hvac,
        initial_temperature: float,
        outdoor_temperature: NDArray[np.float64],
        minimum_temperature: NDArray[np.float64],
        maximum_temperature: NDArray[np.float64],
        loss_rate: float,
        response: float,
        comfort_price: float,
    ) -> None:
        """Allocate room temperatures and deviations, not electrical power variables."""
        super().__init__(name, periods, solver=solver, output_names=ROOM_OUTPUT_NAMES)
        self.hvac = hvac
        self.initial_temperature = initial_temperature
        self.outdoor_temperature = outdoor_temperature
        self.minimum_temperature = minimum_temperature
        self.maximum_temperature = maximum_temperature
        self.loss_rate = loss_rate
        self.response = response
        self.comfort_price = comfort_price
        self.temperature = solver.add_variables(self.n_periods + 1, name=f"{name}.temperature", lower=-np.inf)
        self.cold = solver.add_variables(self.n_periods + 1, name=f"{name}.cold")
        self.hot = solver.add_variables(self.n_periods + 1, name=f"{name}.hot")

    @computed
    def validate_inputs(self) -> None:
        """Reject invalid coefficients and forecasts, including reactive changes."""
        scalars = (self.initial_temperature, self.loss_rate, self.response, self.comfort_price)
        if (
            not all(np.isfinite(v) for v in scalars)
            or self.loss_rate < 0
            or self.response <= 0
            or self.comfort_price <= 0
        ):
            msg = "Room coefficients must be finite; loss nonnegative, response/price positive, mode -1/0/1"
            raise ValueError(msg)
        if np.any(self.periods <= 0) or not np.all(np.isfinite(self.periods)):
            msg = "Room intervals must be finite and positive"
            raise ValueError(msg)
        for values, size in (
            (self.outdoor_temperature, self.n_periods),
            (self.minimum_temperature, self.n_periods + 1),
            (self.maximum_temperature, self.n_periods + 1),
        ):
            if values.shape != (size,) or not np.all(np.isfinite(values)):
                msg = "Room forecasts must be finite and match the horizon"
                raise ValueError(msg)
        if np.any(self.minimum_temperature > self.maximum_temperature):
            msg = "Room comfort minimum cannot exceed maximum"
            raise ValueError(msg)

    @constraint
    def initial_state(self) -> Rows:
        """Use each room's own measured initial temperature."""
        self.validate_inputs()
        return self.temperature[0] == self.initial_temperature

    @constraint
    def dynamics(self) -> Rows:
        """Apply exact first-order decay with constant forcing over each interval."""
        self.validate_inputs()
        decay = np.exp(-self.loss_rate * self.periods)
        gain = -np.expm1(-self.loss_rate * self.periods) / self.loss_rate if self.loss_rate else self.periods
        return self.temperature[1:] == (
            self.temperature[:-1] * decay
            + (1 - decay) * self.outdoor_temperature
            + self.hvac.connection.total_power_out * (self.response * self.hvac.mode * gain)
        )

    @constraint
    def comfort(self) -> Rows:
        """Price unmet comfort rather than making an already-warm room infeasible."""
        self.validate_inputs()
        return Rows.concat(
            [
                self.temperature + self.cold >= self.minimum_temperature,
                self.temperature - self.hot <= self.maximum_temperature,
            ]
        )

    @cost
    def discomfort(self) -> LinearArray:
        """Price degree-hours, including a terminal interval-weighted boundary."""
        self.validate_inputs()
        weights = np.concatenate((self.periods, [self.periods[-1]]))
        return ((self.cold + self.hot) * weights * self.comfort_price).total()

    @output
    def room_temperature(self) -> OutputData:
        """Return predicted room temperatures at boundaries."""
        return OutputData(type=OutputType.TEMPERATURE, unit="°C", values=self.extract_values(self.temperature))

    @output
    def room_cold_shortfall(self) -> OutputData:
        """Return degrees below the comfort minimum, not an absolute temperature."""
        return OutputData(type=OutputType.COEFFICIENT, unit="K", values=self.extract_values(self.cold))

    @output
    def room_hot_shortfall(self) -> OutputData:
        """Return degrees above the comfort maximum."""
        return OutputData(type=OutputType.COEFFICIENT, unit="K", values=self.extract_values(self.hot))
