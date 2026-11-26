"""Experimental thermal-store inputs for a dedicated shadow hub."""

from typing import Annotated, Final, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.schema import ConstantValue, EntityValue
from custom_components.haeo.core.schema.elements.element_type import ElementType
from custom_components.haeo.core.schema.field_hints import FieldHint, SectionHints
from custom_components.haeo.core.schema.sections import ConnectedCommonConfig, ConnectedCommonData

SECTION_THERMAL: Final = "thermal"
SECTION_HEAT_PUMP: Final = "heat_pump"
SECTION_ELEMENT: Final = "element"

CONF_HP_CEILING_TEMPERATURE: Final = "hp_ceiling_temperature"
CONF_HP_MAX_POWER: Final = "hp_max_power"
CONF_HP_COP: Final = "hp_cop"
CONF_ELEMENT_MAX_POWER: Final = "element_max_power"
CONF_ELEMENT_COP: Final = "element_cop"

DEFAULT_TARGET_TEMPERATURE: Final = 60.0
DEFAULT_MAXIMUM_TEMPERATURE: Final = 75.0
DEFAULT_CAPACITY_PER_DEGREE: Final = 0.314
DEFAULT_LOSS_POWER: Final = 0.12
DEFAULT_DRAW_POWER: Final = 0.2
DEFAULT_HP_CEILING_TEMPERATURE: Final = 65.0
DEFAULT_HP_MAX_POWER: Final = 0.8
DEFAULT_HP_COP: Final = 3.0
DEFAULT_ELEMENT_MAX_POWER: Final = 0.8
DEFAULT_ELEMENT_COP: Final = 1.0


class ThermalConfig(TypedDict):
    """Stored thermal inputs for the physical tank and comfort target."""

    initial_temperature: EntityValue | ConstantValue
    target_temperature: EntityValue | ConstantValue
    maximum_temperature: ConstantValue
    capacity_per_degree: ConstantValue
    loss_power: EntityValue | ConstantValue
    draw_power: EntityValue | ConstantValue
    shortfall_price: EntityValue | ConstantValue


class HeatPumpConfig(TypedDict):
    """Stored inputs for the heat-pump heating stage."""

    hp_ceiling_temperature: ConstantValue
    hp_max_power: EntityValue | ConstantValue
    hp_cop: EntityValue | ConstantValue


class ElementConfig(TypedDict):
    """Stored inputs for the resistive element heating stage."""

    element_max_power: EntityValue | ConstantValue
    element_cop: EntityValue | ConstantValue


class ThermalData(TypedDict):
    """Loaded thermal values; capacity uses kWh/K, power uses kW."""

    initial_temperature: float
    target_temperature: NDArray[np.float64]
    maximum_temperature: float
    capacity_per_degree: float
    loss_power: NDArray[np.float64]
    draw_power: NDArray[np.float64]
    shortfall_price: NDArray[np.float64]


class HeatPumpData(TypedDict):
    """Loaded heat-pump stage values."""

    hp_ceiling_temperature: float
    hp_max_power: NDArray[np.float64]
    hp_cop: NDArray[np.float64]


class ElementData(TypedDict):
    """Loaded resistive element values."""

    element_max_power: NDArray[np.float64]
    element_cop: NDArray[np.float64]


class ThermalStoreConfigSchema(ConnectedCommonConfig):
    """Thermal store with two heating stages and a heat-pump ceiling."""

    element_type: Literal[ElementType.THERMAL_STORE]
    thermal: Annotated[
        ThermalConfig,
        SectionHints(
            {
                "initial_temperature": FieldHint(output_type=OutputType.TEMPERATURE),
                "target_temperature": FieldHint(output_type=OutputType.TEMPERATURE, time_series=True, boundaries=True),
                "maximum_temperature": FieldHint(
                    output_type=OutputType.TEMPERATURE, default_mode="value", default_value=DEFAULT_MAXIMUM_TEMPERATURE
                ),
                "capacity_per_degree": FieldHint(
                    output_type=OutputType.COEFFICIENT,
                    min_value=0.0001,
                    default_mode="value",
                    default_value=DEFAULT_CAPACITY_PER_DEGREE,
                ),
                "loss_power": FieldHint(
                    output_type=OutputType.POWER,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_LOSS_POWER,
                ),
                "draw_power": FieldHint(
                    output_type=OutputType.POWER,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_DRAW_POWER,
                ),
                "shortfall_price": FieldHint(
                    output_type=OutputType.PRICE,
                    min_value=0.001,
                    time_series=True,
                    boundaries=True,
                    default_mode="value",
                    default_value=10.0,
                ),
            }
        ),
    ]
    heat_pump: Annotated[
        HeatPumpConfig,
        SectionHints(
            {
                CONF_HP_CEILING_TEMPERATURE: FieldHint(
                    output_type=OutputType.TEMPERATURE,
                    default_mode="value",
                    default_value=DEFAULT_HP_CEILING_TEMPERATURE,
                ),
                CONF_HP_MAX_POWER: FieldHint(
                    output_type=OutputType.POWER_LIMIT,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_HP_MAX_POWER,
                ),
                CONF_HP_COP: FieldHint(
                    output_type=OutputType.COEFFICIENT,
                    min_value=0.01,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_HP_COP,
                ),
            }
        ),
    ]
    element: Annotated[
        ElementConfig,
        SectionHints(
            {
                CONF_ELEMENT_MAX_POWER: FieldHint(
                    output_type=OutputType.POWER_LIMIT,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_ELEMENT_MAX_POWER,
                ),
                CONF_ELEMENT_COP: FieldHint(
                    output_type=OutputType.COEFFICIENT,
                    min_value=0.01,
                    time_series=True,
                    default_mode="value",
                    default_value=DEFAULT_ELEMENT_COP,
                ),
            }
        ),
    ]


class ThermalStoreConfigData(ConnectedCommonData):
    """Thermal configuration after loading input sources."""

    element_type: Literal[ElementType.THERMAL_STORE]
    thermal: ThermalData
    heat_pump: HeatPumpData
    element: ElementData
