"""Shadow two-stage thermal-store configuration fixtures."""

from custom_components.haeo.core.schema import as_connection_target, as_constant_value, as_entity_value

VALID_DATA = [
    {
        "description": "Forecast-only two-stage tank with explicit synthetic parameters",
        "config": {
            "name": "Shadow tank",
            "connection": as_connection_target("switchboard"),
            "thermal": {
                "initial_temperature": as_entity_value(["sensor.tank_temperature"]),
                "target_temperature": as_constant_value(60.0),
                "maximum_temperature": as_constant_value(75.0),
                "capacity_per_degree": as_constant_value(0.31395),
                "loss_power": as_constant_value(0.12),
                "draw_power": as_constant_value(0.2),
                "shortfall_price": as_constant_value(10.0),
            },
            "heat_pump": {
                "hp_ceiling_temperature": as_constant_value(65.0),
                "hp_max_power": as_constant_value(0.8),
                "hp_cop": as_constant_value(3.0),
            },
            "element": {
                "element_max_power": as_constant_value(0.8),
                "element_cop": as_constant_value(1.0),
            },
        },
    }
]
INVALID_DATA: list[dict[str, object]] = [
    {
        "description": "Heat-pump ceiling above physical maximum is rejected",
        "config": {
            "name": "Bad ceiling",
            "connection": as_connection_target("switchboard"),
            "thermal": {
                "initial_temperature": as_constant_value(50.0),
                "target_temperature": as_constant_value(60.0),
                "maximum_temperature": as_constant_value(65.0),
                "capacity_per_degree": as_constant_value(0.1),
                "loss_power": as_constant_value(0.0),
                "draw_power": as_constant_value(0.0),
                "shortfall_price": as_constant_value(10.0),
            },
            "heat_pump": {
                "hp_ceiling_temperature": as_constant_value(70.0),
                "hp_max_power": as_constant_value(0.8),
                "hp_cop": as_constant_value(3.0),
            },
            "element": {
                "element_max_power": as_constant_value(0.8),
                "element_cop": as_constant_value(1.0),
            },
        },
        "error": "invalid_ceiling",
    }
]
