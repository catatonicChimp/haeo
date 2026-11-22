"""Shadow thermal-store configuration fixtures."""

from custom_components.haeo.core.schema import as_connection_target, as_constant_value, as_entity_value

VALID_DATA = [
    {
        "description": "Forecast-only tank with explicit synthetic parameters",
        "config": {
            "name": "Shadow tank",
            "connection": as_connection_target("switchboard"),
            "thermal": {
                "initial_temperature": as_entity_value(["sensor.tank_temperature"]),
                "target_temperature": as_constant_value(60.0),
                "maximum_temperature": as_constant_value(75.0),
                "capacity_per_degree": as_constant_value(0.31395),
                "cop": as_constant_value(3.0),
                "loss_power": as_constant_value(0.03),
                "draw_power": as_constant_value(0.2),
                "max_power": as_constant_value(0.8),
                "shortfall_price": as_constant_value(10.0),
            },
        },
    }
]
INVALID_DATA: list[dict[str, object]] = []
