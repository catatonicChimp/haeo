"""Pure config transformation logic for the v1.7 migration.

A legacy single-stage thermal store becomes a two-stage store. The old heat-pump
COP and maximum electrical power move to the heat-pump section, the old maximum
temperature becomes the heat-pump ceiling, and a disabled resistive element
section is added. Every other field stays where it is.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from custom_components.haeo.core.const import CONF_ELEMENT_TYPE
from custom_components.haeo.core.schema import as_constant_value, is_none_value
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.thermal_store import (
    CONF_ELEMENT_COP,
    CONF_ELEMENT_MAX_POWER,
    CONF_HP_CEILING_TEMPERATURE,
    CONF_HP_COP,
    CONF_HP_MAX_POWER,
    SECTION_ELEMENT,
    SECTION_HEAT_PUMP,
    SECTION_THERMAL,
)
from custom_components.haeo.core.schema.migrations import section_dict

# The config entry minor version these migrations bring an entry to
MINOR_VERSION: Final = 7


def migrate_element_config(config: Mapping[str, object]) -> dict[str, object] | None:
    """Return a two-stage thermal store config, or None for other element types."""
    if config.get(CONF_ELEMENT_TYPE) != ElementType.THERMAL_STORE:
        return None

    thermal = section_dict(config, SECTION_THERMAL)
    heat_pump: dict[str, object] = {}
    element: dict[str, object] = {}

    # Old single-stage values become heat-pump values
    old_cop = thermal.get("cop")
    old_max_power = thermal.get("max_power")
    old_maximum_temperature = thermal.get("maximum_temperature")

    if old_cop is not None and not is_none_value(old_cop):
        heat_pump[CONF_HP_COP] = old_cop
    if old_max_power is not None and not is_none_value(old_max_power):
        heat_pump[CONF_HP_MAX_POWER] = old_max_power
    if old_maximum_temperature is not None and not is_none_value(old_maximum_temperature):
        heat_pump[CONF_HP_CEILING_TEMPERATURE] = old_maximum_temperature

    # Element stage is disabled by default; COP is a dimensionless ratio
    element[CONF_ELEMENT_MAX_POWER] = as_constant_value(0.0)
    element[CONF_ELEMENT_COP] = as_constant_value(1.0)

    new_thermal = {key: value for key, value in thermal.items() if key not in ("cop", "max_power")}

    return {
        **config,
        SECTION_THERMAL: new_thermal,
        SECTION_HEAT_PUMP: heat_pump,
        SECTION_ELEMENT: element,
    }
