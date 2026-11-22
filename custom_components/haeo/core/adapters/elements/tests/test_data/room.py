"""Room mappings add thermal constraints without an electrical sink."""

import numpy as np

from custom_components.haeo.core.model import OutputData, OutputType
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.room import RoomConfigData

from . import CreateCase, OutputsCase

DATA = RoomConfigData(
    name="Bedroom",
    element_type=ElementType.ROOM,
    connection=as_connection_target("AC"),
    room={
        "initial_temperature": 20.0,
        "outdoor_temperature": np.full(2, 15.0),
        "minimum_temperature": np.full(3, 18.0),
        "maximum_temperature": np.full(3, 25.0),
        "loss_rate": 0.03,
        "response": 0.5,
        "comfort_price": 5.0,
    },
)
CREATE_CASES: list[CreateCase] = [
    {
        "description": "Room has no independent power",
        "data": DATA,
        "model": [
            {
                "element_type": "room",
                "name": "Bedroom",
                "hvac": "AC:hvac",
                "initial_temperature": 20.0,
                "outdoor_temperature": [15.0, 15.0],
                "minimum_temperature": [18.0] * 3,
                "maximum_temperature": [25.0] * 3,
                "loss_rate": 0.03,
                "response": 0.5,
                "comfort_price": 5.0,
            }
        ],
    }
]
OUTPUTS_CASES: list[OutputsCase] = [
    {
        "description": "Room temperature and discomfort",
        "data": DATA,
        "periods": np.ones(2),
        "model_outputs": {
            "Bedroom": {
                "room_temperature": OutputData(type=OutputType.TEMPERATURE, unit="°C", values=(20.0, 20.0, 20.0)),
                "room_cold_shortfall": OutputData(type=OutputType.COEFFICIENT, unit="K", values=(0.0, 0.0, 0.0)),
                "room_hot_shortfall": OutputData(type=OutputType.COEFFICIENT, unit="K", values=(0.0, 0.0, 0.0)),
            }
        },
        "outputs": {
            ElementType.ROOM: {
                "room_temperature": OutputData(type=OutputType.TEMPERATURE, unit="°C", values=(20.0, 20.0, 20.0)),
                "room_cold_shortfall": OutputData(type=OutputType.COEFFICIENT, unit="K", values=(0.0, 0.0, 0.0)),
                "room_hot_shortfall": OutputData(type=OutputType.COEFFICIENT, unit="K", values=(0.0, 0.0, 0.0)),
            }
        },
    }
]
