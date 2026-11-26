"""Compose a two-stage thermal load and a thermal overlay; no device commands."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Final, Literal

import numpy as np

from custom_components.haeo.core.adapters.output_utils import expect_output_data
from custom_components.haeo.core.const import ConnectivityLevel
from custom_components.haeo.core.model import ModelElementConfig, ModelOutputName, ModelOutputValue
from custom_components.haeo.core.model.const import OutputType
from custom_components.haeo.core.model.output_data import OutputData
from custom_components.haeo.core.schema import extract_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.buffer import BufferRole
from custom_components.haeo.core.schema.elements.thermal_store import ThermalStoreConfigData

type ThermalDeviceName = Literal[ElementType.THERMAL_STORE]
type ThermalOutputName = Literal[
    "thermal_store_power",
    "thermal_store_power_element",
    "thermal_store_power_hp",
    "thermal_store_temperature",
    "thermal_store_shortfall",
]
THERMAL_OUTPUT_NAMES: Final[frozenset[ThermalOutputName]] = frozenset(
    (
        "thermal_store_power",
        "thermal_store_power_element",
        "thermal_store_power_hp",
        "thermal_store_temperature",
        "thermal_store_shortfall",
    )
)


def _sum_output_values(left: OutputData, right: OutputData) -> tuple[object, ...]:
    """Return the element-wise sum of two output value tuples."""
    return tuple(a + b for a, b in zip(left.values, right.values, strict=True))


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
        """Compose the two electrical connections and the thermal overlay."""
        name = config["name"]
        thermal = config["thermal"]
        heat_pump = config["heat_pump"]
        element = config["element"]
        connection_target = extract_connection_target(config["connection"])
        return [
            {"element_type": "node", "name": name, "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": f"{name}:heat_pump",
                "source": connection_target,
                "target": name,
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": heat_pump["hp_max_power"]}},
            },
            {
                "element_type": "connection",
                "name": f"{name}:element",
                "source": connection_target,
                "target": name,
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": element["element_max_power"]}},
            },
            {
                "element_type": "thermal_store",
                "name": f"{name}:thermal",
                "heat_pump_connection": f"{name}:heat_pump",
                "element_connection": f"{name}:element",
                "capacity_per_degree": thermal["capacity_per_degree"],
                "initial_temperature": thermal["initial_temperature"],
                "reference_temperature": 0.0,
                "maximum_temperature": thermal["maximum_temperature"],
                "hp_ceiling_temperature": heat_pump["hp_ceiling_temperature"],
                "loss_power": thermal["loss_power"] + thermal["draw_power"],
                "draw_energy": np.zeros_like(thermal["draw_power"]),
                "target_temperature": thermal["target_temperature"],
                "shortfall_price": thermal["shortfall_price"],
                "hp_cop": heat_pump["hp_cop"],
                "hp_max_power": heat_pump["hp_max_power"],
                "element_cop": element["element_cop"],
                "element_max_power": element["element_max_power"],
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
        thermal_name = f"{name}:thermal"
        thermal_outputs = model_outputs[thermal_name]
        energy = expect_output_data(thermal_outputs["thermal_store_energy"])
        hp_power = expect_output_data(thermal_outputs["thermal_store_power_hp"])
        element_power = expect_output_data(thermal_outputs["thermal_store_power_element"])
        total_power = replace(
            hp_power,
            type=OutputType.POWER,
            values=_sum_output_values(hp_power, element_power),
            direction="-",
        )
        return {
            ElementType.THERMAL_STORE: {
                "thermal_store_power": total_power,
                "thermal_store_power_hp": hp_power,
                "thermal_store_power_element": element_power,
                "thermal_store_temperature": OutputData(
                    type=OutputType.TEMPERATURE,
                    unit="°C",
                    values=tuple(v / config["thermal"]["capacity_per_degree"] for v in energy.values),
                ),
                "thermal_store_shortfall": expect_output_data(thermal_outputs["thermal_store_shortfall"]),
            }
        }


adapter = ThermalStoreAdapter()
