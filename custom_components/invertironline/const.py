"""Constants for the InvertirOnline (IOL) integration."""

from __future__ import annotations

DOMAIN = "invertironline"
API_BASE_URL = "https://api.invertironline.com"

# Rate limiting & token lifecycle
MIN_SCAN_INTERVAL_MINUTES = 15
DEFAULT_SCAN_INTERVAL_MINUTES = 15
TOKEN_REFRESH_MARGIN_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 20

# Argentina market polling window (America/Argentina/Buenos_Aires, Mon-Fri)
MARKET_TIMEZONE = "America/Argentina/Buenos_Aires"
MARKET_OPEN_HOUR = 10
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 18
MARKET_CLOSE_MINUTE = 30

# BYMA regular trading session hours (America/Argentina/Buenos_Aires, Mon-Fri)
BYMA_OPEN_HOUR = 11
BYMA_OPEN_MINUTE = 0
BYMA_CLOSE_HOUR = 17
BYMA_CLOSE_MINUTE = 0

# Configuration & Options keys
CONF_EXTRA_TICKERS = "extra_tickers"
CONF_SCAN_INTERVAL = "scan_interval_minutes"

# Markets & Reference Instruments
DEFAULT_MARKET = "bCBA"
SPY_SYMBOL = "SPY"
SPY_CEDEAR_RATIO = 20.0

# Caución nominal terms and holiday/weekend fallback search windows (min_days, max_days)
CAUCION_TERMS: tuple[int, ...] = (1, 7, 14, 30, 60)
CAUCION_TERM_WINDOWS: dict[int, tuple[int, int]] = {
    1: (1, 5),
    7: (6, 11),
    14: (12, 18),
    30: (26, 36),
    60: (50, 70),
}

# Endpoints (Read-Only ONLY — trading endpoints are strictly prohibited)
ENDPOINT_TOKEN = "/token"
ENDPOINT_CAUCIONES = "/api/v2/Cotizaciones/cauciones/todas/argentina"
ENDPOINT_CAUCIONES_ALT = "/api/v2/Cotizaciones/cauciones/Argentina"
ENDPOINT_DOLAR_MEP = "/api/v2/Cotizaciones/Dolar/Mep"
ENDPOINT_DOLAR_COTIZACIONES = "/api/v2/Cotizaciones/Dolar"
ENDPOINT_ESTADO_CUENTA = "/api/v2/estadocuenta"
ENDPOINT_PORTAFOLIO = "/api/v2/portafolio/Argentina"
ENDPOINT_COTIZACION_TITULO = "/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion"
ENDPOINT_OPERACIONES = "/api/v2/operaciones"
ENDPOINT_PANEL_COTIZACIONES = "/api/v2/Cotizaciones/{instrumento}/{panel}/{pais}"
ENDPOINT_SERIE_HISTORICA = (
    "/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/"
    "{fecha_desde}/{fecha_hasta}/{ajustada}"
)

# ArgentinaDatos public macro endpoints (Read-Only, no IOL quota usage)
ARGENTINADATOS_INFLACION_MENSUAL_URL = (
    "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
)
ARGENTINADATOS_INFLACION_INTERANUAL_URL = (
    "https://api.argentinadatos.com/v1/finanzas/indices/inflacionInteranual"
)
ARGENTINADATOS_DOLAR_MEP_URL = (
    "https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa"
)
INFLACION_CACHE_HOURS = 12
