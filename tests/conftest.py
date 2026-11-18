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
        {
            "cantidad": 40.0,
            "ultimoPrecio": 37500.0,
            "valorizado": 1500000.0,
            "variacionDiaria": 1.5,
            "gananciaDinero": 120000.0,
            "gananciaPorcentaje": 8.7,
            "titulo": {"simbolo": "SPY", "descripcion": "CEDEAR SPY", "tipo": "CEDEAR", "moneda": "ARS"},
        },
        {
            "cantidad": 1000.0,
            "ultimoPrecio": 500.0,
            "valorizado": 500000.0,
            "variacionDiaria": 0.8,
            "gananciaDinero": 30000.0,
            "gananciaPorcentaje": 6.4,
            "titulo": {"simbolo": "AL30", "descripcion": "Bono AL30", "tipo": "TitulosPublicos", "moneda": "ARS"},
        },
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
        client.async_get_dolar_historico = AsyncMock(
            return_value=[
                {"casa": "bolsa", "fecha": "2025-10-31", "compra": 1090.0, "venta": 1100.0},
                {"casa": "bolsa", "fecha": "2026-08-31", "compra": 1110.0, "venta": 1120.0},
                {"casa": "bolsa", "fecha": "2026-09-30", "compra": 1130.0, "venta": 1140.0},
                {"casa": "bolsa", "fecha": "2026-10-31", "compra": 1145.0, "venta": 1150.0},
            ]
        )
        client.async_get_operaciones = AsyncMock(
            return_value=[
                {
                    "numero": 1001,
                    "simbolo": "AL30",
                    "tipo": "Compra",
                    "estado": "terminada",
                    "mercado": "bCBA",
                    "cantidad": 500,
                    "precio": 500.0,
                    "monto": 250000.0,
                    "fechaOrden": "2026-11-17T12:00:00",
                    "fechaOperada": "2026-11-17T12:01:00",
                }
            ]
        )
        client.async_get_panel_cotizaciones = AsyncMock(
            return_value=[
                {
                    "simbolo": "GGAL",
                    "descripcion": "Grupo Financiero Galicia",
                    "ultimoPrecio": 5420.5,
                    "variacionPorcentual": 2.15,
                    "volumen": 142050,
                    "puntas": [{"precioCompra": 5415.0, "precioVenta": 5425.0}],
                    "moneda": "ARS",
                },
                {
                    "simbolo": "YPFD",
                    "descripcion": "YPF S.A.",
                    "ultimoPrecio": 32100.0,
                    "variacionPorcentual": -0.85,
                    "volumen": 98000,
                    "puntas": [{"precioCompra": 32000.0, "precioVenta": 32200.0}],
                    "moneda": "ARS",
                },
            ]
        )
        client.async_get_serie_historica = AsyncMock(
            return_value=[
                {
                    "fechaHora": "2026-11-01T00:00:00",
                    "apertura": 5000.0,
                    "maximo": 5100.0,
                    "minimo": 4950.0,
                    "ultimoPrecio": 5050.0,
                    "volumenNominal": 100000,
                },
                {
                    "fechaHora": "2026-11-17T00:00:00",
                    "apertura": 5300.0,
                    "maximo": 5450.0,
                    "minimo": 5290.0,
                    "ultimoPrecio": 5420.5,
                    "volumenNominal": 142050,
                },
            ]
        )
        yield client
