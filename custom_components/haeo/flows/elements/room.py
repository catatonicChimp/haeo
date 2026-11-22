"""Configure a room observer attached to the shared HVAC appliance."""

from collections.abc import Mapping
from typing import ClassVar

from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
import voluptuous as vol

from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.flows.connected_flow import ConnectedElementSubentryFlow, connection_target_name
from custom_components.haeo.flows.field_schema import SectionDefinition
from custom_components.haeo.flows.sectioned_flow import FieldEntries


class RoomSubentryFlowHandler(ConnectedElementSubentryFlow):
    """Rooms can select HVAC, never independent electrical power endpoints."""

    element_type = ElementType.ROOM
    sections: ClassVar[tuple[SectionDefinition, ...]] = (
        SectionDefinition(
            key="room",
            fields=(
                "initial_temperature",
                "outdoor_temperature",
                "minimum_temperature",
                "maximum_temperature",
                "loss_rate",
                "response",
                "comfort_price",
            ),
            collapsed=False,
        ),
    )

    def _top_level_entries(self, subentry_data: Mapping[str, object] | None) -> FieldEntries:
        """Offer only configured HVAC appliances as the room's parent."""
        _ = subentry_data
        options = [s.title for s in self._get_entry().subentries.values() if s.subentry_type == ElementType.HVAC]
        return {
            "name": (vol.Required("name"), str),
            "connection": (vol.Required("connection"), SelectSelector(SelectSelectorConfig(options=options))),
        }

    def _validate_fields(self, user_input: Mapping[str, object], errors: dict[str, str]) -> None:
        """Reject a switchboard or a missing shared appliance."""
        names = {s.title for s in self._get_entry().subentries.values() if s.subentry_type == ElementType.HVAC}
        if connection_target_name(user_input.get("connection")) not in names:
            errors["connection"] = "invalid_hvac"
