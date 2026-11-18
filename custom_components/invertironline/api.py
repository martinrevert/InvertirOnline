"""Pure asynchronous REST API client for InvertirOnline (IOL) v2 (Read-Only)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    CAUCION_TERM_WINDOWS,
    CAUCION_TERMS,
    DEFAULT_MARKET,
    ENDPOINT_CAUCIONES,
    ENDPOINT_CAUCIONES_ALT,
    ENDPOINT_COTIZACION_TITULO,
    ENDPOINT_DOLAR_COTIZACIONES,
    ENDPOINT_DOLAR_MEP,
    ENDPOINT_ESTADO_CUENTA,
    ENDPOINT_OPERACIONES,
    ENDPOINT_PANEL_COTIZACIONES,
    ENDPOINT_PORTAFOLIO,
    ENDPOINT_SERIE_HISTORICA,
    ENDPOINT_TOKEN,
    REQUEST_TIMEOUT_SECONDS,
    TOKEN_REFRESH_MARGIN_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class IOLApiError(Exception):
    """Base exception for InvertirOnline API errors."""


class IOLAuthError(IOLApiError):
    """Authentication or token refresh error (HTTP 400/401)."""


class IOLConnectionError(IOLApiError):
    """Network, timeout, or upstream server error."""


class IOLApiClient:
    """Async read-only client for InvertirOnline API v2."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        """Initialize the IOL API client with Home Assistant's shared session."""
        self._session = session
        self._username = username
        self._password = password
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at
        self._token_lock = asyncio.Lock()

    @property
    def access_token(self) -> str | None:
        """Return current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        """Return current refresh token."""
        return self._refresh_token

    @property
    def token_expires_at(self) -> datetime | None:
        """Return UTC expiration timestamp of the current access token."""
        return self._token_expires_at

    def _is_token_expiring_soon(self) -> bool:
        """Check whether the access token is missing or expires within 60 seconds."""
        if not self._access_token or self._token_expires_at is None:
            return True
        now = datetime.now(timezone.utc)
        return now >= (
            self._token_expires_at - timedelta(seconds=TOKEN_REFRESH_MARGIN_SECONDS)
        )

    def _store_token_payload(self, payload: dict[str, Any]) -> None:
        """Persist OAuth2 token fields in memory without logging secrets."""
        self._access_token = payload.get("access_token")
        if payload.get("refresh_token"):
            self._refresh_token = payload["refresh_token"]

        expires_in = payload.get("expires_in", 900)
        try:
            expires_seconds = int(expires_in)
        except (TypeError, ValueError):
            expires_seconds = 900

        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_seconds
        )

    async def _post_token(self, form_data: dict[str, str]) -> dict[str, Any]:
        """Execute an OAuth2 token request against POST /token."""
        url = f"{API_BASE_URL}{ENDPOINT_TOKEN}"
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

        try:
            async with self._session.post(
                url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            ) as response:
                if response.status in (400, 401, 403):
                    raise IOLAuthError(
                        f"Authentication rejected by IOL API (HTTP {response.status})"
                    )
                if response.status >= 500:
                    raise IOLConnectionError(
                        f"IOL API server error during authentication (HTTP {response.status})"
                    )
                if response.status != 200:
                    raise IOLApiError(
                        f"Unexpected HTTP status {response.status} during authentication"
                    )

                payload = await response.json(content_type=None)
                if not isinstance(payload, dict) or not payload.get("access_token"):
                    raise IOLAuthError("Invalid token payload received from IOL API")

                self._store_token_payload(payload)
                return payload
        except IOLApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise IOLConnectionError(
                f"Network error connecting to IOL authentication endpoint: {err}"
            ) from err

    async def async_authenticate(
        self, username: str | None = None, password: str | None = None
    ) -> dict[str, Any]:
        """Authenticate using username and password (grant_type=password)."""
        if username is not None:
            self._username = username
        if password is not None:
            self._password = password

        return await self._post_token(
            {
                "username": self._username,
                "password": self._password,
                "grant_type": "password",
            }
        )

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh access token using grant_type=refresh_token."""
        if not self._refresh_token:
            return await self.async_authenticate()

        return await self._post_token(
            {
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            }
        )

    async def async_ensure_valid_token(self) -> str:
        """Ensure a valid Bearer token is available, refreshing if <60s remain."""
        async with self._token_lock:
            if self._is_token_expiring_soon():
                if self._refresh_token:
                    _LOGGER.debug("IOL access token expiring soon, refreshing token")
                    await self.async_refresh_token()
                else:
                    _LOGGER.debug("No refresh token available, authenticating with password")
                    await self.async_authenticate()

            if not self._access_token:
                raise IOLAuthError("Failed to obtain a valid access token")
            return self._access_token

    async def _async_get(
        self,
        endpoint: str,
        retry_on_401: bool = True,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform an authenticated GET request to the IOL API."""
        token = await self.async_ensure_valid_token()
        url = f"{API_BASE_URL}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

        try:
            async with self._session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=timeout,
            ) as response:
                if response.status == 401:
                    if retry_on_401:
                        _LOGGER.debug("Received HTTP 401 from %s, refreshing token", endpoint)
                        async with self._token_lock:
                            await self.async_refresh_token()
                        return await self._async_get(
                            endpoint, retry_on_401=False, params=params
                        )
                    raise IOLAuthError(
                        f"Unauthorized request to {endpoint} after token refresh"
                    )

                if response.status == 429:
                    raise IOLConnectionError(
                        f"Rate limit exceeded (HTTP 429) on {endpoint}"
                    )

                if response.status >= 500:
                    raise IOLConnectionError(
                        f"IOL server error (HTTP {response.status}) on {endpoint}"
                    )

                if response.status != 200:
                    raise IOLApiError(
                        f"Unexpected HTTP {response.status} on {endpoint}"
                    )

                return await response.json(content_type=None)
        except IOLApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise IOLConnectionError(
                f"Network error requesting {endpoint}: {err}"
            ) from err

    async def async_get_cauciones(self) -> list[dict[str, Any]]:
        """Fetch current cauciones panel for Argentina."""
        endpoints = (
            ENDPOINT_CAUCIONES,
            "/api/v2/argentina/Titulos/Cotizacion/Paneles/cauciones",
            ENDPOINT_CAUCIONES_ALT,
            "/api/Cotizaciones/cauciones/todas/argentina",
        )
        for endpoint in endpoints:
            try:
                data = await self._async_get(endpoint)
            except IOLAuthError:
                raise
            except IOLApiError as err:
                _LOGGER.warning("Cauciones endpoint %s failed: %s", endpoint, err)
                continue

            if isinstance(data, list) and data:
                _LOGGER.debug("Cauciones loaded from %s (%d items)", endpoint, len(data))
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                for key in ("titulos", "cauciones", "items", "data"):
                    nested = data.get(key)
                    if isinstance(nested, list) and nested:
                        _LOGGER.debug(
                            "Cauciones loaded from %s[%s] (%d items)",
                            endpoint,
                            key,
                            len(nested),
                        )
                        return [item for item in nested if isinstance(item, dict)]
                _LOGGER.warning(
                    "Cauciones endpoint %s returned dict with keys %s (no items)",
                    endpoint,
                    list(data.keys()),
                )

        # Fallback: public read-only market quote endpoint on iol.invertironline.com
        web_items = await self._async_get_cauciones_web_fallback()
        if web_items:
            return web_items
        return []

    async def _async_get_cauciones_web_fallback(self) -> list[dict[str, Any]]:
        """Fetch cauciones rates from IOL public market puntas endpoint (read-only)."""
        url = "https://iol.invertironline.com/Mercado/GetCaucionPuntas"
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        results: list[dict[str, Any]] = []

        for nominal in CAUCION_TERMS:
            min_d, max_d = CAUCION_TERM_WINDOWS.get(nominal, (nominal, nominal))
            # Try nominal first, then next business days if nominal has no market data
            candidates = [nominal] + [d for d in range(nominal + 1, max_d + 1)]
            for days in candidates:
                try:
                    async with self._session.post(
                        url,
                        data=f"moneda=PESOS&plazo={days}&idTipoTransaccion=14",
                        headers=headers,
                        timeout=timeout,
                    ) as resp:
                        if resp.status != 200:
                            break
                        payload = await resp.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    break

                parsed = _normalize_web_caucion(payload, days)
                if parsed is not None:
                    results.append(parsed)
                    break

        if not results:
            _LOGGER.warning("Web fallback GetCaucionPuntas returned no caución rates")
        return results

    async def async_get_quote(
        self, simbolo: str, mercado: str = DEFAULT_MARKET
    ) -> dict[str, Any]:
        """Fetch quote for a given symbol and market."""
        clean_symbol = simbolo.strip().upper()
        clean_market = (mercado or DEFAULT_MARKET).strip()
        endpoint = ENDPOINT_COTIZACION_TITULO.format(
            mercado=clean_market, simbolo=clean_symbol
        )
        data = await self._async_get(endpoint)
        return data if isinstance(data, dict) else {}

    async def async_get_dolar_mep(self) -> float | None:
        """Fetch official Dólar MEP rate from IOL if exposed directly."""
        try:
            data = await self._async_get(ENDPOINT_DOLAR_MEP)
            return extract_dolar_rate(data)
        except IOLAuthError:
            raise
        except IOLApiError as err:
            _LOGGER.debug("Direct Dólar MEP endpoint unavailable: %s", err)
            return None

    async def async_get_dolar_cotizaciones(self) -> Any:
        """Fetch currency quotes list from IOL (used to detect direct CCL)."""
        try:
            return await self._async_get(ENDPOINT_DOLAR_COTIZACIONES)
        except IOLAuthError:
            raise
        except IOLApiError as err:
            _LOGGER.debug("Direct Dólar cotizaciones endpoint unavailable: %s", err)
            return None

    async def async_get_estado_cuenta(self) -> dict[str, Any]:
        """Fetch account balances and account metadata."""
        data = await self._async_get(ENDPOINT_ESTADO_CUENTA)
        return data if isinstance(data, dict) else {}

    async def async_get_portafolio(self, pais: str = "Argentina") -> dict[str, Any]:
        """Fetch consolidated portfolio holdings for the given country (Argentina / Estados_Unidos)."""
        clean_pais = "Estados_Unidos" if str(pais).strip().lower() in ("estados_unidos", "eeuu", "usa", "us") else "Argentina"
        endpoint = f"/api/v2/portafolio/{clean_pais}" if clean_pais != "Argentina" else ENDPOINT_PORTAFOLIO
        data = await self._async_get(endpoint)
        return data if isinstance(data, dict) else {}

    async def async_get_operaciones(
        self,
        estado: str | None = None,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
        pais: str = "argentina",
    ) -> list[dict[str, Any]]:
        """Fetch account operations/orders history (read-only)."""
        params: dict[str, str] = {"filtro.pais": (pais or "argentina").strip().lower()}
        if estado:
            params["filtro.estado"] = estado.strip().lower()
        if fecha_desde:
            params["filtro.fechaDesde"] = fecha_desde.strip()
        if fecha_hasta:
            params["filtro.fechaHasta"] = fecha_hasta.strip()

        data = await self._async_get(ENDPOINT_OPERACIONES, params=params)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("operaciones", "items", "data"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        return []

    async def async_get_panel_cotizaciones(
        self,
        instrumento: str,
        panel: str,
        pais: str = "Argentina",
    ) -> list[dict[str, Any]]:
        """Fetch a full market quote panel (e.g., Acciones/Merval/Argentina)."""
        endpoint = ENDPOINT_PANEL_COTIZACIONES.format(
            instrumento=instrumento.strip(),
            panel=panel.strip(),
            pais=(pais or "Argentina").strip(),
        )
        data = await self._async_get(endpoint)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            titulos = data.get("titulos")
            if isinstance(titulos, list):
                return [item for item in titulos if isinstance(item, dict)]
        return []

    async def async_get_serie_historica(
        self,
        simbolo: str,
        fecha_desde: str,
        fecha_hasta: str,
        mercado: str = DEFAULT_MARKET,
        ajustada: str = "ajustada",
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLCV quote series for a security."""
        clean_ajustada = "sinAjustar" if str(ajustada).strip().lower() in ("sinajustar", "sin_ajustar") else "ajustada"
        endpoint = ENDPOINT_SERIE_HISTORICA.format(
            mercado=(mercado or DEFAULT_MARKET).strip(),
            simbolo=simbolo.strip().upper(),
            fecha_desde=fecha_desde.strip(),
            fecha_hasta=fecha_hasta.strip(),
            ajustada=clean_ajustada,
        )
        data = await self._async_get(endpoint)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def async_get_inflacion(self, url: str) -> dict[str, Any] | None:
        """Fetch inflation time series from ArgentinaDatos and return latest entry."""
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with self._session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "ArgentinaDatos inflation endpoint %s returned HTTP %s",
                        url,
                        response.status,
                    )
                    return None
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.warning("Failed to fetch ArgentinaDatos inflation (%s): %s", url, err)
            return None

        if not isinstance(payload, list) or not payload:
            return None

        valid_entries = [
            item for item in payload if isinstance(item, dict) and item.get("valor") is not None
        ]
        if not valid_entries:
            return None

        # Ensure chronological order by fecha ISO string
        valid_entries.sort(key=lambda x: str(x.get("fecha") or ""))
        latest = valid_entries[-1]
        previous = valid_entries[-2] if len(valid_entries) >= 2 else {}

        valor = safe_float(latest.get("valor"))
        if valor is None:
            return None

        return {
            "valor": round(valor, 2),
            "fecha": latest.get("fecha"),
            "valor_anterior": safe_float(previous.get("valor")),
            "fecha_anterior": previous.get("fecha"),
            "fuente": "ArgentinaDatos",
        }

    async def async_get_dolar_historico(
        self, url: str
    ) -> list[dict[str, Any]] | None:
        """Fetch historical dollar quotes list from ArgentinaDatos."""
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        try:
            async with self._session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "ArgentinaDatos dollar endpoint %s returned HTTP %s",
                        url,
                        response.status,
                    )
                    return None
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.warning(
                "Failed to fetch ArgentinaDatos dollar series (%s): %s", url, err
            )
            return None

        if not isinstance(payload, list) or not payload:
            return None
        return [item for item in payload if isinstance(item, dict)]


