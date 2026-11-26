"""Tests for the config entry version 1.7 migration."""

from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haeo.const import DOMAIN
from custom_components.haeo.core.const import CONF_ELEMENT_TYPE, CONF_NAME
from custom_components.haeo.core.schema import as_constant_value, as_entity_value
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.elements.thermal_store import (
    CONF_ELEMENT_COP,
    CONF_ELEMENT_MAX_POWER,
    CONF_HP_CEILING_TEMPERATURE,
    CONF_HP_COP,
    CONF_HP_MAX_POWER,
    SECTION_ELEMENT,
    SECTION_HEAT_PUMP,
    SECTION_THERMAL,
)
from custom_components.haeo.migrations import v1_7


@pytest.fixture
async def migrated_thermal_store(hass: HomeAssistant) -> tuple[MockConfigEntry, ConfigSubentry]:
    """Create and migrate a v1.6-era single-stage thermal store."""
    entry = MockConfigEntry(domain=DOMAIN, title="Hub", data={CONF_NAME: "Hub"}, version=1, minor_version=6)
    entry.add_to_hass(hass)

    data: dict[str, object] = {
        CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
        CONF_NAME: "Shadow tank",
        SECTION_THERMAL: {
            "initial_temperature": as_entity_value(["sensor.tank_temp"]),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.314),
            "cop": as_constant_value(3.0),
            "loss_power": as_constant_value(0.12),
            "draw_power": as_constant_value(0.2),
            "max_power": as_constant_value(0.8),
            "shortfall_price": as_constant_value(10.0),
        },
    }
    subentry = ConfigSubentry(
        data=MappingProxyType(data), subentry_type=ElementType.THERMAL_STORE, title="Shadow tank", unique_id=None
    )
    hass.config_entries.async_add_subentry(entry, subentry)

    assert await v1_7.async_migrate_entry(hass, entry)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    return entry, updated_entry.subentries[subentry.subentry_id]


async def test_migration_moves_cop_and_max_power_to_heat_pump(
    hass: HomeAssistant, migrated_thermal_store: tuple[MockConfigEntry, ConfigSubentry]
) -> None:
    """Old COP and max power become heat-pump fields; old maximum becomes the ceiling."""
    _entry, subentry = migrated_thermal_store
    thermal = subentry.data[SECTION_THERMAL]
    heat_pump = subentry.data[SECTION_HEAT_PUMP]

    assert "cop" not in thermal
    assert "max_power" not in thermal
    assert heat_pump[CONF_HP_COP] == as_constant_value(3.0)
    assert heat_pump[CONF_HP_MAX_POWER] == as_constant_value(0.8)
    assert heat_pump[CONF_HP_CEILING_TEMPERATURE] == as_constant_value(75.0)


async def test_migration_adds_disabled_element_section(
    hass: HomeAssistant, migrated_thermal_store: tuple[MockConfigEntry, ConfigSubentry]
) -> None:
    """The element stage is added with zero power and a COP of one."""
    _entry, subentry = migrated_thermal_store
    element = subentry.data[SECTION_ELEMENT]
    assert element[CONF_ELEMENT_MAX_POWER] == as_constant_value(0.0)
    assert element[CONF_ELEMENT_COP] == as_constant_value(1.0)


async def test_migration_preserves_other_thermal_fields(
    hass: HomeAssistant, migrated_thermal_store: tuple[MockConfigEntry, ConfigSubentry]
) -> None:
    """Unchanged thermal fields keep their original values and wrappers."""
    _entry, subentry = migrated_thermal_store
    thermal = subentry.data[SECTION_THERMAL]
    assert thermal["initial_temperature"] == as_entity_value(["sensor.tank_temp"])
    assert thermal["target_temperature"] == as_constant_value(60.0)
    assert thermal["maximum_temperature"] == as_constant_value(75.0)
    assert thermal["capacity_per_degree"] == as_constant_value(0.314)
    assert thermal["loss_power"] == as_constant_value(0.12)
    assert thermal["draw_power"] == as_constant_value(0.2)
    assert thermal["shortfall_price"] == as_constant_value(10.0)


async def test_migration_updates_minor_version(
    hass: HomeAssistant, migrated_thermal_store: tuple[MockConfigEntry, ConfigSubentry]
) -> None:
    """The entry minor version is bumped to 1.7."""
    entry, _subentry = migrated_thermal_store
    assert entry.minor_version == v1_7.MINOR_VERSION


