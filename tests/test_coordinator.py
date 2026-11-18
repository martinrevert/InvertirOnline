"""Tests for InvertirOnline (IOL) coordinator, token refresh, and fallbacks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.invertironline.api import IOLApiClient
from custom_components.invertironline.const import DOMAIN, MARKET_TIMEZONE
from custom_components.invertironline.coordinator import (
    IOLDataUpdateCoordinator,
    is_within_market_window,
    resolve_cauciones,
)


async def test_coordinator_token_refresh(hass: HomeAssistant) -> None:
    """Test that API client triggers grant_type=refresh_token when <60s remain."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 900,
        }
    )

    mock_post_ctx = MagicMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    # Token expires in 30 seconds (< 60s threshold)
    client = IOLApiClient(
        session=mock_session,
        username="user",
        password="pw",
        access_token="old_token",
        refresh_token="old_refresh_token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )

    token = await client.async_ensure_valid_token()

    assert token == "new_access_token"
    assert client.refresh_token == "new_refresh_token"
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args.kwargs
    assert call_kwargs["data"]["grant_type"] == "refresh_token"
    assert call_kwargs["data"]["refresh_token"] == "old_refresh_token"


async def test_coordinator_caucion_holiday_fallback() -> None:
    """Test that 1D caución falls back to 3D on Fridays/holidays and sets plazo_dias_real."""
    friday_panel = [
        {
            "plazo": 3,
            "tasaColocadora": 35.80,
            "tasaTomadora": 36.40,
            "montoOperado": 90000000.0,
            "puntas": [{"precioCompra": 35.7, "precioVenta": 36.5}],
            "fechaHora": "2026-11-20T15:00:00",
        },
        {
            "plazo": 7,
            "tasaColocadora": 37.50,
            "tasaTomadora": 38.20,
            "montoOperado": 25000000.0,
            "puntas": [{"precioCompra": 37.4, "precioVenta": 38.3}],
            "fechaHora": "2026-11-20T15:00:00",
        },
    ]

    resolved = resolve_cauciones(friday_panel)

    assert 1 in resolved
    assert resolved[1]["plazo_dias"] == 1
    assert resolved[1]["plazo_dias_real"] == 3
    assert resolved[1]["tasa_colocadora"] == 35.80
    assert resolved[7]["plazo_dias_real"] == 7


async def test_coordinator_ccl_implicit_fallback(hass: HomeAssistant, mock_iol_api) -> None:
    """Test implicit CCL calculation via AL30/AL30C when direct CCL is absent."""
    mock_iol_api.async_get_dolar_cotizaciones = AsyncMock(return_value=[])

    async def _quote_al30(simbolo: str, mercado: str = "bCBA"):
        if simbolo == "AL30":
            return {"ultimoPrecio": 72000.0}
        if simbolo == "AL30C":
            return {"ultimoPrecio": 60.0}
        return {"ultimoPrecio": 34500.0}

    mock_iol_api.async_get_quote = AsyncMock(side_effect=_quote_al30)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={"username": "u", "password": "p"},
    )
    coordinator = IOLDataUpdateCoordinator(hass, mock_iol_api, entry)
    data = await coordinator._async_update_data()

    assert data["dolar_ccl"] == 1200.0
    assert data["fuente_ccl"] == "ratio_implicito"
    assert data["total_usd_ccl"] == round(2500000.0 / 1200.0, 2)


async def test_coordinator_market_window_and_skip(hass: HomeAssistant, mock_iol_api) -> None:
    """Test Argentina market window (Mon-Fri 10:30-18:30 ART) and off-hours skip."""
    tz = ZoneInfo(MARKET_TIMEZONE)
    assert is_within_market_window(datetime(2026, 11, 17, 11, 0, tzinfo=tz)) is True
    assert is_within_market_window(datetime(2026, 11, 17, 19, 0, tzinfo=tz)) is False
    assert is_within_market_window(datetime(2026, 11, 21, 12, 0, tzinfo=tz)) is False  # Saturday

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={"username": "u", "password": "p"},
    )
    coordinator = IOLDataUpdateCoordinator(hass, mock_iol_api, entry)
    coordinator.data = {"cached": True}

    with patch(
        "custom_components.invertironline.coordinator.is_within_market_window",
        return_value=False,
    ):
        result = await coordinator._async_update_data()

    assert result == {"cached": True}
    mock_iol_api.async_ensure_valid_token.assert_not_called()


async def test_coordinator_expired_refresh_token_falls_back_to_password() -> None:
    """Test that an expired refresh_token (HTTP 400) falls back to grant_type=password."""
    resp_400 = MagicMock()
    resp_400.status = 400

    resp_200 = MagicMock()
    resp_200.status = 200
    resp_200.json = AsyncMock(
        return_value={
            "access_token": "fresh_password_token",
            "refresh_token": "fresh_refresh_token",
            "expires_in": 900,
        }
    )

    ctx_400 = MagicMock()
    ctx_400.__aenter__ = AsyncMock(return_value=resp_400)
    ctx_400.__aexit__ = AsyncMock(return_value=False)

    ctx_200 = MagicMock()
    ctx_200.__aenter__ = AsyncMock(return_value=resp_200)
    ctx_200.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.post = MagicMock(side_effect=[ctx_400, ctx_200])

    client = IOLApiClient(
        session=mock_session,
        username="user",
        password="pw",
        access_token="old_token",
        refresh_token="expired_refresh_token",
        token_expires_at=datetime.now(timezone.utc) - timedelta(hours=12),
    )

    token = await client.async_ensure_valid_token()

    assert token == "fresh_password_token"
    assert client.refresh_token == "fresh_refresh_token"
    assert mock_session.post.call_count == 2
    assert mock_session.post.call_args_list[0].kwargs["data"]["grant_type"] == "refresh_token"
    assert mock_session.post.call_args_list[1].kwargs["data"]["grant_type"] == "password"
