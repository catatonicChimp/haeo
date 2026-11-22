"""Shared HVAC mappings have only one electrical connection."""

import numpy as np

from custom_components.haeo.core.model import OutputData, OutputType
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.hvac import HvacConfigData

from . import CreateCase, OutputsCase

DATA = HvacConfigData(
    name="AC",
    element_type=ElementType.HVAC,
    connection=as_connection_target("bus"),
    hvac={"mode": 1.0, "max_power": np.full(2, 4.5)},
)
CREATE_CASES: list[CreateCase] = [
    {
        "description": "Single whole-house actuator",
        "data": DATA,
        "model": [
            {"element_type": "node", "name": "AC", "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": "AC:connection",
                "source": "bus",
                "target": "AC",
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": [4.5, 4.5]}},
            },
            {"element_type": "hvac", "name": "AC:hvac", "connection": "AC:connection", "mode": 1.0},
        ],
    }
]
OUTPUTS_CASES: list[OutputsCase] = [
    {
        "description": "Shared demand output",
        "data": DATA,
        "periods": np.ones(2),
        "model_outputs": {
            "AC:connection": {
                "connection_power": OutputData(type=OutputType.POWER_FLOW, unit="kW", values=(1.0, 2.0), direction="+")
            }
        },
        "outputs": {
            ElementType.HVAC: {
                "hvac_power": OutputData(type=OutputType.POWER, unit="kW", values=(1.0, 2.0), direction="-")
            }
        },
    }
]
