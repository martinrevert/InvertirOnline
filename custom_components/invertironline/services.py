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
from .coordinator import (
    normalize_historical_series,
    normalize_market_panel,
    normalize_operations,
    normalize_portfolio,
    normalize_quote,
)

SERVICE_GET_QUOTE = "get_quote"
SERVICE_GET_PORTFOLIO = "get_portfolio"
SERVICE_GET_OPERATIONS = "get_operations"
SERVICE_GET_MARKET_PANEL = "get_market_panel"
SERVICE_GET_HISTORICAL_QUOTES = "get_historical_quotes"

ATTR_SIMBOLO = "simbolo"
ATTR_MERCADO = "mercado"
ATTR_PAIS = "pais"
ATTR_TIPO = "tipo"
ATTR_ESTADO = "estado"
ATTR_FECHA_DESDE = "fecha_desde"
ATTR_FECHA_HASTA = "fecha_hasta"
ATTR_LIMITE = "limite"
ATTR_INSTRUMENTO = "instrumento"
ATTR_PANEL = "panel"
ATTR_ORDENAR_POR = "ordenar_por"
ATTR_AJUSTADA = "ajustada"

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

GET_OPERATIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ESTADO): cv.string,
        vol.Optional(ATTR_FECHA_DESDE): cv.string,
        vol.Optional(ATTR_FECHA_HASTA): cv.string,
        vol.Optional(ATTR_PAIS, default="argentina"): cv.string,
        vol.Optional(ATTR_LIMITE, default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
    }
)

GET_MARKET_PANEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_INSTRUMENTO): cv.string,
        vol.Required(ATTR_PANEL): cv.string,
        vol.Optional(ATTR_PAIS, default="Argentina"): cv.string,
        vol.Optional(ATTR_ORDENAR_POR, default="variacion_desc"): vol.In(
            ["variacion_desc", "variacion_asc", "volumen_desc"]
        ),
        vol.Optional(ATTR_LIMITE, default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
    }
)

GET_HISTORICAL_QUOTES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SIMBOLO): cv.string,
        vol.Required(ATTR_FECHA_DESDE): cv.string,
        vol.Required(ATTR_FECHA_HASTA): cv.string,
        vol.Optional(ATTR_MERCADO, default=DEFAULT_MARKET): cv.string,
        vol.Optional(ATTR_AJUSTADA, default="ajustada"): vol.In(
            ["ajustada", "sinAjustar"]
        ),
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

    async def handle_get_operations(call: ServiceCall) -> ServiceResponse:
        """Handle invertironline.get_operations service call."""
        estado = call.data.get(ATTR_ESTADO)
        fecha_desde = call.data.get(ATTR_FECHA_DESDE)
        fecha_hasta = call.data.get(ATTR_FECHA_HASTA)
        pais = str(call.data.get(ATTR_PAIS, "argentina")).strip() or "argentina"
        limite = int(call.data.get(ATTR_LIMITE, 20))

        api = _get_active_api_client(hass)
        try:
            raw = await api.async_get_operaciones(
                estado=estado,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                pais=pais,
            )
        except IOLApiError as err:
            raise HomeAssistantError(
                f"Error al consultar operaciones ({pais}): {err}"
            ) from err

        return normalize_operations(raw, limit=limite)

    if not hass.services.has_service(DOMAIN, SERVICE_GET_OPERATIONS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_OPERATIONS,
            handle_get_operations,
            schema=GET_OPERATIONS_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_get_market_panel(call: ServiceCall) -> ServiceResponse:
        """Handle invertironline.get_market_panel service call."""
        instrumento = str(call.data[ATTR_INSTRUMENTO]).strip()
        panel = str(call.data[ATTR_PANEL]).strip()
        pais = str(call.data.get(ATTR_PAIS, "Argentina")).strip() or "Argentina"
        ordenar_por = str(call.data.get(ATTR_ORDENAR_POR, "variacion_desc"))
        limite = int(call.data.get(ATTR_LIMITE, 20))

        if not instrumento or not panel:
            raise ServiceValidationError(
                "Los parámetros 'instrumento' y 'panel' son obligatorios."
            )

        api = _get_active_api_client(hass)
        try:
            raw = await api.async_get_panel_cotizaciones(
                instrumento=instrumento, panel=panel, pais=pais
            )
        except IOLApiError as err:
            raise HomeAssistantError(
                f"Error al consultar panel {instrumento}/{panel} ({pais}): {err}"
            ) from err

        return normalize_market_panel(
            raw,
            instrumento=instrumento,
            panel=panel,
            pais=pais,
            sort_by=ordenar_por,
            limit=limite,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_MARKET_PANEL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_MARKET_PANEL,
            handle_get_market_panel,
            schema=GET_MARKET_PANEL_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    async def handle_get_historical_quotes(call: ServiceCall) -> ServiceResponse:
        """Handle invertironline.get_historical_quotes service call."""
        simbolo = str(call.data[ATTR_SIMBOLO]).strip().upper()
        fecha_desde = str(call.data[ATTR_FECHA_DESDE]).strip()
        fecha_hasta = str(call.data[ATTR_FECHA_HASTA]).strip()
        mercado = str(call.data.get(ATTR_MERCADO, DEFAULT_MARKET)).strip() or DEFAULT_MARKET
        ajustada = str(call.data.get(ATTR_AJUSTADA, "ajustada")).strip()

        if not simbolo:
            raise ServiceValidationError("El parámetro 'simbolo' no puede estar vacío.")

        api = _get_active_api_client(hass)
        try:
            raw = await api.async_get_serie_historica(
                simbolo=simbolo,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                mercado=mercado,
                ajustada=ajustada,
            )
        except IOLApiError as err:
            raise HomeAssistantError(
                f"Error al consultar serie histórica de {simbolo} ({mercado}): {err}"
            ) from err

        return normalize_historical_series(raw, simbolo=simbolo, mercado=mercado)

    if not hass.services.has_service(DOMAIN, SERVICE_GET_HISTORICAL_QUOTES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_HISTORICAL_QUOTES,
            handle_get_historical_quotes,
            schema=GET_HISTORICAL_QUOTES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister InvertirOnline service actions when no entries remain."""
    for service_name in (
        SERVICE_GET_QUOTE,
        SERVICE_GET_PORTFOLIO,
        SERVICE_GET_OPERATIONS,
        SERVICE_GET_MARKET_PANEL,
        SERVICE_GET_HISTORICAL_QUOTES,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
