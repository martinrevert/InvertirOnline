"""Binary sensor platform for InvertirOnline (IOL)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    IOLDataUpdateCoordinator,
    is_byma_market_open,
    is_within_market_window,
)
from .entity import IOLEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up InvertirOnline binary sensor entities from a config entry."""
    coordinator: IOLDataUpdateCoordinator = entry.runtime_data["coordinator"]
    async_add_entities([IOLMercadoAbiertoBinarySensor(coordinator)])


class IOLMercadoAbiertoBinarySensor(IOLEntity, BinarySensorEntity):
    """Binary sensor indicating whether the local BYMA market session is open."""

    _attr_name = "Mercado Abierto"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the BYMA market open binary sensor."""
        super().__init__(coordinator, "mercado_abierto")
        self.entity_id = "binary_sensor.iol_mercado_abierto"

    @property
    def is_on(self) -> bool:
        """Return True during regular BYMA trading hours (Mon-Fri 11:00-17:00 ART)."""
        return is_byma_market_open()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return polling window status and regular session schedule."""
        return {
            "en_ventana_sondeo": is_within_market_window(),
            "horario_rueda": "11:00-17:00 ART (Lun-Vie)",
            "horario_sondeo": "10:30-18:30 ART (Lun-Vie)",
        }
