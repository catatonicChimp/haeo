"""Room predictions reference a shared HVAC model and consume no extra power."""

from collections.abc import Mapping
from typing import Final, Literal

from custom_components.haeo.core.adapters.output_utils import expect_output_data
from custom_components.haeo.core.const import ConnectivityLevel
from custom_components.haeo.core.model import ModelElementConfig, ModelOutputName, ModelOutputValue, OutputData
from custom_components.haeo.core.schema import extract_connection_target
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.buffer import BufferRole
from custom_components.haeo.core.schema.elements.room import RoomConfigData

type RoomDeviceName = Literal[ElementType.ROOM]
type RoomOutputName = Literal["room_temperature", "room_cold_shortfall", "room_hot_shortfall"]
ROOM_OUTPUT_NAMES: Final[frozenset[RoomOutputName]] = frozenset(
    ("room_temperature", "room_cold_shortfall", "room_hot_shortfall")
)


class RoomAdapter:
    """Room observer and comfort objective; not a separately controllable zone."""

    element_type: str = ElementType.ROOM
    advanced = False
    connectivity = ConnectivityLevel.NEVER
    can_source = False
    can_sink = False
    switchboard = False
    buffer_roles: frozenset[BufferRole] = frozenset()
    device_names: frozenset[RoomDeviceName] = frozenset((ElementType.ROOM,))

    def model_elements(self, config: RoomConfigData) -> list[ModelElementConfig]:
        """Contribute only thermal constraints tied to shared HVAC."""
        return [
            {
                "element_type": "room",
                "name": config["name"],
                "hvac": f"{extract_connection_target(config['connection'])}:hvac",
                **config["room"],
            }
        ]

    def outputs(
        self,
        name: str,
        model_outputs: Mapping[str, Mapping[ModelOutputName, ModelOutputValue]],
        *,
        config: RoomConfigData,
        **_kwargs: object,
    ) -> Mapping[RoomDeviceName, Mapping[RoomOutputName, OutputData]]:
        """Publish room-specific temperatures and both comfort deviations."""
        _ = config
        return {ElementType.ROOM: {key: expect_output_data(model_outputs[name][key]) for key in ROOM_OUTPUT_NAMES}}


adapter = RoomAdapter()
