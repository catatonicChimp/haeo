"""Two-stage hot-water store with heat-pump ceiling gating.

One continuous total-energy state tracks thermal kWh above a reference
temperature. A binary variable per interval decides whether the heat pump may
run; the resistive element can run at any energy level. When the heat-pump
ceiling equals the physical maximum there is no upper band, the model is a pure
LP, and the heat pump is allowed everywhere.

Cutoff is applied at period start: a period whose starting energy is above the
heat-pump ceiling energy forces the binary off, so only the element may heat in
that interval.
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
type ThermalStoreOutputName = Literal[
    "thermal_store_energy",
    "thermal_store_power_element",
    "thermal_store_power_hp",
    "thermal_store_shortfall",
]
ELEMENT_TYPE: Final[ThermalStoreElementTypeName] = "thermal_store"
THERMAL_STORE_OUTPUT_NAMES: Final[frozenset[ThermalStoreOutputName]] = frozenset(
    (
        "thermal_store_energy",
        "thermal_store_power_element",
        "thermal_store_power_hp",
        "thermal_store_shortfall",
    )
)


class ThermalStoreElementConfig(TypedDict):
    """Loaded model inputs; period arrays have T entries, targets T+1."""

    element_type: ThermalStoreElementTypeName
    name: str
    heat_pump_connection: str
    element_connection: str
    capacity_per_degree: float
    initial_temperature: float
    reference_temperature: float
    maximum_temperature: float
    hp_ceiling_temperature: float
    loss_power: NDArray[np.float64]
    draw_energy: NDArray[np.float64]
    target_temperature: NDArray[np.float64]
    shortfall_price: NDArray[np.float64]
    hp_cop: NDArray[np.float64]
    hp_max_power: NDArray[np.float64]
    element_cop: NDArray[np.float64]
    element_max_power: NDArray[np.float64]


def thermal_store_arguments(config: ThermalStoreElementConfig, elements: Mapping[str, object], /) -> dict[str, object]:
    """Resolve the two electrical connections before building the thermal overlay."""
    heat_pump_connection = elements[config["heat_pump_connection"]]
    element_connection = elements[config["element_connection"]]
    if not isinstance(heat_pump_connection, Connection) or not isinstance(element_connection, Connection):
        msg = "Thermal store requires two electrical connections"
        raise TypeError(msg)
    return {
        **{
            key: value
            for key, value in config.items()
            if key not in ("element_type", "name", "heat_pump_connection", "element_connection")
        },
        "heat_pump_connection": heat_pump_connection,
        "element_connection": element_connection,
    }


class ThermalStore(Element[ThermalStoreOutputName]):
    """Two-stage thermal store: heat pump below a ceiling, element at any level.

    Reference temperature is the zero-energy datum, not a configurable comfort
    floor. The physical maximum is hard; targets are soft, including the terminal
    target. A constant draw forecast is prescribed thermal extraction, not a
    stratified tank or temperature-dependent flow model.
    """

    initial_temperature: TrackedParam[float] = TrackedParam()
    loss_power: TrackedParam[NDArray[np.float64]] = TrackedParam()
    draw_energy: TrackedParam[NDArray[np.float64]] = TrackedParam()
    target_temperature: TrackedParam[NDArray[np.float64]] = TrackedParam()
    shortfall_price: TrackedParam[NDArray[np.float64]] = TrackedParam()
    hp_cop: TrackedParam[NDArray[np.float64]] = TrackedParam()
    hp_max_power: TrackedParam[NDArray[np.float64]] = TrackedParam()
    element_cop: TrackedParam[NDArray[np.float64]] = TrackedParam()
    element_max_power: TrackedParam[NDArray[np.float64]] = TrackedParam()

    def __init__(
        self,
        name: str,
        periods: NDArray[np.float64],
        *,
        solver: Solver,
        heat_pump_connection: Connection[ConnectionOutputName],
        element_connection: Connection[ConnectionOutputName],
        capacity_per_degree: float,
        initial_temperature: float,
        reference_temperature: float,
        maximum_temperature: float,
        hp_ceiling_temperature: float,
        loss_power: NDArray[np.float64],
        draw_energy: NDArray[np.float64],
        target_temperature: NDArray[np.float64],
        shortfall_price: NDArray[np.float64],
        hp_cop: NDArray[np.float64],
        hp_max_power: NDArray[np.float64],
        element_cop: NDArray[np.float64],
        element_max_power: NDArray[np.float64],
    ) -> None:
        """Create boundary energy states attached to the two connection powers."""
        if (
            not np.isfinite(capacity_per_degree)
            or capacity_per_degree <= 0
            or not np.isfinite(reference_temperature)
            or not np.isfinite(maximum_temperature)
            or not np.isfinite(hp_ceiling_temperature)
            or not (reference_temperature < hp_ceiling_temperature <= maximum_temperature)
        ):
            msg = (
                "Thermal capacity must be positive and temperature bounds finite and ordered: "
                f"reference ({reference_temperature}) < ceiling ({hp_ceiling_temperature}) "
                f"<= maximum ({maximum_temperature})"
            )
            raise ValueError(msg)
        super().__init__(name, periods, solver=solver, output_names=THERMAL_STORE_OUTPUT_NAMES)
        self.heat_pump_connection = heat_pump_connection
        self.element_connection = element_connection
        self.capacity_per_degree = capacity_per_degree
        self.reference_temperature = reference_temperature
        self.initial_temperature = initial_temperature
        self.maximum_temperature = maximum_temperature
        self.hp_ceiling_temperature = hp_ceiling_temperature
        self.loss_power = loss_power
        self.draw_energy = draw_energy
        self.target_temperature = target_temperature
        self.shortfall_price = shortfall_price
        self.hp_cop = hp_cop
        self.hp_max_power = hp_max_power
        self.element_cop = element_cop
        self.element_max_power = element_max_power
        self.energy = solver.add_variables(
            self.n_periods + 1,
            name=f"{name}.energy",
            upper=capacity_per_degree * (maximum_temperature - reference_temperature),
        )
        self.shortfall = solver.add_variables(self.n_periods + 1, name=f"{name}.shortfall")
        # Energy at the heat-pump ceiling. An upper band above this creates binaries.
        self._ceiling_energy = capacity_per_degree * (hp_ceiling_temperature - reference_temperature)
        self._upper_band = capacity_per_degree * (maximum_temperature - hp_ceiling_temperature)
        self._has_upper_band = self._upper_band > 0.0
        self._heat_pump_binary: LinearArray | None = None
        if self._has_upper_band:
            self._heat_pump_binary = solver.add_binary_variables(self.n_periods, name=f"{name}.hp_enabled")

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
            ("hp_cop", self.hp_cop, self.n_periods, True),
            ("element_cop", self.element_cop, self.n_periods, True),
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
        for name, values, count, nonnegative in (
            ("hp_max_power", self.hp_max_power, self.n_periods, True),
            ("element_max_power", self.element_max_power, self.n_periods, True),
        ):
            if (
                values.shape != (count,)
                or not np.all(np.isfinite(values))
                or (np.any(values < 0) if nonnegative else np.any(values <= 0))
            ):
                msg = f"{name} must have {count} finite nonnegative values"
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
        """Conserve thermal energy; electrical powers are supplied by HAEO connections."""
        self.validate_inputs()
        hp_thermal = self.heat_pump_connection.total_power_out * self.hp_cop * self.periods
        element_thermal = self.element_connection.total_power_out * self.element_cop * self.periods
        return self.energy[1:] == (
            self.energy[:-1] + hp_thermal + element_thermal - self.loss_power * self.periods - self.draw_energy
        )

    @constraint
    def heat_pump_ceiling(self) -> Rows:
        """Force the heat-pump off when starting energy is above the ceiling.

        When there is no upper band this row is free and the heat pump is always
        allowed; the energy_maximum constraint already bounds the tank.
        """
        self.validate_inputs()
        if not self._has_upper_band or self._heat_pump_binary is None:
            return self.energy[:-1].free()
        return self.energy[:-1] <= self._ceiling_energy + self._upper_band * (1.0 - self._heat_pump_binary)

    @constraint
    def heat_pump_power_limit(self) -> Rows:
        """Cap heat-pump power by its binary on/off state."""
        self.validate_inputs()
        if not self._has_upper_band or self._heat_pump_binary is None:
            return self.heat_pump_connection.total_power_out <= self.hp_max_power
        return self.heat_pump_connection.total_power_out <= self.hp_max_power * self._heat_pump_binary

    @constraint
    def heat_pump_thermal_limit(self) -> Rows:
        """Prevent the heat pump from lifting energy above the ceiling in one interval."""
        self.validate_inputs()
        if not self._has_upper_band or self._heat_pump_binary is None:
            return (
                self.heat_pump_connection.total_power_out * self.hp_cop * self.periods
                <= self._ceiling_energy - self.energy[:-1] + self.loss_power * self.periods + self.draw_energy
            )
        return (
            self.heat_pump_connection.total_power_out * self.hp_cop * self.periods
            <= self._ceiling_energy
            - self.energy[:-1]
            + self.loss_power * self.periods
            + self.draw_energy
            + self._upper_band * (1.0 - self._heat_pump_binary)
        )

    @constraint
    def element_power_limit(self) -> Rows:
        """Cap element electrical power."""
        self.validate_inputs()
        return self.element_connection.total_power_out <= self.element_max_power

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
    def thermal_store_power_hp(self) -> OutputData:
        """Return heat-pump electrical power."""
        return OutputData(
            type=OutputType.POWER,
            unit="kW",
            values=self.extract_values(self.heat_pump_connection.total_power_out),
            direction="-",
        )

    @output
    def thermal_store_power_element(self) -> OutputData:
        """Return resistive element electrical power."""
        return OutputData(
            type=OutputType.POWER,
            unit="kW",
            values=self.extract_values(self.element_connection.total_power_out),
            direction="-",
        )

    @output
    def thermal_store_shortfall(self) -> OutputData:
        """Return thermal energy missing from readiness targets."""
        return OutputData(type=OutputType.ENERGY, unit="kWh", values=self.extract_values(self.shortfall))
