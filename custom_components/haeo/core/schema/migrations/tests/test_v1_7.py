"""Tests for the v1.7 pure schema migration."""

from custom_components.haeo.core.const import CONF_ELEMENT_TYPE
from custom_components.haeo.core.schema import as_constant_value, as_entity_value
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
from custom_components.haeo.core.schema.migrations.v1_7 import migrate_element_config


def _single_stage_config() -> dict[str, object]:
    return {
        CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
        "name": "Tank",
        SECTION_THERMAL: {
            "initial_temperature": as_entity_value(["sensor.tank_temp"]),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.314),
            "cop": as_constant_value(3.0),
            "loss_power": as_constant_value(0.12),
            "draw_power": as_constant_value(0.2),
            "max_power": as_constant_value(0.8),
            "shortfall_price": as_constant_value(10.0),
        },
    }


def test_migrate_element_config_turns_single_stage_into_two_stage() -> None:
    """A legacy single-stage thermal store gets heat_pump and element sections."""
    result = migrate_element_config(_single_stage_config())
    assert result is not None

    thermal = result[SECTION_THERMAL]
    heat_pump = result[SECTION_HEAT_PUMP]
    element = result[SECTION_ELEMENT]
    assert isinstance(thermal, dict)
    assert isinstance(heat_pump, dict)
    assert isinstance(element, dict)

    assert "cop" not in thermal
    assert "max_power" not in thermal
    assert heat_pump[CONF_HP_COP] == as_constant_value(3.0)
    assert heat_pump[CONF_HP_MAX_POWER] == as_constant_value(0.8)
    assert heat_pump[CONF_HP_CEILING_TEMPERATURE] == as_constant_value(75.0)
    assert element[CONF_ELEMENT_MAX_POWER] == as_constant_value(0.0)
    assert element[CONF_ELEMENT_COP] == as_constant_value(1.0)


def test_migrate_element_config_is_idempotent() -> None:
    """Applying the pure transformation twice gives the same result as once."""
    first = migrate_element_config(_single_stage_config())
    assert first is not None
    second = migrate_element_config(first)
    assert second is not None
    assert first == second


def test_migrate_element_config_preserves_already_migrated_config() -> None:
    """An already-migrated thermal store passes through unchanged."""
    already_migrated = {
        CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
        "name": "Tank",
        SECTION_THERMAL: {
            "initial_temperature": as_entity_value(["sensor.tank_temp"]),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.314),
            "loss_power": as_constant_value(0.12),
            "draw_power": as_constant_value(0.2),
            "shortfall_price": as_constant_value(10.0),
        },
        SECTION_HEAT_PUMP: {
            CONF_HP_CEILING_TEMPERATURE: as_constant_value(65.0),
            CONF_HP_MAX_POWER: as_constant_value(1.2),
            CONF_HP_COP: as_constant_value(3.5),
        },
        SECTION_ELEMENT: {
            CONF_ELEMENT_MAX_POWER: as_constant_value(0.8),
            CONF_ELEMENT_COP: as_constant_value(1.0),
        },
    }

    result = migrate_element_config(already_migrated)
    assert result == already_migrated


def test_migrate_element_config_ignores_non_thermal_elements() -> None:
    """Other element types are not migrated."""
    assert migrate_element_config({CONF_ELEMENT_TYPE: ElementType.BATTERY, "name": "Battery"}) is None
