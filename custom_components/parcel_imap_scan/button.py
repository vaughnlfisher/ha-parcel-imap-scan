"""Button platform for Parcel IMAP Scan: one tap to run a backfill scan."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SERVICE_SCAN_NOW


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the scan-now button for this config entry."""
    async_add_entities([ParcelScanButton(entry)])


class ParcelScanButton(ButtonEntity):
    """Button that triggers parcel_imap_scan.scan_now for this entry."""

    _attr_has_entity_name = True
    _attr_name = "Scan inbox now"
    _attr_icon = "mdi:email-search"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_scan_now"

    async def async_press(self) -> None:
        """Run the scan when pressed."""
        await self.hass.services.async_call(
            DOMAIN, SERVICE_SCAN_NOW, {"entry_id": self._entry.entry_id}, blocking=True
        )
