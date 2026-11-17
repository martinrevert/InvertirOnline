"""DataUpdateCoordinator for InvertirOnline (IOL)."""

from __future__ import annotations

import asyncio
from datetime import datetime, time as dt_time, timedelta
import logging
import re
from typing import Any
import unicodedata
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    IOLApiClient,
    IOLApiError,
    IOLAuthError,
    extract_dolar_rate,
    safe_float,
)
from .const import (
    ARGENTINADATOS_INFLACION_INTERANUAL_URL,
    ARGENTINADATOS_INFLACION_MENSUAL_URL,
    CAUCION_TERM_WINDOWS,
    CAUCION_TERMS,
    CONF_EXTRA_TICKERS,
    CONF_SCAN_INTERVAL,
    DEFAULT_MARKET,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    INFLACION_CACHE_HOURS,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_TIMEZONE,
    MIN_SCAN_INTERVAL_MINUTES,
    SPY_CEDEAR_RATIO,
    SPY_SYMBOL,
)

_LOGGER = logging.getLogger(__name__)


def parse_extra_tickers(raw_tickers: list[str] | str | None) -> list[tuple[str, str]]:
    """Parse configured extra tickers into (mercado, simbolo) tuples."""
    if not raw_tickers:
        return []
    if isinstance(raw_tickers, str):
        items = [part.strip() for part in raw_tickers.split(",") if part.strip()]
    else:
        items = [str(part).strip() for part in raw_tickers if str(part).strip()]

    parsed: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if ":" in item:
            mercado, simbolo = item.split(":", 1)
            mercado = mercado.strip() or DEFAULT_MARKET
            simbolo = simbolo.strip().upper()
        else:
            mercado = DEFAULT_MARKET
            simbolo = item.strip().upper()

        if not simbolo:
            continue
        pair = (mercado, simbolo)
        if pair not in seen:
            seen.add(pair)
            parsed.append(pair)
    return parsed


