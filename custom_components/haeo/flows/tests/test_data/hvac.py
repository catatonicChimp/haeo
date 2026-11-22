"""Shared HVAC configuration fixtures."""

from custom_components.haeo.core.schema import as_connection_target, as_constant_value

VALID_DATA = [
    {
        "description": "Unzoned HVAC",
        "config": {
            "name": "Aircon",
            "connection": as_connection_target("switchboard"),
            "hvac": {"mode": as_constant_value(1), "max_power": as_constant_value(4.5)},
        },
    }
]
INVALID_DATA: list[dict[str, object]] = []
