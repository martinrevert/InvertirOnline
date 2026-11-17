"""Tests for InvertirOnline (IOL) config flow and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.invertironline.api import IOLAuthError
from custom_components.invertironline.const import (
    CONF_EXTRA_TICKERS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)


async def test_config_flow_success(hass: HomeAssistant) -> None:
    """Test successful config flow with mocked IOL authentication."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        patch(
            "custom_components.invertironline.config_flow._validate_credentials",
            new=AsyncMock(return_value="987654"),
        ),
        patch(
            "custom_components.invertironline.async_setup_entry",
            return_value=True,
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "InvertirOnline (987654)"
    assert result2["data"] == {
        CONF_USERNAME: "usuario_iol",
        CONF_PASSWORD: "secret_password",
    }


async def test_config_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Test config flow shows invalid_auth on HTTP 400/401."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.invertironline.config_flow._validate_credentials",
        new=AsyncMock(side_effect=IOLAuthError("HTTP 401")),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "wrong_password"},
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_options_flow_extra_tickers(hass: HomeAssistant, mock_iol_api) -> None:
    """Test configuring additional tickers and polling interval via OptionsFlow."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_EXTRA_TICKERS: "GGAL, AL30, NYSE:AAPL",
            CONF_SCAN_INTERVAL: 20,
        },
    )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_EXTRA_TICKERS: ["GGAL", "AL30", "NYSE:AAPL"],
        CONF_SCAN_INTERVAL: 20,
    }
    await hass.async_block_till_done()
