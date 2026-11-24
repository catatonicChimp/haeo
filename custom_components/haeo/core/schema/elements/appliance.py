"""Appliance element schema definitions.

An appliance is an armed load that runs once inside its allowed hours, such as
a dishwasher or a washing machine. The user chooses the run's energy and its
length, the hours of the day it may run in, and the switch that arms it.
"""

from typing import Annotated, Final, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.schema import ConstantValue, EntityValue
from custom_components.haeo.core.schema.elements.element_type import ElementType
from custom_components.haeo.core.schema.field_hints import FieldHint, SectionHints, WindowHint
from custom_components.haeo.core.schema.sections import ConnectedCommonConfig, ConnectedCommonData

ELEMENT_TYPE = ElementType.APPLIANCE

# Section names
SECTION_SCHEDULE: Final = "schedule"
SECTION_WINDOW: Final = "window"

# Schedule section field names
CONF_ARMED: Final = "armed"
CONF_ENERGY: Final = "energy"
CONF_DURATION: Final = "duration"

# Window section field names
CONF_EARLIEST_START: Final = "earliest_start"
CONF_LATEST_FINISH: Final = "latest_finish"
# Per-period mask the two hour fields derive, not an input of its own
CONF_IN_WINDOW: Final = "in_window"

# One run's energy in kWh, pre-filled in the flow
DEFAULT_ENERGY: Final = 1.0
# One run's length in hours, pre-filled in the flow
DEFAULT_DURATION: Final = 2.0
# The whole day, so an appliance added without hours can run whenever it is cheapest
DEFAULT_EARLIEST_START: Final = 0.0
DEFAULT_LATEST_FINISH: Final = 24.0


class ScheduleConfig(TypedDict, total=False):
    """One run's arming, energy, and length.

    Every field has a default in the flow, so a stored config may omit any of
    them and the loader fills the default.
    """

    armed: EntityValue | ConstantValue
    energy: EntityValue | ConstantValue
    duration: EntityValue | ConstantValue


class ScheduleData(TypedDict):
    """Loaded run values; energy uses kWh and duration hours."""

    armed: bool
    energy: float
    duration: float


class WindowConfig(TypedDict, total=False):
    """The hours of the day the run may start and must finish in.

    Both bounds default to a full day, so a stored config may omit them.
    """

    earliest_start: ConstantValue
    latest_finish: ConstantValue


class WindowData(TypedDict):
    """Loaded window hours, and the per-period mask they derive."""

    earliest_start: float
    latest_finish: float
    in_window: NDArray[np.float64]


class ApplianceConfigSchema(ConnectedCommonConfig):
    """Appliance element configuration as stored in Home Assistant."""

    element_type: Literal[ElementType.APPLIANCE]
    schedule: Annotated[
        ScheduleConfig,
        SectionHints(
            {
                CONF_ARMED: FieldHint(
                    output_type=OutputType.STATUS,
                    time_series=False,
                    default_mode="value",
                    default_value=True,
                ),
                CONF_ENERGY: FieldHint(
                    output_type=OutputType.ENERGY,
                    min_value=0.0,
                    default_mode="value",
                    default_value=DEFAULT_ENERGY,
                ),
                CONF_DURATION: FieldHint(
                    output_type=OutputType.DURATION,
                    min_value=0.25,
                    step=0.25,
                    default_mode="value",
                    default_value=DEFAULT_DURATION,
                ),
            }
        ),
    ]
    window: Annotated[
        WindowConfig,
        SectionHints(
            {
                CONF_EARLIEST_START: FieldHint(
                    output_type=OutputType.DURATION,
                    min_value=0.0,
                    max_value=24.0,
                    step=1.0,
                    default_mode="value",
                    default_value=DEFAULT_EARLIEST_START,
                ),
                CONF_LATEST_FINISH: FieldHint(
                    output_type=OutputType.DURATION,
                    min_value=0.0,
                    max_value=24.0,
                    step=1.0,
                    default_mode="value",
                    default_value=DEFAULT_LATEST_FINISH,
                ),
            }
        ),
        WindowHint(earliest=CONF_EARLIEST_START, latest=CONF_LATEST_FINISH, target=CONF_IN_WINDOW),
    ]


class ApplianceConfigData(ConnectedCommonData):
    """Appliance element configuration with loaded values."""

    element_type: Literal[ElementType.APPLIANCE]
    schedule: ScheduleData
    window: WindowData


__all__ = [
    "CONF_ARMED",
    "CONF_DURATION",
    "CONF_EARLIEST_START",
    "CONF_ENERGY",
    "CONF_IN_WINDOW",
    "CONF_LATEST_FINISH",
    "DEFAULT_DURATION",
    "DEFAULT_EARLIEST_START",
    "DEFAULT_ENERGY",
    "DEFAULT_LATEST_FINISH",
    "ELEMENT_TYPE",
    "SECTION_SCHEDULE",
    "SECTION_WINDOW",
    "ApplianceConfigData",
    "ApplianceConfigSchema",
    "ScheduleConfig",
    "ScheduleData",
    "WindowConfig",
    "WindowData",
]