async def test_migration_is_idempotent(
    hass: HomeAssistant, migrated_thermal_store: tuple[MockConfigEntry, ConfigSubentry]
) -> None:
    """Running the migration again leaves the already-migrated store unchanged."""
    entry, before = migrated_thermal_store
    assert await v1_7.async_migrate_entry(hass, entry)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    after = updated_entry.subentries[before.subentry_id]
    assert dict(before.data) == dict(after.data)


async def test_migration_passes_through_non_thermal_elements(
    hass: HomeAssistant,
) -> None:
    """Elements that are not thermal stores are not modified."""
    entry = MockConfigEntry(domain=DOMAIN, title="Hub", data={CONF_NAME: "Hub"}, version=1, minor_version=6)
    entry.add_to_hass(hass)
    data: dict[str, object] = {
        CONF_ELEMENT_TYPE: ElementType.NODE,
        CONF_NAME: "Switchboard",
        "role": {"is_source": False},
    }
    subentry = ConfigSubentry(
        data=MappingProxyType(data), subentry_type=ElementType.NODE, title="Switchboard", unique_id=None
    )
    hass.config_entries.async_add_subentry(entry, subentry)

    assert await v1_7.async_migrate_entry(hass, entry)

    assert entry.minor_version == v1_7.MINOR_VERSION
    assert dict(entry.subentries[subentry.subentry_id].data) == data


async def test_migration_renames_thermal_input_number_unique_ids(
    hass: HomeAssistant,
) -> None:
    """The unique IDs of the old cop and max_power number entities are renamed."""
    entry = MockConfigEntry(domain=DOMAIN, title="Hub", data={CONF_NAME: "Hub"}, version=1, minor_version=6)
    entry.add_to_hass(hass)
    data: dict[str, object] = {
        CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
        CONF_NAME: "Shadow tank",
        SECTION_THERMAL: {
            "initial_temperature": as_constant_value(50.0),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.314),
            "cop": as_constant_value(3.0),
            "loss_power": as_constant_value(0.12),
            "draw_power": as_constant_value(0.2),
            "max_power": as_constant_value(0.8),
            "shortfall_price": as_constant_value(10.0),
        },
    }
    subentry = ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type=ElementType.THERMAL_STORE,
        title="Shadow tank",
        unique_id="sub_thermal",
    )
    hass.config_entries.async_add_subentry(entry, subentry)

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{entry.entry_id}_{subentry.subentry_id}_cop",
        config_entry=entry,
    )
    registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{entry.entry_id}_{subentry.subentry_id}_max_power",
        config_entry=entry,
    )

    assert await v1_7.async_migrate_entry(hass, entry)

    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}_cop") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}_max_power") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}_hp_cop") is not None
    assert (
        registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}_hp_max_power")
        is not None
    )


async def test_migration_passes_through_already_migrated_subentry_at_v6(
    hass: HomeAssistant,
) -> None:
    """A subentry that already has two-stage sections is left untouched at v1.6."""
    entry = MockConfigEntry(domain=DOMAIN, title="Hub", data={CONF_NAME: "Hub"}, version=1, minor_version=6)
    entry.add_to_hass(hass)
    data: dict[str, object] = {
        CONF_ELEMENT_TYPE: ElementType.THERMAL_STORE,
        CONF_NAME: "Shadow tank",
        SECTION_THERMAL: {
            "initial_temperature": as_constant_value(50.0),
            "target_temperature": as_constant_value(60.0),
            "maximum_temperature": as_constant_value(75.0),
            "capacity_per_degree": as_constant_value(0.314),
            "loss_power": as_constant_value(0.12),
            "draw_power": as_constant_value(0.2),
            "shortfall_price": as_constant_value(10.0),
        },
        SECTION_HEAT_PUMP: {
            CONF_HP_CEILING_TEMPERATURE: as_constant_value(65.0),
            CONF_HP_MAX_POWER: as_constant_value(1.2),
            CONF_HP_COP: as_constant_value(3.5),
        },
        SECTION_ELEMENT: {
            CONF_ELEMENT_MAX_POWER: as_constant_value(0.8),
            CONF_ELEMENT_COP: as_constant_value(1.0),
        },
    }
    subentry = ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type=ElementType.THERMAL_STORE,
        title="Shadow tank",
        unique_id="sub_thermal",
    )
    hass.config_entries.async_add_subentry(entry, subentry)

    assert await v1_7.async_migrate_entry(hass, entry)

    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert dict(updated_entry.subentries[subentry.subentry_id].data) == data
