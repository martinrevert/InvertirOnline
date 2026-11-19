"""Config flow and Options flow for InvertirOnline (IOL)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IOLApiClient, IOLApiError, IOLAuthError, IOLConnectionError
from .const import (
    CONF_EXTRA_TICKERS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .coordinator import parse_extra_tickers

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_credentials(
    hass: Any, username: str, password: str
) -> str:
    """Validate credentials against IOL API and return account identifier."""
    session = async_get_clientsession(hass)
    client = IOLApiClient(session=session, username=username, password=password)
    await client.async_authenticate(username, password)

    account_number = username
    try:
        estado = await client.async_get_estado_cuenta()
        cuentas = estado.get("cuentas")
        if isinstance(cuentas, list) and cuentas:
            numero = cuentas[0].get("numero")
            if numero is not None:
                account_number = str(numero)
        elif estado.get("numeroCuenta") is not None:
            account_number = str(estado["numeroCuenta"])
    except IOLApiError:
        _LOGGER.debug("Could not fetch account number during setup; using username")

    return account_number


class IOLConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for InvertirOnline (IOL)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                account_number = await _validate_credentials(
                    self.hass, username, password
                )
            except IOLAuthError:
                errors["base"] = "invalid_auth"
            except (IOLConnectionError, IOLApiError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during IOL config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"iol_{account_number}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"InvertirOnline ({account_number})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when credentials or refresh tokens fail."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                await _validate_credentials(self.hass, username, password)
            except IOLAuthError:
                errors["base"] = "invalid_auth"
            except (IOLConnectionError, IOLApiError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during IOL reauth flow")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reauth_entry.data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IOLOptionsFlow:
        """Return the options flow for this handler."""
        return IOLOptionsFlow()


class IOLOptionsFlow(OptionsFlow):
    """Handle InvertirOnline options (extra tickers and scan interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            scan_interval = int(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
            )
            if scan_interval < MIN_SCAN_INTERVAL_MINUTES:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            else:
                raw_tickers = user_input.get(CONF_EXTRA_TICKERS, "")
                normalized_pairs = parse_extra_tickers(raw_tickers)
                formatted_tickers = [
                    f"{mkt}:{sym}" if mkt != "bCBA" else sym
                    for mkt, sym in normalized_pairs
                ]
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: scan_interval,
                        CONF_EXTRA_TICKERS: formatted_tickers,
                    },
                )

        current_tickers = self.config_entry.options.get(CONF_EXTRA_TICKERS, [])
        if isinstance(current_tickers, list):
            default_tickers = ", ".join(current_tickers)
        else:
            default_tickers = str(current_tickers or "")

        default_interval = int(
            self.config_entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_EXTRA_TICKERS,
                        default=default_tickers,
                    ): str,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=default_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=1440)),
                }
            ),
            errors=errors,
        )