def _extract_puntas(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract best bid/ask prices or rates from IOL puntas structures."""
    puntas = raw.get("puntas")
    if isinstance(puntas, list) and puntas:
        first = puntas[0] if isinstance(puntas[0], dict) else {}
        bid = safe_float(first.get("precioCompra") or first.get("tasaCompra"))
        ask = safe_float(first.get("precioVenta") or first.get("tasaVenta"))
        return bid, ask
    if isinstance(puntas, dict):
        bid = safe_float(puntas.get("precioCompra") or puntas.get("tasaCompra"))
        ask = safe_float(puntas.get("precioVenta") or puntas.get("tasaVenta"))
        return bid, ask

    bid = safe_float(raw.get("precioCompra") or raw.get("puntaCompradora"))
    ask = safe_float(raw.get("precioVenta") or raw.get("puntaVendedora"))
    return bid, ask


def normalize_quote(
    raw: dict[str, Any], simbolo: str, mercado: str = DEFAULT_MARKET
) -> dict[str, Any]:
    """Normalize an IOL title quote payload into a flat dictionary."""
    bid, ask = _extract_puntas(raw)
    ultimo = safe_float(
        raw.get("ultimoPrecio") if raw.get("ultimoPrecio") is not None else raw.get("ultimo")
    )
    return {
        "simbolo": simbolo.upper(),
        "mercado": mercado,
        "descripcion": raw.get("descripcionTitulo") or raw.get("descripcion") or simbolo.upper(),
        "ultimo_precio": round(ultimo, 2) if ultimo is not None else None,
        "moneda": raw.get("moneda") or ("ARS" if mercado == DEFAULT_MARKET else "USD"),
        "variacion_diaria": safe_float(
            raw.get("variacion")
            if raw.get("variacion") is not None
            else raw.get("variacionPorcentual")
        ),
        "punta_compradora": bid,
        "punta_vendedora": ask,
        "volumen_nominal": safe_float(raw.get("volumenNominal") or raw.get("volumen")),
        "precio_apertura": safe_float(raw.get("apertura")),
        "precio_maximo": safe_float(raw.get("maximo")),
        "precio_minimo": safe_float(raw.get("minimo")),
        "ultimo_cierre": safe_float(raw.get("cierreAnterior")),
        "fecha_hora": raw.get("fechaHora"),
    }


def _extract_caucion_days(item: dict[str, Any]) -> int | None:
    """Extract term in days from explicit fields or symbol/description text."""
    raw_days = item.get("plazo") if item.get("plazo") is not None else item.get("plazoDias")
    if raw_days is not None:
        try:
            days = int(raw_days)
            if days > 0:
                return days
        except (TypeError, ValueError):
            pass

    for field in ("simbolo", "descripcion", "descripcionTitulo"):
        text = str(item.get(field) or "")
        match = re.search(r"\b(\d{1,3})\s*(?:d[ií]as?|d)\b", text, re.IGNORECASE)
        if match:
            days = int(match.group(1))
            if days > 0:
                return days
    return None


def _normalize_text(value: Any) -> str:
    """Lowercase and strip accents for resilient Spanish text matching."""
    text = str(value or "").lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _is_ars_caucion(item: dict[str, Any]) -> bool:
    """Filter out USD-denominated cauciones when resolving ARS caución rates."""
    fields = " ".join(
        _normalize_text(item.get(k))
        for k in ("moneda", "simbolo", "descripcion", "descripcionTitulo")
    )
    if any(token in fields for token in ("dolar", "usd", "u$s", "us$", "dol ")):
        return False
    return True


def _caucion_candidate_score(item: dict[str, Any]) -> tuple[int, int, float, float]:
    """Rank ARS caución candidates when multiple entries share the same term."""
    fields = " ".join(
        _normalize_text(item.get(k))
        for k in ("moneda", "simbolo", "descripcion", "descripcionTitulo")
    )
    explicit_ars = 1 if ("peso" in fields or "ars" in fields) else 0
    monto = (
        safe_float(
            item.get("montoOperado")
            or item.get("montoContado")
            or item.get("volumenNominal")
            or item.get("volumen")
        )
        or 0.0
    )
    bid, _ = _extract_puntas(item)
    tasa = (
        safe_float(
            next(
                (
                    item.get(k)
                    for k in ("tasaColocadora", "tasaPromedio", "ultimoPrecio", "ultimo")
                    if item.get(k) is not None
                ),
                bid,
            )
        )
        or 0.0
    )
    # ARS caución TNA in Argentina is > 5%; USD caución rates are typically 0.5% - 4%
    plausible_ars_rate = 1 if tasa >= 5.0 else 0
    return (explicit_ars, plausible_ars_rate, monto, tasa)


def resolve_cauciones(panel: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Resolve nominal caución terms (1, 7, 14, 30, 60) with holiday/weekend fallback."""
    by_days: dict[int, dict[str, Any]] = {}
    for item in panel:
        if not _is_ars_caucion(item):
            continue
        days = _extract_caucion_days(item)
        if days is None or days <= 0:
            continue
        score = _caucion_candidate_score(item)
        # Skip implausibly low rates (< 5% TNA, typical of USD cauciones)
        if score[1] == 0:
            continue
        if days not in by_days or score > _caucion_candidate_score(by_days[days]):
            by_days[days] = item

    resolved: dict[int, dict[str, Any]] = {}
    for nominal in CAUCION_TERMS:
        chosen_days: int | None = None
        if nominal in by_days:
            chosen_days = nominal
        else:
            min_d, max_d = CAUCION_TERM_WINDOWS.get(nominal, (nominal, nominal))
            # Prefer immediate next business day (>= nominal), otherwise closest in window
            forward = sorted(d for d in by_days if nominal <= d <= max_d)
            backward = sorted((d for d in by_days if min_d <= d < nominal), reverse=True)
            if forward:
                chosen_days = forward[0]
            elif backward:
                chosen_days = backward[0]

        if chosen_days is None:
            continue

        item = by_days[chosen_days]
        bid, ask = _extract_puntas(item)
        tasa_colocadora = safe_float(
            next(
                (
                    item.get(k)
                    for k in ("tasaColocadora", "tasaPromedio", "ultimoPrecio", "ultimo")
                    if item.get(k) is not None
                ),
                bid,
            )
        )

        tasa_val = round(tasa_colocadora, 2) if tasa_colocadora is not None else None
        if tasa_val is not None and tasa_val < 5.0:
            _LOGGER.warning(
                "Low caución rate (%s) for %sD (real %sD); raw item fields: %s",
                tasa_val,
                nominal,
                chosen_days,
                {
                    k: item.get(k)
                    for k in (
                        "simbolo",
                        "descripcion",
                        "moneda",
                        "plazo",
                        "ultimoPrecio",
                        "tasaColocadora",
                        "tasaPromedio",
                        "montoOperado",
                    )
                    if k in item
                },
            )

        resolved[nominal] = {
            "tasa_colocadora": tasa_val,
            "tasa_tomadora": safe_float(
                item.get("tasaTomadora") if item.get("tasaTomadora") is not None else ask
            ),
            "monto_operado": safe_float(
                item.get("montoOperado")
                or item.get("montoContado")
                or item.get("volumenNominal")
                or item.get("volumen")
            ),
            "punta_compradora": bid,
            "punta_vendedora": ask,
            "plazo_dias": nominal,
            "plazo_dias_real": chosen_days,
            "ultima_actualizacion": item.get("fechaHora") or item.get("fechaVencimiento"),
        }

    if panel and not resolved:
        sample = panel[0]
        _LOGGER.warning(
            "Cauciones panel returned %d items but none resolved. Sample keys=%s, sample=%s",
            len(panel),
            list(sample.keys()),
            {k: sample.get(k) for k in ("simbolo", "descripcion", "plazo", "plazoDias", "moneda", "ultimoPrecio")},
        )

    return resolved


def _extract_account_summary(
    estado_cuenta: dict[str, Any], portafolio: dict[str, Any]
) -> dict[str, Any]:
    """Extract consolidated ARS/USD balances and holdings from IOL account endpoints."""
    numero_cuenta = None
    disponible_pesos = 0.0
    disponible_dolares = 0.0
    total_ars_estado = safe_float(estado_cuenta.get("totalEnPesos"))

    cuentas = estado_cuenta.get("cuentas")
    if isinstance(cuentas, list):
        for cuenta in cuentas:
            if not isinstance(cuenta, dict):
                continue
            if numero_cuenta is None and cuenta.get("numero") is not None:
                numero_cuenta = str(cuenta.get("numero"))

            moneda = str(cuenta.get("moneda") or "").lower()
            disponible = safe_float(cuenta.get("disponible")) or 0.0
            if "peso" in moneda or "ars" in moneda:
                disponible_pesos += disponible
            elif "dolar" in moneda or "usd" in moneda:
                disponible_dolares += disponible

    if numero_cuenta is None and estado_cuenta.get("numeroCuenta") is not None:
        numero_cuenta = str(estado_cuenta.get("numeroCuenta"))

    tenencia_titulos_pesos = 0.0
    activos = portafolio.get("activos")
    if isinstance(activos, list):
        for activo in activos:
            if not isinstance(activo, dict):
                continue
            val = safe_float(activo.get("valorizado"))
            if val is not None:
                tenencia_titulos_pesos += val

    if total_ars_estado is not None and total_ars_estado > 0:
        total_ars = total_ars_estado
    else:
        total_ars = disponible_pesos + tenencia_titulos_pesos

    return {
        "numero_cuenta": numero_cuenta or "default",
        "disponible_pesos": round(disponible_pesos, 2),
        "disponible_dolares": round(disponible_dolares, 2),
        "tenencia_titulos_pesos": round(tenencia_titulos_pesos, 2),
        "total_ars": round(total_ars, 2),
    }


def normalize_portfolio(
    raw: dict[str, Any], tipo_filtro: str | None = None
) -> dict[str, Any]:
    """Normalize IOL portfolio response into a compact, sorted structure."""
    raw_activos = raw.get("activos")
    if not isinstance(raw_activos, list):
        raw_activos = []

    filtro_norm = _normalize_text(tipo_filtro).strip() if tipo_filtro else ""
    parsed_items: list[dict[str, Any]] = []

    for item in raw_activos:
        if not isinstance(item, dict):
            continue
        titulo = item.get("titulo") if isinstance(item.get("titulo"), dict) else {}
        simbolo = str(titulo.get("simbolo") or item.get("simbolo") or "").upper()
        if not simbolo:
            continue

        tipo = str(titulo.get("tipo") or item.get("tipo") or "Otros")
        if filtro_norm and filtro_norm not in _normalize_text(tipo):
            continue

        valorizado = safe_float(item.get("valorizado")) or 0.0
        ganancia_dinero = safe_float(item.get("gananciaDinero"))
        ganancia_pct = safe_float(item.get("gananciaPorcentaje"))

        parsed_items.append(
            {
                "simbolo": simbolo,
                "descripcion": titulo.get("descripcion") or item.get("descripcion") or simbolo,
                "tipo": tipo,
                "cantidad": safe_float(item.get("cantidad")),
                "ultimo_precio": safe_float(item.get("ultimoPrecio")),
                "valorizado": round(valorizado, 2),
                "variacion_diaria": safe_float(item.get("variacionDiaria")),
                "ganancia_dinero": round(ganancia_dinero, 2) if ganancia_dinero is not None else None,
                "ganancia_porcentaje": round(ganancia_pct, 2) if ganancia_pct is not None else None,
                "moneda": titulo.get("moneda") or item.get("moneda") or "ARS",
            }
        )

    parsed_items.sort(key=lambda x: x["valorizado"], reverse=True)

    total_valorizado = round(sum(x["valorizado"] for x in parsed_items), 2)
    ganancia_total = round(
        sum(x["ganancia_dinero"] for x in parsed_items if x["ganancia_dinero"] is not None),
        2,
    )

    distribucion_raw: dict[str, float] = {}
    for entry in parsed_items:
        peso = (
            round((entry["valorizado"] / total_valorizado) * 100, 2)
            if total_valorizado > 0
            else 0.0
        )
        entry["peso_porcentaje"] = peso
        distribucion_raw[entry["tipo"]] = distribucion_raw.get(entry["tipo"], 0.0) + entry["valorizado"]

    distribucion_por_tipo = {
        k: {
            "valorizado": round(v, 2),
            "porcentaje": round((v / total_valorizado) * 100, 2) if total_valorizado > 0 else 0.0,
        }
        for k, v in sorted(distribucion_raw.items(), key=lambda kv: kv[1], reverse=True)
    }

    return {
        "pais": raw.get("pais") or "argentina",
        "cantidad_activos": len(parsed_items),
        "total_valorizado": total_valorizado,
        "ganancia_total": ganancia_total,
        "distribucion_por_tipo": distribucion_por_tipo,
        "activos": parsed_items,
    }


def _extract_direct_ccl(
    estado_cuenta: dict[str, Any], dolar_list: Any
) -> float | None:
    """Check if IOL exposes a direct CCL rate in estadocuenta or Cotizaciones/Dolar."""
    for key in ("cotizacionDolarCCL", "dolarCCL", "ccl"):
        val = safe_float(estado_cuenta.get(key))
        if val is not None and val > 0:
            return val

    if isinstance(dolar_list, list):
        for entry in dolar_list:
            if not isinstance(entry, dict):
                continue
            desc = str(
                entry.get("descripcion")
                or entry.get("tipo")
                or entry.get("nombre")
                or ""
            ).lower()
            if "ccl" in desc or "liquidacion" in desc or "liquidación" in desc:
                rate = extract_dolar_rate(entry)
                if rate is not None and rate > 0:
                    return rate
    elif isinstance(dolar_list, dict):
        for key in ("ccl", "CCL", "dolarCCL"):
            if key in dolar_list:
                rate = extract_dolar_rate(dolar_list[key])
                if rate is not None and rate > 0:
                    return rate
    return None


def is_within_market_window(now: datetime | None = None) -> bool:
    """Return True during Mon-Fri 10:30-18:30 America/Argentina/Buenos_Aires."""
    tz = ZoneInfo(MARKET_TIMEZONE)
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    if current.weekday() >= 5:
        return False
    current_time = current.time()
    open_time = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    close_time = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
    return open_time <= current_time <= close_time


class IOLDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Centralized coordinator that polls IOL API v2 within rate-limit bounds."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: IOLApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator with enforced >= 15 min interval."""
        configured_minutes = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        interval_minutes = max(MIN_SCAN_INTERVAL_MINUTES, int(configured_minutes))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=interval_minutes),
        )
        self.api = api
        self.config_entry = entry
        self._last_inflacion_fetch: datetime | None = None

    async def _async_get_quote_cached(
        self,
        simbolo: str,
        mercado: str,
        quote_cache: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Fetch a title quote once per update cycle and reuse within the same cycle."""
        key = (mercado, simbolo.upper())
        if key not in quote_cache:
            quote_cache[key] = await self.api.async_get_quote(simbolo, mercado)
        return quote_cache[key]

    async def _async_resolve_mep_rate(
        self,
        direct_mep: float | None,
        quote_cache: dict[tuple[str, str], dict[str, Any]],
    ) -> float | None:
        """Resolve Dólar MEP rate: direct endpoint first, AL30/AL30D ratio fallback."""
        if direct_mep is not None and direct_mep > 0:
            return round(direct_mep, 2)

        for sym_ars, sym_usd in (("AL30", "AL30D"), ("GD30", "GD30D")):
            try:
                q_ars, q_usd = await asyncio.gather(
                    self._async_get_quote_cached(sym_ars, DEFAULT_MARKET, quote_cache),
                    self._async_get_quote_cached(sym_usd, DEFAULT_MARKET, quote_cache),
                )
                p_ars = safe_float(q_ars.get("ultimoPrecio") or q_ars.get("cierreAnterior"))
                p_usd = safe_float(q_usd.get("ultimoPrecio") or q_usd.get("cierreAnterior"))
                if p_ars and p_usd and p_usd > 0:
                    return round(p_ars / p_usd, 2)
                _LOGGER.warning(
                    "MEP fallback %s/%s returned invalid prices: %s=%s, %s=%s",
                    sym_ars,
                    sym_usd,
                    sym_ars,
                    p_ars,
                    sym_usd,
                    p_usd,
                )
            except IOLAuthError:
                raise
            except IOLApiError as err:
                _LOGGER.warning("%s/%s MEP fallback unavailable: %s", sym_ars, sym_usd, err)
        return None

    async def _async_resolve_ccl_rate(
        self,
        estado_cuenta: dict[str, Any],
        dolar_list: Any,
        spy_bcba: dict[str, Any] | None,
        quote_cache: dict[tuple[str, str], dict[str, Any]],
    ) -> tuple[float | None, str | None]:
        """Resolve Dólar CCL rate: direct API first, implicit ratio fallback second."""
        direct_ccl = _extract_direct_ccl(estado_cuenta, dolar_list)
        if direct_ccl is not None:
            return round(direct_ccl, 2), "api_directa"

        # Fallback 1: AL30 / AL30C implicit ratio (reuses AL30 from quote_cache)
        try:
            al30_ars, al30_ccl = await asyncio.gather(
                self._async_get_quote_cached("AL30", DEFAULT_MARKET, quote_cache),
                self._async_get_quote_cached("AL30C", DEFAULT_MARKET, quote_cache),
            )
            p_ars = safe_float(al30_ars.get("ultimoPrecio"))
            p_ccl = safe_float(al30_ccl.get("ultimoPrecio"))
            if p_ars and p_ccl and p_ccl > 0:
                return round(p_ars / p_ccl, 2), "ratio_implicito"
        except IOLAuthError:
            raise
        except IOLApiError as err:
            _LOGGER.debug("AL30/AL30C implicit CCL fallback unavailable: %s", err)

        # Fallback 2: SPY (bCBA ARS) vs SPY (NYSE USD) adjusted by 20:1 CEDEAR ratio
        if spy_bcba and spy_bcba.get("ultimo_precio"):
            try:
                spy_nyse = await self._async_get_quote_cached(
                    SPY_SYMBOL, "NYSE", quote_cache
                )
                p_nyse = safe_float(spy_nyse.get("ultimoPrecio"))
                if p_nyse and p_nyse > 0:
                    implicit = (spy_bcba["ultimo_precio"] * SPY_CEDEAR_RATIO) / p_nyse
                    return round(implicit, 2), "ratio_implicito"
            except IOLAuthError:
                raise
            except IOLApiError as err:
                _LOGGER.debug("SPY NYSE implicit CCL fallback unavailable: %s", err)

        return None, None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch consolidated market and account data from IOL API v2."""
        # Outside Mon-Fri 10:30-18:30 ART, skip polling to preserve API quota
        # (Always allow initial refresh when self.data is None on startup)
        if self.data is not None and not is_within_market_window():
            _LOGGER.debug(
                "Outside Argentina market window (Mon-Fri 10:30-18:30 ART); skipping IOL poll"
            )
            return self.data

        try:
            await self.api.async_ensure_valid_token()
        except IOLAuthError as err:
            raise ConfigEntryAuthFailed(
                "InvertirOnline authentication failed; please reauthenticate"
            ) from err
        except IOLApiError as err:
            raise UpdateFailed(f"Error ensuring IOL token: {err}") from err

        extra_tickers = parse_extra_tickers(
            self.config_entry.options.get(CONF_EXTRA_TICKERS)
        )
        quote_cache: dict[tuple[str, str], dict[str, Any]] = {}

        # Core endpoints in parallel
        core_tasks = [
            self.api.async_get_cauciones(),
            self._async_get_quote_cached(SPY_SYMBOL, DEFAULT_MARKET, quote_cache),
            self.api.async_get_dolar_mep(),
            self.api.async_get_estado_cuenta(),
            self.api.async_get_portafolio(),
            self.api.async_get_dolar_cotizaciones(),
        ]
        results = await asyncio.gather(*core_tasks, return_exceptions=True)

        # Propagate auth failures immediately
        for res in results:
            if isinstance(res, IOLAuthError):
                raise ConfigEntryAuthFailed(
                    "InvertirOnline session expired or invalid"
                ) from res

        cauciones_raw, spy_raw, mep_raw, estado_raw, portafolio_raw, dolar_list_raw = results

        # If every core endpoint failed, abort the update cycle
        core_errors = [
            res
            for res in (cauciones_raw, spy_raw, mep_raw, estado_raw, portafolio_raw)
            if isinstance(res, Exception)
        ]
        if len(core_errors) == 5:
            raise UpdateFailed(f"All IOL endpoints failed: {core_errors[0]}")

        previous_data = self.data or {}

        if isinstance(cauciones_raw, Exception):
            _LOGGER.warning("Failed to fetch cauciones: %s", cauciones_raw)
            cauciones = previous_data.get("cauciones", {})
        else:
            cauciones = resolve_cauciones(cauciones_raw)

        if isinstance(spy_raw, Exception):
            _LOGGER.warning("Failed to fetch CEDEAR SPY: %s", spy_raw)
            spy_quote = previous_data.get("spy", {})
        else:
            spy_quote = normalize_quote(spy_raw, SPY_SYMBOL, DEFAULT_MARKET)

        if isinstance(mep_raw, Exception):
            _LOGGER.warning("Failed to fetch Dólar MEP: %s", mep_raw)
            dolar_mep = previous_data.get("dolar_mep")
        else:
            dolar_mep = await self._async_resolve_mep_rate(mep_raw, quote_cache)
            if dolar_mep is None:
                dolar_mep = previous_data.get("dolar_mep")

        estado_cuenta = (
            {} if isinstance(estado_raw, Exception) else estado_raw
        )
        if isinstance(estado_raw, Exception):
            _LOGGER.warning("Failed to fetch estado de cuenta: %s", estado_raw)

        portafolio = (
            {} if isinstance(portafolio_raw, Exception) else portafolio_raw
        )
        if isinstance(portafolio_raw, Exception):
            _LOGGER.warning("Failed to fetch portafolio: %s", portafolio_raw)

        if isinstance(estado_raw, Exception) and isinstance(portafolio_raw, Exception):
            account = previous_data.get("account", _extract_account_summary({}, {}))
        else:
            account = _extract_account_summary(estado_cuenta, portafolio)

        dolar_list = None if isinstance(dolar_list_raw, Exception) else dolar_list_raw
        ccl_rate, ccl_source = await self._async_resolve_ccl_rate(
            estado_cuenta, dolar_list, spy_quote, quote_cache
        )
        if ccl_rate is None:
            ccl_rate = previous_data.get("dolar_ccl")
            ccl_source = previous_data.get("fuente_ccl")

        total_ars = account.get("total_ars", 0.0)
        total_usd_mep = (
            round(total_ars / dolar_mep, 2)
            if dolar_mep is not None and dolar_mep > 0
            else None
        )
        total_usd_ccl = (
            round(total_ars / ccl_rate, 2)
            if ccl_rate is not None and ccl_rate > 0
            else None
        )

        # Extra user-configured tickers (isolated failures, reusing intra-cycle quote_cache)
        extra_quotes: dict[str, dict[str, Any]] = {}
        if extra_tickers:
            ticker_results = await asyncio.gather(
                *(
                    self._async_get_quote_cached(sym, mkt, quote_cache)
                    for mkt, sym in extra_tickers
                ),
                return_exceptions=True,
            )
            for (mkt, sym), t_res in zip(extra_tickers, ticker_results):
                key = f"{mkt}:{sym}"
                if isinstance(t_res, IOLAuthError):
                    raise ConfigEntryAuthFailed(
                        "InvertirOnline session expired while fetching tickers"
                    ) from t_res
                if isinstance(t_res, Exception):
                    _LOGGER.warning("Failed to fetch extra ticker %s: %s", key, t_res)
                    if key in previous_data.get("extra_tickers", {}):
                        extra_quotes[key] = previous_data["extra_tickers"][key]
                else:
                    extra_quotes[key] = normalize_quote(t_res, sym, mkt)

        # ArgentinaDatos inflation (refreshed at most once every INFLACION_CACHE_HOURS)
        inflacion_mensual = previous_data.get("inflacion_mensual")
        inflacion_interanual = previous_data.get("inflacion_interanual")
        now_utc = datetime.now(ZoneInfo("UTC"))
        should_fetch_inflacion = (
            self._last_inflacion_fetch is None
            or inflacion_mensual is None
            or inflacion_interanual is None
            or (now_utc - self._last_inflacion_fetch)
            >= timedelta(hours=INFLACION_CACHE_HOURS)
        )
        if should_fetch_inflacion:
            inf_m_res, inf_i_res = await asyncio.gather(
                self.api.async_get_inflacion(ARGENTINADATOS_INFLACION_MENSUAL_URL),
                self.api.async_get_inflacion(ARGENTINADATOS_INFLACION_INTERANUAL_URL),
                return_exceptions=True,
            )
            if isinstance(inf_m_res, dict):
                inflacion_mensual = inf_m_res
            if isinstance(inf_i_res, dict):
                inflacion_interanual = inf_i_res
            if isinstance(inf_m_res, dict) or isinstance(inf_i_res, dict):
                self._last_inflacion_fetch = now_utc

        return {
            "cauciones": cauciones,
            "spy": spy_quote,
            "account": account,
            "portafolio": normalize_portfolio(portafolio) if portafolio else previous_data.get("portafolio", {}),
            "dolar_mep": round(dolar_mep, 2) if dolar_mep is not None else None,
            "total_usd_mep": total_usd_mep,
            "dolar_ccl": ccl_rate,
            "fuente_ccl": ccl_source,
            "total_usd_ccl": total_usd_ccl,
            "extra_tickers": extra_quotes,
            "inflacion_mensual": inflacion_mensual,
            "inflacion_interanual": inflacion_interanual,
        }
