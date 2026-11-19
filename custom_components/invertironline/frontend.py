"""Frontend resource registration for InvertirOnline (IOL) Lovelace cards."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/invertironline_files"
CARD_FILENAME = "invertironline-ticker-card.js"
CARD_VERSION = "1.0.4"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and auto-register the custom LED ticker card in Home Assistant."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("frontend_registered"):
        return

    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        _LOGGER.debug(
            "Skipping frontend card registration (http/frontend not active)"
        )
        return

    frontend_dir = Path(__file__).parent / "frontend"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(frontend_dir), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={CARD_VERSION}")
    domain_data["frontend_registered"] = True
    _LOGGER.debug("Registered InvertirOnline Lovelace ticker card at %s", URL_BASE)
