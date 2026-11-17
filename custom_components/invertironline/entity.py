"""Base entity for InvertirOnline (IOL) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IOLDataUpdateCoordinator


class IOLEntity(CoordinatorEntity[IOLDataUpdateCoordinator]):
    """Common base entity linked to the IOL brokerage account device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IOLDataUpdateCoordinator,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the base IOL entity."""
        super().__init__(coordinator)
        account_id = (
            coordinator.data.get("account", {}).get("numero_cuenta")
            if coordinator.data
            else None
        ) or coordinator.config_entry.unique_id or coordinator.config_entry.entry_id

        self._attr_unique_id = f"{account_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.config_entry.entry_id))},
            name=coordinator.config_entry.title,
            manufacturer="InvertirOnline (IOL)",
            model="Cuenta Comitente",
            entry_type=DeviceEntryType.SERVICE,
        )
