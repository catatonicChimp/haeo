"""Shared unzoned HVAC electrical input and externally selected mode."""

from typing import Annotated, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.schema import ConstantValue, EntityValue
from custom_components.haeo.core.schema.elements.element_type import ElementType
from custom_components.haeo.core.schema.field_hints import FieldHint, SectionHints
from custom_components.haeo.core.schema.sections import ConnectedCommonConfig, ConnectedCommonData


class HvacInputs(TypedDict):
    """Mode uses -1 cooling, 0 idle, 1 heating; no simultaneous modes."""

    mode: ConstantValue | EntityValue
    max_power: ConstantValue | EntityValue


class HvacData(TypedDict):
    """Loaded shared input."""

    mode: float
    max_power: NDArray[np.float64]


class HvacConfigSchema(ConnectedCommonConfig):
    """User-configured shared appliance model."""

    element_type: Literal[ElementType.HVAC]
    hvac: Annotated[
        HvacInputs,
        SectionHints(
            {
                "mode": FieldHint(output_type=OutputType.COEFFICIENT, min_value=-1, max_value=1, step=1),
                "max_power": FieldHint(output_type=OutputType.POWER_LIMIT, time_series=True),
            }
        ),
    ]


class HvacConfigData(ConnectedCommonData):
    """Loaded appliance values."""

    element_type: Literal[ElementType.HVAC]
    hvac: HvacData
