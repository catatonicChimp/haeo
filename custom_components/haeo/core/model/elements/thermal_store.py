"""Experimental lumped hot-water store coupled to an electrical connection.

This continuous-power relaxation is for offline research, not appliance control.
Heat and draw are thermal kWh; losses are thermal kW; capacity is kWh/K.
"""

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

from .connection import Connection, ConnectionOutputName

type ThermalStoreElementTypeName = Literal["thermal_store"]
type ThermalStoreOutputName = Literal["thermal_store_energy", "thermal_store_shortfall"]
ELEMENT_TYPE: Final[ThermalStoreElementTypeName] = "thermal_store"
THERMAL_STORE_OUTPUT_NAMES: Final[frozenset[ThermalStoreOutputName]] = frozenset(
    ("thermal_store_energy", "thermal_store_shortfall")
)


class ThermalStoreElementConfig(TypedDict):
    """Loaded model inputs; period arrays have T entries, targets T+1."""

    element_type: ThermalStoreElementTypeName
    name: str
    connection: str
    capacity_per_degree: float
    initial_temperature: float
    reference_temperature: float
    maximum_temperature: float
    cop: NDArray[np.float64]
    loss_power: NDArray[np.float64]
    draw_energy: NDArray[np.float64]
    target_temperature: NDArray[np.float64]
    shortfall_price: NDArray[np.float64]


def thermal_store_arguments(config: ThermalStoreElementConfig, elements: Mapping[str, object], /) -> dict[str, object]:
    """Resolve the electrical connection before building the thermal overlay."""
    connection = elements[config["connection"]]
    if not isinstance(connection, Connection):
        msg = "Thermal store requires an electrical connection"
        raise TypeError(msg)
    return {
        **{key: value for key, value in config.items() if key not in ("element_type", "name")},
        "connection": connection,
    }


class ThermalStore(Element[ThermalStoreOutputName]):
    """Constrain a load connection using a thermal balance and soft readiness targets.

    Reference temperature is the zero-energy datum, not a configurable comfort
    floor. The physical maximum is hard; targets are soft, including the terminal
    target. A constant draw forecast is prescribed thermal extraction, not a
    stratified tank or temperature-dependent flow model.
    """

    initial_temperature: TrackedParam[float] = TrackedParam()
    cop: TrackedParam[NDArray[np.float64]] = TrackedParam()
    loss_power: TrackedParam[NDArray[np.float64]] = TrackedParam()
    draw_energy: TrackedParam[NDArray[np.float64]] = TrackedParam()
    target_temperature: TrackedParam[NDArray[np.float64]] = TrackedParam()
    shortfall_price: TrackedParam[NDArray[np.float64]] = TrackedParam()

    def __init__(
        self,
        name: str,
        periods: NDArray[np.float64],
        *,
        solver: Solver,
        connection: Connection[ConnectionOutputName],
        capacity_per_degree: float,
        initial_temperature: float,
        reference_temperature: float,
        maximum_temperature: float,
        cop: NDArray[np.float64],
        loss_power: NDArray[np.float64],
        draw_energy: NDArray[np.float64],
        target_temperature: NDArray[np.float64],
        shortfall_price: NDArray[np.float64],
    ) -> None:
        """Create boundary energy states attached to the connection's delivered power."""
        if (
            not np.isfinite(capacity_per_degree)
            or capacity_per_degree <= 0
            or not np.isfinite(reference_temperature)
            or not np.isfinite(maximum_temperature)
            or maximum_temperature <= reference_temperature
        ):
            msg = "Thermal capacity must be positive and physical temperature bounds finite and ordered"
            raise ValueError(msg)
        super().__init__(name, periods, solver=solver, output_names=THERMAL_STORE_OUTPUT_NAMES)
        self.connection = connection
        self.capacity_per_degree = capacity_per_degree
        self.reference_temperature = reference_temperature
        self.initial_temperature = initial_temperature
        self.cop = cop
        self.loss_power = loss_power
        self.draw_energy = draw_energy
        self.target_temperature = target_temperature
        self.shortfall_price = shortfall_price
        self.energy = solver.add_variables(
            self.n_periods + 1,
            name=f"{name}.energy",
            upper=capacity_per_degree * (maximum_temperature - reference_temperature),
        )
        self.shortfall = solver.add_variables(self.n_periods + 1, name=f"{name}.shortfall")

    @computed
    def validate_inputs(self) -> None:
        """Reject malformed or nonphysical forecasts, including reactive updates."""
        if not np.isfinite(self.initial_temperature):
            msg = "Initial temperature must be finite"
            raise ValueError(msg)
        if not np.all(np.isfinite(self.periods)) or np.any(self.periods <= 0):
            msg = "Thermal periods must be finite and positive"
            raise ValueError(msg)
        for name, values, count, strictly_positive in (
            ("cop", self.cop, self.n_periods, True),
            ("loss_power", self.loss_power, self.n_periods, False),
            ("draw_energy", self.draw_energy, self.n_periods, False),
            ("shortfall_price", self.shortfall_price, self.n_periods + 1, True),
        ):
            if (
                values.shape != (count,)
                or not np.all(np.isfinite(values))
                or np.any(values <= 0 if strictly_positive else values < 0)
            ):
                msg = f"{name} must have {count} finite {'positive' if strictly_positive else 'nonnegative'} values"
                raise ValueError(msg)
        if self.target_temperature.shape != (self.n_periods + 1,) or not np.all(np.isfinite(self.target_temperature)):
            msg = "Target temperatures must be finite and have one value per boundary"
            raise ValueError(msg)

    @constraint
    def initial_energy(self) -> Rows:
        """Pin the measured initial state, without forcing a comfort target."""
        self.validate_inputs()
        return self.energy[0] == self.capacity_per_degree * (self.initial_temperature - self.reference_temperature)

    @constraint
    def heat_balance(self) -> Rows:
        """Conserve thermal energy; electrical power variables belong to HAEO."""
        self.validate_inputs()
        return self.energy[1:] == (
            self.energy[:-1]
            + self.connection.total_power_out * self.cop * self.periods
            - self.loss_power * self.periods
            - self.draw_energy
        )

    @constraint
    def readiness(self) -> Rows:
        """Allow and expose unmet comfort, never relax the physical energy balance."""
        self.validate_inputs()
        return (
            self.energy + self.shortfall
            >= (self.target_temperature - self.reference_temperature) * self.capacity_per_degree
        )

    @cost
    def comfort_cost(self) -> LinearArray:
        """Price each boundary's thermal shortfall, including terminal readiness."""
        self.validate_inputs()
        return (self.shortfall * self.shortfall_price).total()

    def temperatures(self) -> tuple[float, ...]:
        """Return predicted boundary temperatures in C for offline diagnostics."""
        return tuple(
            value / self.capacity_per_degree + self.reference_temperature for value in self.extract_values(self.energy)
        )

    @output
    def thermal_store_energy(self) -> OutputData:
        """Return stored thermal energy above the reference temperature."""
        return OutputData(type=OutputType.ENERGY, unit="kWh", values=self.extract_values(self.energy))

    @output
    def thermal_store_shortfall(self) -> OutputData:
        """Return thermal energy missing from readiness targets."""
        return OutputData(type=OutputType.ENERGY, unit="kWh", values=self.extract_values(self.shortfall))
