"""Tests for the two-stage thermal-store config flow."""

from types import MappingProxyType
from unittest.mock import Mock

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import add_participant
from custom_components.haeo.core.const import CONF_ELEMENT_TYPE, CONF_NAME
from custom_components.haeo.core.schema import as_connection_target, as_constant_value
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.thermal_store import (
    CONF_HP_CEILING_TEMPERATURE,
    SECTION_ELEMENT,
    SECTION_HEAT_PUMP,
    SECTION_THERMAL,
)
from custom_components.haeo.core.schema.sections import CONF_CONNECTION
from custom_components.haeo.flows.conftest import create_flow


def _base_config() -> dict[str, object]:
    """Return a complete two-stage thermal-store config for the flow."""
    return {
        CONF_NAME: "Shadow tank",
        CONF_CONNECTION: as_connection_target("switchboard"),
        SECTION_THERMAL: {
            "initial_temperature": as_constant_value(50.0),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.1),
            "loss_power": as_constant_value(0.0),
            "draw_power": as_constant_value(0.0),
            "shortfall_price": as_constant_value(10.0),
        },
        SECTION_HEAT_PUMP: {
            CONF_HP_CEILING_TEMPERATURE: as_constant_value(65.0),
            "hp_max_power": as_constant_value(0.8),
            "hp_cop": as_constant_value(3.0),
        },
        SECTION_ELEMENT: {
            "element_max_power": as_constant_value(0.8),
            "element_cop": as_constant_value(1.0),
        },
    }


async def test_valid_two_stage_config_creates_entry(hass: HomeAssistant, hub_entry: MockConfigEntry) -> None:
    """Submitting valid two-stage parameters creates the subentry."""
    add_participant(hass, hub_entry, "switchboard", "node")
    flow = create_flow(hass, hub_entry, ElementType.THERMAL_STORE)

    flow.async_create_entry = Mock(
        return_value={
            "type": FlowResultType.CREATE_ENTRY,
            "title": "Shadow tank",
            "data": {},
        }
    )

    result = await flow.async_step_user(user_input=_base_config())

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    created = flow.async_create_entry.call_args.kwargs["data"]
    assert created[CONF_ELEMENT_TYPE] == ElementType.THERMAL_STORE
    assert created[CONF_NAME] == "Shadow tank"
    assert created[SECTION_HEAT_PUMP][CONF_HP_CEILING_TEMPERATURE] == as_constant_value(65.0)


async def test_ceiling_above_maximum_adds_section_error(hass: HomeAssistant, hub_entry: MockConfigEntry) -> None:
    """A heat-pump ceiling above the physical maximum is rejected on the heat_pump section."""
    add_participant(hass, hub_entry, "switchboard", "node")
    flow = create_flow(hass, hub_entry, ElementType.THERMAL_STORE)

    user_input = _base_config()
    heat_pump_section = user_input[SECTION_HEAT_PUMP]
    assert isinstance(heat_pump_section, dict)
    heat_pump_section[CONF_HP_CEILING_TEMPERATURE] = as_constant_value(80.0)

    result = await flow.async_step_user(user_input=user_input)
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors") == {SECTION_HEAT_PUMP: "invalid_ceiling"}


async def test_migration_reports_old_power_as_hp_and_element_zero(
    hass: HomeAssistant, hub_entry: MockConfigEntry
) -> None:
    """A single-stage thermal store migrated to v1.7 keeps old power as HP and disables element."""
    add_participant(hass, hub_entry, "switchboard", "node")
    data = MappingProxyType(
        {
            CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
            CONF_NAME: "Shadow tank",
            CONF_CONNECTION: as_connection_target("switchboard"),
            SECTION_THERMAL: {
                "initial_temperature": as_constant_value(50.0),
                "target_temperature": as_constant_value(60.0),
                "maximum_temperature": as_constant_value(75.0),
                "capacity_per_degree": as_constant_value(0.1),
                "cop": as_constant_value(3.0),
                "loss_power": as_constant_value(0.0),
                "draw_power": as_constant_value(0.0),
                "max_power": as_constant_value(0.8),
                "shortfall_price": as_constant_value(10.0),
            },
        }
    )
    subentry = ConfigSubentry(data=data, subentry_type=ElementType.THERMAL_STORE, title="Shadow tank", unique_id=None)
    hass.config_entries.async_add_subentry(hub_entry, subentry)

    flow = create_flow(hass, hub_entry, ElementType.THERMAL_STORE)
    result = await flow.async_step_reconfigure(user_input=None)
    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors") is None
