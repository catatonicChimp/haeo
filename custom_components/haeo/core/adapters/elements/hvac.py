"""One electrical sink and one mode for all rooms of a whole-house aircon."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Final, Literal

from custom_components.haeo.core.adapters.output_utils import connection_power
from custom_components.haeo.core.const import ConnectivityLevel
from custom_components.haeo.core.model import (
    ModelElementConfig,
    ModelOutputName,
    ModelOutputValue,
    OutputData,
    OutputType,
)
from custom_components.haeo.core.schema import extract_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.buffer import BufferRole
from custom_components.haeo.core.schema.elements.hvac import HvacConfigData

type HvacDeviceName = Literal[ElementType.HVAC]
type HvacOutputName = Literal["hvac_power"]
HVAC_OUTPUT_NAMES: Final[frozenset[HvacOutputName]] = frozenset(("hvac_power",))


class HvacAdapter:
    """Shared electrical HVAC appliance; never calls a climate service."""

    element_type: str = ElementType.HVAC
    advanced = False
    connectivity = ConnectivityLevel.NEVER
    can_source = False
    can_sink = True
    switchboard = False
    buffer_roles: frozenset[BufferRole] = frozenset()
    device_names: frozenset[HvacDeviceName] = frozenset((ElementType.HVAC,))

    def model_elements(self, config: HvacConfigData) -> list[ModelElementConfig]:
        """Create one sink regardless of how many rooms observe the appliance."""
        name = config["name"]
        return [
            {"element_type": "node", "name": name, "is_source": False, "is_sink": True},
            {
                "element_type": "connection",
                "name": f"{name}:connection",
                "source": extract_connection_target(config["connection"]),
                "target": name,
                "segments": {"power_limit": {"segment_type": "power_limit", "max_power": config["hvac"]["max_power"]}},
            },
            {
                "element_type": "hvac",
                "name": f"{name}:hvac",
                "connection": f"{name}:connection",
                "mode": config["hvac"]["mode"],
            },
        ]

    def outputs(
        self,
        name: str,
        model_outputs: Mapping[str, Mapping[ModelOutputName, ModelOutputValue]],
        *,
        config: HvacConfigData,
        **_kwargs: object,
    ) -> Mapping[HvacDeviceName, Mapping[HvacOutputName, OutputData]]:
        """Publish the single shared consumption forecast."""
        n = len(config["hvac"]["max_power"])
        return {
            ElementType.HVAC: {
                "hvac_power": replace(
                    connection_power(model_outputs.get(f"{name}:connection"), n), type=OutputType.POWER, direction="-"
                )
            }
        }


adapter = HvacAdapter()
