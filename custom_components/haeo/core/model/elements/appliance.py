"""Appliance element for an armed load that runs one contiguous block.

An appliance is a load that consumes a fixed amount of energy in a single
uninterrupted run of fixed length: a dishwasher, a washing machine, a tumble
dryer. An external switch arms it. While armed, the plan must deliver the run's
energy inside the allowed hours of the day; while disarmed, the appliance
consumes nothing and has no planned start.

This is the continuous relaxation. Power may fill any allowed periods up to
``energy / duration``, so the optimization is free to spread the run across the
window and the model stays a linear program. The adapter then commits the
cheapest single contiguous block of the run length that the plan can cover,
which is what an actuator can follow; this element only reports the relaxed
power it was asked for.

Window hours are hours of the day. A window that starts later than it finishes
runs overnight, and equal bounds cover the whole day. A period lies inside the
window by the hour it starts at.

Energy the window cannot deliver is shortfall, priced high enough that the
optimizer always runs an armed appliance when the window allows it, and finite
so an impossible run leaves the optimization feasible and reports the miss
rather than failing the solve.
"""

from typing import Final, Literal, NotRequired, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.model.element import ELEMENT_POWER_BALANCE, NetworkElement
from custom_components.haeo.core.model.linear import LinearArray, Rows
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.model.reactive import TrackedParam, computed, constraint, cost, output
from custom_components.haeo.core.model.solver import Solver

# Model element type for appliances
ELEMENT_TYPE: Final = "appliance"
type ApplianceElementTypeName = Literal["appliance"]

# Constraint names the element exposes as shadow prices
type ApplianceConstraintName = Literal["element_power_balance"]

# All appliance output names (the relaxed power plus the power balance price)
type ApplianceOutputName = Literal["appliance_power"] | ApplianceConstraintName

APPLIANCE_OUTPUT_NAMES: Final[frozenset[ApplianceOutputName]] = frozenset(
    (
        APPLIANCE_POWER := "appliance_power",
        APPLIANCE_POWER_BALANCE := ELEMENT_POWER_BALANCE,
    )
)

# Price of each kWh the window cannot deliver. It is far above any real energy
# price, so an armed appliance runs whenever the window physically allows it,
# and finite, so an impossible window leaves the optimization feasible.
SHORTFALL_PRICE: Final = 100.0


class ApplianceElementConfig(TypedDict):
    """Configuration for Appliance model elements."""

    element_type: ApplianceElementTypeName
    name: str
    in_window: NDArray[np.float64]
    energy: float
    duration: float
    armed: bool
    is_source: Literal[False]
    is_sink: Literal[True]
    inbound_tags: NotRequired[set[int] | None]


class Appliance(NetworkElement[ApplianceOutputName]):
    """An armed load that must receive one run's energy inside its allowed hours.

    ``in_window`` is 1 in each period whose start hour lies inside the allowed
    window and 0 elsewhere. ``energy`` is the energy one run takes in kWh and
    ``duration`` its length in hours, so a period draws at most
    ``energy / duration`` kW. ``armed`` decides whether the run is required at
    all.

    Power is never negative and is zero outside the window and while disarmed.
    The energy of the whole horizon plus any shortfall equals the run's energy,
    so the run fits the window or the shortfall reports how much of it does not.
    """

    in_window: TrackedParam[NDArray[np.float64]] = TrackedParam()
    energy: TrackedParam[float] = TrackedParam()
    duration: TrackedParam[float] = TrackedParam()
    armed: TrackedParam[bool] = TrackedParam()

    def __init__(
        self,
        name: str,
        periods: NDArray[np.float64],
        *,
        solver: Solver,
        in_window: NDArray[np.float64],
        energy: float,
        duration: float,
        armed: bool,
        is_source: Literal[False] = False,
        is_sink: Literal[True] = True,
        inbound_tags: set[int] | None = None,
    ) -> None:
        """Initialize an appliance.

        An appliance only consumes, which ``is_source`` and ``is_sink`` declare
        for policy compilation and buffer roles.
        """
        if duration <= 0.0:
            msg = "An appliance needs a positive run duration"
            raise ValueError(msg)
        if energy < 0.0:
            msg = "An appliance cannot require negative energy"
            raise ValueError(msg)
        super().__init__(
            name=name,
            periods=periods,
            solver=solver,
            output_names=APPLIANCE_OUTPUT_NAMES,
            is_source=is_source,
            is_sink=is_sink,
            inbound_tags=inbound_tags,
        )
        if len(in_window) != self.n_periods:
            msg = f"An appliance needs one window value per period, got {len(in_window)} for {self.n_periods}"
            raise ValueError(msg)

        self.in_window = in_window
        self.energy = energy
        self.duration = duration
        self.armed = armed

        # Power drawn from the network in each period, bounded by the constraints below
        self.power = solver.add_variables(self.n_periods, name=f"{name}.power")
        # Energy the window could not deliver, in total over the horizon
        self.shortfall = solver.add_variables(1, name=f"{name}.shortfall")

    @computed
    def max_power(self) -> float:
        """Return the power that delivers the run's energy over its duration."""
        return self.energy / self.duration

    @computed
    def required_energy(self) -> float:
        """Return the energy the plan must deliver, zero while the appliance is disarmed."""
        return self.energy if self.armed else 0.0

    @constraint
    def appliance_power_limit(self) -> Rows:
        """Constraint: a period draws at most the run's power, only inside the window, only while armed."""
        available = self.in_window * (1.0 if self.armed else 0.0)
        return self.power <= self.max_power() * available

    @constraint
    def appliance_energy(self) -> Rows:
        """Constraint: the run's energy is delivered inside the horizon, or reported as shortfall."""
        return (self.power * self.periods).total() + self.shortfall.total() == self.required_energy()

    @cost
    def appliance_shortfall_cost(self) -> LinearArray:
        """Cost: each kWh the window cannot deliver, priced high enough to run whenever possible."""
        return SHORTFALL_PRICE * self.shortfall.total()

    def element_power_produced(self) -> LinearArray | None:
        """Appliances never produce power."""
        return None

    def element_power_consumed(self) -> LinearArray:
        """Return power absorbed from the network."""
        return self.power

    @output
    def appliance_power(self) -> OutputData:
        """Output: relaxed power the appliance draws in each period."""
        return OutputData(type=OutputType.POWER, unit="kW", values=self.extract_values(self.power), direction="-")
