"""Tests for the appliance element config flow."""

from homeassistant.config_entries import SOURCE_USER, SubentryFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import add_participant
from custom_components.haeo.core.const import CONF_NAME
from custom_components.haeo.core.schema import as_constant_value, as_entity_value
from custom_components.haeo.core.schema.elements import node
from custom_components.haeo.core.schema.elements.appliance import (
    CONF_ARMED,
    CONF_DURATION,
    CONF_EARLIEST_START,
    CONF_ENERGY,
    CONF_LATEST_FINISH,
    ELEMENT_TYPE,
    SECTION_SCHEDULE,
    SECTION_WINDOW,
)
from custom_components.haeo.core.schema.sections import CONF_CONNECTION
from custom_components.haeo.flows.field_schema import CHOICE_CONSTANT, CHOICE_ENTITY


async def _appliance_form(hass: HomeAssistant, hub_entry: MockConfigEntry) -> SubentryFlowResult:
    """Open a new appliance form on a hub that has a switchboard to connect to."""
    add_participant(hass, hub_entry, "Switchboard", node.ELEMENT_TYPE)
    return await hass.config_entries.subentries.async_init(
        (hub_entry.entry_id, ELEMENT_TYPE),
        context={"source": SOURCE_USER},
    )


async def _submit(hass: HomeAssistant, form: SubentryFlowResult, user_input: dict[str, object]) -> SubentryFlowResult:
    """Submit the appliance form the way the frontend does, through the flow manager's schema."""
    return await hass.config_entries.subentries.async_configure(form["flow_id"], user_input)


def _stored_schedule(result: SubentryFlowResult) -> dict[str, object]:
    """Return the schedule section of a created appliance's stored config."""
    data = result.get("data")
    assert data is not None
    return data[SECTION_SCHEDULE]


def _entity(entity_id: str) -> dict[str, object]:
    """Build a frontend entity choice submission."""
    return {"active_choice": CHOICE_ENTITY, CHOICE_ENTITY: [entity_id]}


def _constant(value: object) -> dict[str, object]:
    """Build a frontend constant choice submission."""
    return {"active_choice": CHOICE_CONSTANT, CHOICE_CONSTANT: value}


async def test_armed_entity_submission_stores_an_entity_value(
    hass: HomeAssistant,
    hub_entry: MockConfigEntry,
) -> None:
    """An armed switch chosen as an entity survives the form and is stored as an entity."""
    form = await _appliance_form(hass, hub_entry)

    result = await _submit(
        hass,
        form,
        {
            CONF_NAME: "Dishwasher",
            CONF_CONNECTION: "Switchboard",
            SECTION_SCHEDULE: {
                CONF_ARMED: _entity("input_boolean.dishwasher_armed"),
                CONF_ENERGY: _entity("input_number.dishwasher_energy"),
                CONF_DURATION: _entity("input_number.dishwasher_duration"),
            },
            SECTION_WINDOW: {
                CONF_EARLIEST_START: _constant(18.0),
                CONF_LATEST_FINISH: _constant(7.0),
            },
        },
    )

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    schedule = _stored_schedule(result)
    assert schedule[CONF_ARMED] == as_entity_value(["input_boolean.dishwasher_armed"])
    assert schedule[CONF_ENERGY] == as_entity_value(["input_number.dishwasher_energy"])
    assert schedule[CONF_DURATION] == as_entity_value(["input_number.dishwasher_duration"])


async def test_bare_armed_entity_list_stores_an_entity_value(
    hass: HomeAssistant,
    hub_entry: MockConfigEntry,
) -> None:
    """An armed switch submitted as a bare entity list is stored as an entity."""
    form = await _appliance_form(hass, hub_entry)

    result = await _submit(
        hass,
        form,
        {
            CONF_NAME: "Dishwasher",
            CONF_CONNECTION: "Switchboard",
            SECTION_SCHEDULE: {
                CONF_ARMED: ["input_boolean.dishwasher_armed"],
                CONF_ENERGY: 1.0,
                CONF_DURATION: 2.0,
            },
            SECTION_WINDOW: {
                CONF_EARLIEST_START: 0.0,
                CONF_LATEST_FINISH: 24.0,
            },
        },
    )

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert _stored_schedule(result)[CONF_ARMED] == as_entity_value(["input_boolean.dishwasher_armed"])


async def test_armed_constant_submission_stores_a_constant_value(
    hass: HomeAssistant,
    hub_entry: MockConfigEntry,
) -> None:
    """An armed constant is still stored as a constant, and energy chosen as an entity stays an entity."""
    form = await _appliance_form(hass, hub_entry)

    result = await _submit(
        hass,
        form,
        {
            CONF_NAME: "Dishwasher",
            CONF_CONNECTION: "Switchboard",
            SECTION_SCHEDULE: {
                CONF_ARMED: _constant(False),
                CONF_ENERGY: _entity("input_number.dishwasher_energy"),
                CONF_DURATION: _constant(2.0),
            },
            SECTION_WINDOW: {
                CONF_EARLIEST_START: _constant(18.0),
                CONF_LATEST_FINISH: _constant(7.0),
            },
        },
    )

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    schedule = _stored_schedule(result)
    assert schedule[CONF_ARMED] == as_constant_value(False)
    assert schedule[CONF_ENERGY] == as_entity_value(["input_number.dishwasher_energy"])
    assert schedule[CONF_DURATION] == as_constant_value(2.0)
