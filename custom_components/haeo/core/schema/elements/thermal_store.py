"""Experimental thermal-store inputs for a dedicated shadow hub."""

from typing import Annotated, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.schema import ConstantValue, EntityValue
from custom_components.haeo.core.schema.elements.element_type import ElementType
from custom_components.haeo.core.schema.field_hints import FieldHint, SectionHints
from custom_components.haeo.core.schema.sections import ConnectedCommonConfig, ConnectedCommonData


class ThermalConfig(TypedDict):
    """Stored input selectors; all parameters explicitly configured."""

    initial_temperature: EntityValue | ConstantValue
    target_temperature: EntityValue | ConstantValue
    maximum_temperature: ConstantValue
    capacity_per_degree: ConstantValue
    cop: EntityValue | ConstantValue
    loss_power: EntityValue | ConstantValue
    draw_power: EntityValue | ConstantValue
    max_power: EntityValue | ConstantValue
    shortfall_price: EntityValue | ConstantValue


class ThermalData(TypedDict):
    """Loaded values; thermal capacity uses kWh/K, power uses kW."""

    initial_temperature: float
    target_temperature: NDArray[np.float64]
    maximum_temperature: float
    capacity_per_degree: float
    cop: NDArray[np.float64]
    loss_power: NDArray[np.float64]
    draw_power: NDArray[np.float64]
    max_power: NDArray[np.float64]
    shortfall_price: NDArray[np.float64]


class ThermalStoreConfigSchema(ConnectedCommonConfig):
    """Thermal store modeled as a load, with no actuator configuration."""

    element_type: Literal[ElementType.THERMAL_STORE]
    thermal: Annotated[
        ThermalConfig,
        SectionHints(
            {
                "initial_temperature": FieldHint(output_type=OutputType.TEMPERATURE),
                "target_temperature": FieldHint(output_type=OutputType.TEMPERATURE, time_series=True, boundaries=True),
                "maximum_temperature": FieldHint(output_type=OutputType.TEMPERATURE),
                "capacity_per_degree": FieldHint(output_type=OutputType.COEFFICIENT, min_value=0.0001),
                "cop": FieldHint(output_type=OutputType.COEFFICIENT, min_value=0.01, time_series=True),
                "loss_power": FieldHint(output_type=OutputType.POWER, time_series=True),
                "draw_power": FieldHint(output_type=OutputType.POWER, time_series=True),
                "max_power": FieldHint(output_type=OutputType.POWER_LIMIT, time_series=True),
                "shortfall_price": FieldHint(
                    output_type=OutputType.PRICE, min_value=0.001, time_series=True, boundaries=True
                ),
            }
        ),
    ]


class ThermalStoreConfigData(ConnectedCommonData):
    """Thermal configuration after loading input sources."""

    element_type: Literal[ElementType.THERMAL_STORE]
    thermal: ThermalData
