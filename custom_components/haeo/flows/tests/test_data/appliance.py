"""Test appliance config flow data for the choose selector approach."""

from custom_components.haeo.core.const import CONF_NAME
from custom_components.haeo.core.schema import as_connection_target, as_constant_value, as_entity_value
from custom_components.haeo.core.schema.elements.appliance import (
    CONF_ARMED,
    CONF_DURATION,
    CONF_EARLIEST_START,
    CONF_ENERGY,
    CONF_LATEST_FINISH,
    SECTION_SCHEDULE,
    SECTION_WINDOW,
)
from custom_components.haeo.core.schema.sections import CONF_CONNECTION

VALID_DATA = [
    {
        "description": "Dishwasher armed by a switch, running an evening block",
        "config": {
            CONF_NAME: "Dishwasher",
            CONF_CONNECTION: as_connection_target("switchboard"),
            SECTION_SCHEDULE: {
                CONF_ARMED: as_entity_value(["switch.dishwasher"]),
                CONF_ENERGY: as_constant_value(1.2),
                CONF_DURATION: as_constant_value(2.0),
            },
            SECTION_WINDOW: {
                CONF_EARLIEST_START: as_constant_value(18.0),
                CONF_LATEST_FINISH: as_constant_value(7.0),
            },
        },
    },
    {
        "description": "Minimal appliance - defaults for energy, duration, and a full-day window",
        "config": {
            CONF_NAME: "Washing Machine",
            CONF_CONNECTION: as_connection_target("switchboard"),
            SECTION_SCHEDULE: {
                CONF_ARMED: as_entity_value(["input_boolean.washing_machine"]),
            },
            SECTION_WINDOW: {
                CONF_EARLIEST_START: as_constant_value(0.0),
                CONF_LATEST_FINISH: as_constant_value(24.0),
            },
        },
    },
]

INVALID_DATA: list[dict[str, object]] = []