def safe_float(value: Any) -> float | None:
    """Safely convert an API numeric value to float."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_web_caucion(payload: Any, days: int) -> dict[str, Any] | None:
    """Normalize response from iol.invertironline.com/Mercado/GetCaucionPuntas."""
    if not payload:
        return None
    if isinstance(payload, list):
        first = payload[0] if payload and isinstance(payload[0], dict) else None
        if not first:
            return None
        payload = first
    if not isinstance(payload, dict):
        return None

    # Handle nested Data / Result wrappers if present
    for wrapper in ("Data", "data", "Result", "result"):
        if isinstance(payload.get(wrapper), dict):
            payload = payload[wrapper]
            break

    tasa_col = safe_float(
        next(
            (
                payload.get(k)
                for k in (
                    "tasaColocadora",
                    "TasaColocadora",
                    "tasa",
                    "Tasa",
                    "tasaPromedio",
                    "TasaPromedio",
                    "ultimoPrecio",
                    "UltimoPrecio",
                )
                if payload.get(k) is not None
            ),
            None,
        )
    )
    tasa_tom = safe_float(
        next(
            (
                payload.get(k)
                for k in ("tasaTomadora", "TasaTomadora")
                if payload.get(k) is not None
            ),
            None,
        )
    )
    bid = safe_float(
        next(
            (
                payload.get(k)
                for k in ("precioCompra", "PrecioCompra", "tasaCompra", "TasaCompra")
                if payload.get(k) is not None
            ),
            None,
        )
    )
    ask = safe_float(
        next(
            (
                payload.get(k)
                for k in ("precioVenta", "PrecioVenta", "tasaVenta", "TasaVenta")
                if payload.get(k) is not None
            ),
            None,
        )
    )

    puntas = payload.get("puntas") or payload.get("Puntas")
    if isinstance(puntas, list) and puntas and isinstance(puntas[0], dict):
        p0 = puntas[0]
        bid = bid if bid is not None else safe_float(p0.get("precioCompra") or p0.get("PrecioCompra") or p0.get("tasaCompra"))
        ask = ask if ask is not None else safe_float(p0.get("precioVenta") or p0.get("PrecioVenta") or p0.get("tasaVenta"))

    if tasa_col is None:
        tasa_col = bid
    if tasa_col is None or tasa_col <= 0:
        return None

    return {
        "plazo": days,
        "moneda": "pesos",
        "tasaColocadora": tasa_col,
        "tasaTomadora": tasa_tom if tasa_tom is not None else ask,
        "montoOperado": safe_float(
            payload.get("montoOperado")
            or payload.get("MontoOperado")
            or payload.get("volumen")
            or payload.get("Volumen")
        ),
        "puntas": [{"precioCompra": bid, "precioVenta": ask}],
        "fechaHora": payload.get("fechaHora") or payload.get("FechaHora"),
    }


def extract_dolar_rate(data: Any) -> float | None:
    """Extract a numeric dollar exchange rate from various IOL response shapes."""
    if isinstance(data, (int, float)):
        return float(data)
    if isinstance(data, dict):
        for key in (
            "valor",
            "cotizacion",
            "venta",
            "compra",
            "ultimoPrecio",
            "precio",
            "ccl",
            "mep",
        ):
            val = safe_float(data.get(key))
            if val is not None and val > 0:
                return val
    return None
