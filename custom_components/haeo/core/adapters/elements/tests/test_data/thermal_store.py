"""Thermal adapter fixtures with independently specified expected mappings."""

import numpy as np

from custom_components.haeo.core.model import OutputData, OutputType
from custom_components.haeo.core.schema import as_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData

from . import CreateCase, OutputsCase

DATA = ThermalStoreConfigData(
    name="tank",
    element_type=ElementType.THERMAL_STORE,
    connection=as_connection_target("bus"),
    thermal={
        "initial_temperature": 50.0,
        "target_temperature": np.full(3, 60.0),
        "maximum_temperature": 75.0,
        "capacity_per_degree": 0.1,
        "cop": np.full(2, 2.0),
        "loss_power": np.full(2, 0.03),
        "draw_power": np.full(2, 0.2),
        "max_power": np.full(2, 0.8),
        "shortfall_price": np.full(3, 10.0),
    },
)
CREATE_CASES: list[CreateCase] = [
    {
        "description": "Thermal load converts draw rate into a duration-scaled heat withdrawal",
        "data": DATA,
        "model": [
            {"element_type": "node", "name": "tank", "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": "tank:connection",
                "source": "bus",
                "target": "tank",
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": [0.8, 0.8]}},
            },
            {
                "element_type": "thermal_store",
                "name": "tank:thermal",
                "connection": "tank:connection",
                "initial_temperature": 50.0,
                "target_temperature": [60.0] * 3,
                "maximum_temperature": 75.0,
                "capacity_per_degree": 0.1,
                "reference_temperature": 0.0,
                "cop": [2.0] * 2,
                "loss_power": [0.23] * 2,
                "draw_energy": [0.0] * 2,
                "shortfall_price": [10.0] * 3,
            },
        ],
    }
]
OUTPUTS_CASES: list[OutputsCase] = [
    {
        "description": "Thermal energy maps to C with forecast-only power and deficit",
        "data": DATA,
        "periods": np.ones(2),
        "model_outputs": {
            "tank:thermal": {
                "thermal_store_energy": OutputData(type=OutputType.ENERGY, unit="kWh", values=(5.0, 6.0, 6.0)),
                "thermal_store_shortfall": OutputData(type=OutputType.ENERGY, unit="kWh", values=(1.0, 0.0, 0.0)),
            },
            "tank:connection": {
                "connection_power": OutputData(type=OutputType.POWER_FLOW, unit="kW", values=(0.5, 0.0), direction="+")
            },
        },
        "outputs": {
            ElementType.THERMAL_STORE: {
                "thermal_store_temperature": OutputData(
                    type=OutputType.TEMPERATURE, unit="°C", values=(50.0, 60.0, 60.0)
                ),
                "thermal_store_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.5, 0.0), direction="-"),
                "thermal_store_shortfall": OutputData(type=OutputType.ENERGY, unit="kWh", values=(1.0, 0.0, 0.0)),
            }
        },
    }
]
