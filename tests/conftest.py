"""Shared fixtures for InvertirOnline (IOL) tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

MOCK_TOKEN_RESPONSE: dict[str, Any] = {
    "access_token": "mock_access_token_123",
    "token_type": "bearer",
    "expires_in": 900,
    "refresh_token": "mock_refresh_token_456",
}

MOCK_CAUCIONES_RESPONSE: list[dict[str, Any]] = [
    {
        "plazo": 1,
        "tasaColocadora": 36.50,
        "tasaTomadora": 37.20,
        "montoOperado": 125000000.0,
        "puntas": [{"precioCompra": 36.4, "precioVenta": 37.3}],
        "fechaHora": "2026-11-17T15:30:00",
    },
    {
        "plazo": 7,
        "tasaColocadora": 38.00,
        "tasaTomadora": 38.90,
        "montoOperado": 45000000.0,
        "puntas": [{"precioCompra": 37.8, "precioVenta": 39.0}],
        "fechaHora": "2026-11-17T15:30:00",
    },
    {
        "plazo": 14,
        "tasaColocadora": 39.25,
        "tasaTomadora": 40.10,
        "montoOperado": 18000000.0,
        "puntas": [{"precioCompra": 39.0, "precioVenta": 40.2}],
        "fechaHora": "2026-11-17T15:30:00",
    },
    {
        "plazo": 30,
        "tasaColocadora": 41.00,
        "tasaTomadora": 42.00,
        "montoOperado": 32000000.0,
        "puntas": [{"precioCompra": 40.8, "precioVenta": 42.1}],
        "fechaHora": "2026-11-17T15:30:00",
    },
    {
        "plazo": 60,
        "tasaColocadora": 42.50,
        "tasaTomadora": 43.50,
        "montoOperado": 9500000.0,
        "puntas": [{"precioCompra": 42.2, "precioVenta": 43.6}],
        "fechaHora": "2026-11-17T15:30:00",
    },
]

MOCK_SPY_QUOTE: dict[str, Any] = {
    "simbolo": "SPY",
    "descripcionTitulo": "SPDR S&P 500 ETF Trust CEDEAR",
    "ultimoPrecio": 34500.0,
    "moneda": "ARS",
    "variacion": 1.25,
    "puntas": [{"precioCompra": 34450.0, "precioVenta": 34550.0}],
    "volumenNominal": 5420,
    "apertura": 34100.0,
    "maximo": 34600.0,
    "minimo": 34050.0,
    "cierreAnterior": 34074.0,
    "fechaHora": "2026-11-17T15:30:00",
}

MOCK_ESTADO_CUENTA: dict[str, Any] = {
    "cuentas": [
        {
            "numero": "987654",
            "moneda": "peso_Argentino",
            "disponible": 500000.0,
        },
        {
            "numero": "987654",
            "moneda": "dolar_Estadounidense",
            "disponible": 250.0,
        },
    ],
    "totalEnPesos": 2500000.0,
}

MOCK_PORTAFOLIO: dict[str, Any] = {
    "pais": "argentina",
    "activos": [
        {"titulo": {"simbolo": "SPY"}, "valorizado": 1500000.0},
        {"titulo": {"simbolo": "AL30"}, "valorizado": 500000.0},
    ],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_iol_api() -> Generator[AsyncMock, None, None]:
    """Mock IOLApiClient methods with realistic responses (no network calls)."""
    with (
        patch("custom_components.invertironline.async_get_clientsession"),
        patch(
            "custom_components.invertironline.IOLApiClient", autospec=True
        ) as mock_cls,
    ):
        client = mock_cls.return_value
        client.async_authenticate = AsyncMock(return_value=MOCK_TOKEN_RESPONSE)
        client.async_refresh_token = AsyncMock(return_value=MOCK_TOKEN_RESPONSE)
        client.async_ensure_valid_token = AsyncMock(
            return_value="mock_access_token_123"
        )
        client.async_get_cauciones = AsyncMock(return_value=MOCK_CAUCIONES_RESPONSE)
        client.async_get_dolar_mep = AsyncMock(return_value=1150.0)
        client.async_get_dolar_cotizaciones = AsyncMock(
            return_value=[{"descripcion": "Dólar CCL", "valor": 1200.0}]
        )
        client.async_get_estado_cuenta = AsyncMock(return_value=MOCK_ESTADO_CUENTA)
        client.async_get_portafolio = AsyncMock(return_value=MOCK_PORTAFOLIO)

        async def _quote(simbolo: str, mercado: str = "bCBA") -> dict[str, Any]:
            if simbolo.upper() == "SPY":
                return MOCK_SPY_QUOTE
            return {
                "simbolo": simbolo.upper(),
                "descripcionTitulo": f"Activo {simbolo.upper()}",
                "ultimoPrecio": 5420.5,
                "moneda": "ARS",
                "variacion": 2.15,
                "puntas": [{"precioCompra": 5415.0, "precioVenta": 5425.0}],
                "volumenNominal": 142050,
                "apertura": 5300.0,
                "maximo": 5450.0,
                "minimo": 5290.0,
                "cierreAnterior": 5306.4,
                "fechaHora": "2026-11-17T15:30:00",
            }

        client.async_get_quote = AsyncMock(side_effect=_quote)

        async def _inflacion(url: str) -> dict[str, Any]:
            if "Interanual" in url:
                return {
                    "valor": 33.13,
                    "fecha": "2026-10-01",
                    "valor_anterior": 34.5,
                    "fecha_anterior": "2026-09-01",
                    "fuente": "ArgentinaDatos",
                }
            return {
                "valor": 2.7,
                "fecha": "2026-10-01",
                "valor_anterior": 2.9,
                "fecha_anterior": "2026-09-01",
                "fuente": "ArgentinaDatos",
            }

        client.async_get_inflacion = AsyncMock(side_effect=_inflacion)
        yield client
