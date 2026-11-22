"""Room observer configuration fixtures."""

from custom_components.haeo.core.schema import as_connection_target, as_constant_value

VALID_DATA = [
    {
        "description": "One room attached to a shared HVAC appliance",
        "config": {
            "name": "Bedroom",
            "connection": as_connection_target("Aircon"),
            "room": {
                key: as_constant_value(value)
                for key, value in {
                    "initial_temperature": 20.0,
                    "outdoor_temperature": 15.0,
                    "minimum_temperature": 18.0,
                    "maximum_temperature": 25.0,
                    "loss_rate": 0.03,
                    "response": 0.5,
                    "comfort_price": 5.0,
                }.items()
            },
        },
    }
]
INVALID_DATA: list[dict[str, object]] = []
