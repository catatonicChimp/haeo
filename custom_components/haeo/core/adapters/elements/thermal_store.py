"""Compose a passive electrical load and a thermal overlay; no device commands."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Final, Literal

import numpy as np

from custom_components.haeo.core.adapters.output_utils import connection_power, expect_output_data
from custom_components.haeo.core.const import ConnectivityLevel
from custom_components.haeo.core.model import ModelElementConfig, ModelOutputName, ModelOutputValue
from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.schema import extract_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.buffer import BufferRole
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData

type ThermalDeviceName = Literal[ElementType.THERMAL_STORE]
type ThermalOutputName = Literal["thermal_store_power", "thermal_store_temperature", "thermal_store_shortfall"]
THERMAL_OUTPUT_NAMES: Final[frozenset[ThermalOutputName]] = frozenset(
    ("thermal_store_power", "thermal_store_temperature", "thermal_store_shortfall")
)


class ThermalStoreAdapter:
    """Experimental planning element for a separately configured shadow network."""

    element_type: str = ElementType.THERMAL_STORE
    advanced = True
    connectivity = ConnectivityLevel.NEVER
    can_source = False
    can_sink = True
    switchboard = False
    buffer_roles: frozenset[BufferRole] = frozenset()
    device_names: frozenset[ThermalDeviceName] = frozenset((ElementType.THERMAL_STORE,))

    def model_elements(self, config: ThermalStoreConfigData) -> list[ModelElementConfig]:
        """Compose the load and flow-reader with explicit thermal units."""
        name = config["name"]
        data = config["thermal"]
        return [
            {"element_type": "node", "name": name, "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": f"{name}:connection",
                "source": extract_connection_target(config["connection"]),
                "target": name,
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": data["max_power"]}},
            },
            {
                "element_type": "thermal_store",
                "name": f"{name}:thermal",
                "connection": f"{name}:connection",
                "capacity_per_degree": data["capacity_per_degree"],
                "initial_temperature": data["initial_temperature"],
                "reference_temperature": 0.0,
                "maximum_temperature": data["maximum_temperature"],
                "cop": data["cop"],
                "loss_power": data["loss_power"] + data["draw_power"],
                "draw_energy": np.zeros_like(data["draw_power"]),
                "target_temperature": data["target_temperature"],
                "shortfall_price": data["shortfall_price"],
            },
        ]

    def outputs(
        self,
        name: str,
        model_outputs: Mapping[str, Mapping[ModelOutputName, ModelOutputValue]],
        *,
        config: ThermalStoreConfigData,
        **_kwargs: object,
    ) -> Mapping[ThermalDeviceName, Mapping[ThermalOutputName, OutputData]]:
        """Expose forecast-only power, temperature and thermal readiness deficit."""
        outputs = model_outputs[f"{name}:thermal"]
        energy = expect_output_data(outputs["thermal_store_energy"])
        return {
            ElementType.THERMAL_STORE: {
                "thermal_store_power": replace(
                    connection_power(model_outputs.get(f"{name}:connection"), len(energy.values) - 1),
                    type=OutputType.POWER,
                    direction="-",
                ),
                "thermal_store_temperature": OutputData(
                    type=OutputType.TEMPERATURE,
                    unit="°C",
                    values=tuple(v / config["thermal"]["capacity_per_degree"] for v in energy.values),
                ),
                "thermal_store_shortfall": expect_output_data(outputs["thermal_store_shortfall"]),
            }
        }


adapter = ThermalStoreAdapter()
