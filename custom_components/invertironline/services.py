"""Service actions for InvertirOnline (IOL) Assist/LLM integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import IOLApiClient, IOLApiError
from .const import DEFAULT_MARKET, DOMAIN
from .coordinator import normalize_portfolio, normalize_quote

SERVICE_GET_QUOTE = "get_quote"
SERVICE_GET_PORTFOLIO = "get_portfolio"
ATTR_SIMBOLO = "simbolo"
ATTR_MERCADO = "mercado"
ATTR_PAIS = "pais"
ATTR_TIPO = "tipo"

GET_QUOTE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SIMBOLO): cv.string,
        vol.Optional(ATTR_MERCADO, default=DEFAULT_MARKET): cv.string,
    }
)

GET_PORTFOLIO_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PAIS, default="Argentina"): cv.string,
        vol.Optional(ATTR_TIPO): cv.string,
    }
)


def _get_active_api_client(hass: HomeAssistant) -> IOLApiClient:
    """Retrieve an active IOLApiClient from loaded config entries."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and isinstance(
            entry.runtime_data, dict
        ):
            api = entry.runtime_data.get("api")
            if isinstance(api, IOLApiClient):
                return api
    raise ServiceValidationError(
        "No active InvertirOnline account is loaded in Home Assistant."
    )


async def async_register_services(hass: HomeAssistant) -> None:
    """Register InvertirOnline service actions."""
    async def handle_get_quote(call: ServiceCall) -> ServiceResponse:
        """Handle invertironline.get_quote service call."""
        simbolo = str(call.data[ATTR_SIMBOLO]).strip().upper()
        mercado = str(call.data.get(ATTR_MERCADO, DEFAULT_MARKET)).strip() or DEFAULT_MARKET

        if not simbolo:
            raise ServiceValidationError("El parámetro 'simbolo' no puede estar vacío.")

        api = _get_active_api_client(hass)
        try:
            raw = await api.async_get_quote(simbolo=simbolo, mercado=mercado)
        except IOLApiError as err:
            raise HomeAssistantError(
                f"Error al consultar la cotización de {simbolo} ({mercado}): {err}"
            ) from err

        normalized = normalize_quote(raw, simbolo=simbolo, mercado=mercado)
        payload: dict[str, Any] = {
            "simbolo": normalized["simbolo"],
            "descripcion": normalized["descripcion"],
            "ultimo_precio": normalized["ultimo_precio"],
            "moneda": normalized["moneda"],
            "variacion_porcentual": normalized["variacion_diaria"],
            "punta_compradora": normalized["punta_compradora"],
            "punta_vendedora": normalized["punta_vendedora"],
            "volumen": normalized["volumen_nominal"],
            "fecha_hora": normalized["fecha_hora"],
        }
        return payload

    if not hass.services.has_service(DOMAIN, SERVICE_GET_QUOTE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_QUOTE,
            handle_get_quote,
            schema=GET_QUOTE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_get_portfolio(call: ServiceCall) -> ServiceResponse:
        """Handle invertironline.get_portfolio service call."""
        pais = str(call.data.get(ATTR_PAIS, "Argentina")).strip() or "Argentina"
        tipo = call.data.get(ATTR_TIPO)

        api = _get_active_api_client(hass)
        try:
            raw = await api.async_get_portafolio(pais=pais)
        except IOLApiError as err:
            raise HomeAssistantError(
                f"Error al consultar el portafolio ({pais}): {err}"
            ) from err

        return normalize_portfolio(raw, tipo_filtro=tipo)

    if not hass.services.has_service(DOMAIN, SERVICE_GET_PORTFOLIO):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PORTFOLIO,
            handle_get_portfolio,
            schema=GET_PORTFOLIO_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister InvertirOnline service actions when no entries remain."""
    for service_name in (SERVICE_GET_QUOTE, SERVICE_GET_PORTFOLIO):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
