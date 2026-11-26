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
        "target_temperature": np.array([60.0, 60.0, 60.0]),
        "maximum_temperature": 75.0,
        "capacity_per_degree": 0.1,
        "loss_power": np.array([0.03, 0.03]),
        "draw_power": np.array([0.2, 0.2]),
        "shortfall_price": np.array([10.0, 10.0, 10.0]),
    },
    heat_pump={
        "hp_ceiling_temperature": 65.0,
        "hp_max_power": np.array([0.8, 0.8]),
        "hp_cop": np.array([3.0, 3.0]),
    },
    element={
        "element_max_power": np.array([0.8, 0.8]),
        "element_cop": np.array([1.0, 1.0]),
    },
)
CREATE_CASES: list[CreateCase] = [
    {
        "description": "Two-stage thermal store creates two connections and a thermal overlay",
        "data": DATA,
        "model": [
            {"element_type": "node", "name": "tank", "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": "tank:heat_pump",
                "source": "bus",
                "target": "tank",
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": [0.8, 0.8]}},
            },
            {
                "element_type": "connection",
                "name": "tank:element",
                "source": "bus",
                "target": "tank",
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": [0.8, 0.8]}},
            },
            {
                "element_type": "thermal_store",
                "name": "tank:thermal",
                "heat_pump_connection": "tank:heat_pump",
                "element_connection": "tank:element",
                "capacity_per_degree": 0.1,
                "initial_temperature": 50.0,
                "reference_temperature": 0.0,
                "maximum_temperature": 75.0,
                "hp_ceiling_temperature": 65.0,
                "loss_power": [0.23, 0.23],
                "draw_energy": [0.0, 0.0],
                "target_temperature": [60.0] * 3,
                "shortfall_price": [10.0] * 3,
                "hp_cop": [3.0, 3.0],
                "hp_max_power": [0.8, 0.8],
                "element_cop": [1.0, 1.0],
                "element_max_power": [0.8, 0.8],
            },
        ],
    }
]
OUTPUTS_CASES: list[OutputsCase] = [
    {
        "description": "Thermal energy maps to C with per-stage and total heating power",
        "data": DATA,
        "periods": np.ones(2),
        "model_outputs": {
            "tank:thermal": {
                "thermal_store_energy": OutputData(type=OutputType.ENERGY, unit="kWh", values=(5.0, 6.5, 6.5)),
                "thermal_store_power_hp": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.5, 0.0), direction="-"
                ),
                "thermal_store_power_element": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, 0.0), direction="-"
                ),
                "thermal_store_shortfall": OutputData(type=OutputType.ENERGY, unit="kWh", values=(1.0, 0.0, 0.0)),
            },
            "tank:heat_pump": {
                "connection_power": OutputData(type=OutputType.POWER_FLOW, unit="kW", values=(0.5, 0.0), direction="+")
            },
            "tank:element": {
                "connection_power": OutputData(type=OutputType.POWER_FLOW, unit="kW", values=(0.0, 0.0), direction="+")
            },
        },
        "outputs": {
            ElementType.THERMAL_STORE: {
                "thermal_store_temperature": OutputData(
                    type=OutputType.TEMPERATURE, unit="°C", values=(50.0, 65.0, 65.0)
                ),
                "thermal_store_power": OutputData(type=OutputType.POWER, unit="kW", values=(0.5, 0.0), direction="-"),
                "thermal_store_power_hp": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.5, 0.0), direction="-"
                ),
                "thermal_store_power_element": OutputData(
                    type=OutputType.POWER, unit="kW", values=(0.0, 0.0), direction="-"
                ),
                "thermal_store_shortfall": OutputData(type=OutputType.ENERGY, unit="kWh", values=(1.0, 0.0, 0.0)),
            }
        },
    }
]
