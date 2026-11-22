"""Per-room observation and comfort inputs attached to shared HVAC."""

from typing import Annotated, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.schema import ConstantValue, EntityValue
from custom_components.haeo.core.schema.elements.element_type import ElementType
from custom_components.haeo.core.schema.field_hints import FieldHint, SectionHints
from custom_components.haeo.core.schema.sections import ConnectedCommonConfig, ConnectedCommonData


class RoomInputs(TypedDict):
    """Measured temperature, ambient forecast and explicit provisional dynamics."""

    initial_temperature: ConstantValue | EntityValue
    outdoor_temperature: ConstantValue | EntityValue
    minimum_temperature: ConstantValue | EntityValue
    maximum_temperature: ConstantValue | EntityValue
    loss_rate: ConstantValue | EntityValue
    response: ConstantValue | EntityValue
    comfort_price: ConstantValue | EntityValue


class RoomData(TypedDict):
    """Loaded room dynamics and comfort bands."""

    initial_temperature: float
    outdoor_temperature: NDArray[np.float64]
    minimum_temperature: NDArray[np.float64]
    maximum_temperature: NDArray[np.float64]
    loss_rate: float
    response: float
    comfort_price: float


class RoomConfigSchema(ConnectedCommonConfig):
    """Connection identifies shared HVAC, not a switchboard or separate zone."""

    element_type: Literal[ElementType.ROOM]
    room: Annotated[
        RoomInputs,
        SectionHints(
            {
                "initial_temperature": FieldHint(output_type=OutputType.TEMPERATURE),
                "outdoor_temperature": FieldHint(output_type=OutputType.TEMPERATURE, time_series=True),
                "minimum_temperature": FieldHint(output_type=OutputType.TEMPERATURE, time_series=True, boundaries=True),
                "maximum_temperature": FieldHint(output_type=OutputType.TEMPERATURE, time_series=True, boundaries=True),
                "loss_rate": FieldHint(output_type=OutputType.COEFFICIENT, min_value=0),
                "response": FieldHint(output_type=OutputType.COEFFICIENT, min_value=0.001),
                "comfort_price": FieldHint(output_type=OutputType.COEFFICIENT, min_value=0.001),
            }
        ),
    ]


class RoomConfigData(ConnectedCommonData):
    """Loaded room input values."""

    element_type: Literal[ElementType.ROOM]
    room: RoomData
