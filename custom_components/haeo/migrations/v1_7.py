"""Migration for config entry version 1.7.

Two-stage thermal stores get their legacy single-stage fields reorganised, and
the input-number unique IDs that exposed the old cop and max_power fields are
renamed to hp_cop and hp_max_power so existing entities keep their entity IDs.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.haeo.const import DOMAIN
from custom_components.haeo.core.const import CONF_ELEMENT_TYPE
from custom_components.haeo.core.schema.elements import ElementType
from custom_components.haeo.core.schema.migrations import v1_7
from custom_components.haeo.core.schema.migrations.v1_7 import MINOR_VERSION

__all__ = ["MINOR_VERSION", "async_migrate_entry"]

_LOGGER = logging.getLogger(__name__)

# Fields whose unique-id leaf changed in the v1.7 thermal-store schema
_THERMAL_FIELD_RENAMES: dict[str, str] = {
    "cop": "hp_cop",
    "max_power": "hp_max_power",
}
_UNIQUE_ID_PART_COUNT = 3
_LIST_ITEM_PATH_PART_COUNT = 3


async def _migrate_entity_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename thermal-store input-number unique ids that collide after the schema change."""
    registry = er.async_get(hass)
    candidate_unique_ids: dict[str, str] = {}
    candidate_counts: dict[str, int] = {}

    subentry_types: dict[str, str] = {sid: sub.subentry_type or "" for sid, sub in entry.subentries.items()}

    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        uid = entity_entry.unique_id
        if not uid:
            continue

        parts = uid.split("_", 2)
        if len(parts) != _UNIQUE_ID_PART_COUNT:
            continue

        subentry_id = parts[1]
        field_path_key = parts[2]
        path_parts = field_path_key.split(".")
        if len(path_parts) >= _LIST_ITEM_PATH_PART_COUNT:
            continue

        new_leaf = path_parts[-1]
        if subentry_types.get(subentry_id, "") == ElementType.THERMAL_STORE:
            new_leaf = _THERMAL_FIELD_RENAMES.get(new_leaf, new_leaf)

        new_uid = f"{parts[0]}_{subentry_id}_{new_leaf}"
        if new_uid == uid:
            continue

        candidate_unique_ids[entity_entry.entity_id] = new_uid
        candidate_counts[new_uid] = candidate_counts.get(new_uid, 0) + 1

    def _migrate_unique_id(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
        new_uid = candidate_unique_ids.get(entity_entry.entity_id)
        if new_uid is None:
            return None

        if candidate_counts.get(new_uid, 0) > 1:
            _LOGGER.info(
                "Skipping unique_id migration for %s because stripped key would collide: %s",
                entity_entry.entity_id,
                new_uid,
            )
            return None

        conflict_entity_id = registry.async_get_entity_id(
            entity_entry.domain,
            entity_entry.platform,
            new_uid,
        )
        if conflict_entity_id and conflict_entity_id != entity_entry.entity_id:
            _LOGGER.info(
                "Removing duplicate entity %s to keep existing stable unique_id %s",
                entity_entry.entity_id,
                new_uid,
            )
            registry.async_remove(entity_entry.entity_id)
            return None

        return {"new_unique_id": new_uid}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate existing config entries to version 1.7."""
    if entry.minor_version >= MINOR_VERSION:
        return True

    _LOGGER.info(
        "Migrating %s entry %s to version 1.%s",
        DOMAIN,
        entry.entry_id,
        MINOR_VERSION,
    )

    for subentry in list(entry.subentries.values()):
        migrated = v1_7.migrate_element_config({CONF_ELEMENT_TYPE: subentry.subentry_type, **subentry.data})
        if migrated is not None:
            hass.config_entries.async_update_subentry(entry, subentry, data=migrated)

    await _migrate_entity_unique_ids(hass, entry)
    hass.config_entries.async_update_entry(entry, minor_version=MINOR_VERSION)
    _LOGGER.info("Migration complete for %s entry %s", DOMAIN, entry.entry_id)
    return True
