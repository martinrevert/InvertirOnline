"""Sensor platform for InvertirOnline (IOL)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CAUCION_TERMS, CONF_EXTRA_TICKERS, DEFAULT_MARKET
from .coordinator import (
    IOLDataUpdateCoordinator,
    is_within_market_window,
    parse_extra_tickers,
)
from .entity import IOLEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up InvertirOnline sensor entities from a config entry."""
    coordinator: IOLDataUpdateCoordinator = entry.runtime_data["coordinator"]

    entities: list[SensorEntity] = [
        IOLCaucionSensor(coordinator, term) for term in CAUCION_TERMS
    ]
    entities.extend(
        [
            IOLCedearSpySensor(coordinator),
            IOLAccountTotalArsSensor(coordinator),
            IOLAccountTotalUsdMepSensor(coordinator),
            IOLAccountTotalUsdCclSensor(coordinator),
            IOLDolarMepSensor(coordinator),
            IOLDolarCclSensor(coordinator),
            IOLDisponibleArsSensor(coordinator),
            IOLDisponibleUsdSensor(coordinator),
            IOLPortafolioGananciaSensor(coordinator),
            IOLInflacionMensualSensor(coordinator),
            IOLInflacionInteranualSensor(coordinator),
            IOLInflacionMensualUsdSensor(coordinator),
            IOLInflacionInteranualUsdSensor(coordinator),
            IOLUltimaActualizacionSensor(coordinator),
            IOLPortfolioSensor(coordinator),
        ]
    )

    extra_entities: list[IOLExtraTickerSensor] = []
    for mercado, simbolo in parse_extra_tickers(entry.options.get(CONF_EXTRA_TICKERS)):
        extra_entities.append(IOLExtraTickerSensor(coordinator, mercado, simbolo))
    entities.extend(extra_entities)

    # Remove orphaned extra-ticker entities no longer present in OptionsFlow
    ent_reg = er.async_get(hass)
    active_ticker_uids = {e.unique_id for e in extra_entities if e.unique_id}
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if "_ticker_" in reg_entry.unique_id and reg_entry.unique_id not in active_ticker_uids:
            ent_reg.async_remove(reg_entry.entity_id)

    async_add_entities(entities)


class IOLCaucionSensor(IOLEntity, SensorEntity):
    """Sensor representing BYMA caución placement rate for a nominal term."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:percent-circle-outline"

    def __init__(self, coordinator: IOLDataUpdateCoordinator, days: int) -> None:
        """Initialize the caución sensor."""
        super().__init__(coordinator, f"caucion_{days}d")
        self._days = days
        self._attr_name = f"Caución {days}D"
        self.entity_id = f"sensor.iol_caucion_{days}d"

    def _caucion_data(self) -> dict[str, Any]:
        """Return resolved caución data for this term."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("cauciones", {}).get(self._days, {})

    @property
    def native_value(self) -> float | None:
        """Return the placement TNA rate."""
        return self._caucion_data().get("tasa_colocadora")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional caución market attributes."""
        data = self._caucion_data()
        return {
            "tasa_tomadora": data.get("tasa_tomadora"),
            "monto_operado": data.get("monto_operado"),
            "punta_compradora": data.get("punta_compradora"),
            "punta_vendedora": data.get("punta_vendedora"),
            "plazo_dias": self._days,
            "plazo_dias_real": data.get("plazo_dias_real"),
            "ultima_actualizacion": data.get("ultima_actualizacion"),
        }


class IOLCedearSpySensor(IOLEntity, SensorEntity):
    """Sensor representing the CEDEAR SPY price in ARS."""

    _attr_name = "CEDEAR SPY"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the CEDEAR SPY sensor."""
        super().__init__(coordinator, "cedear_spy")
        self.entity_id = "sensor.iol_cedear_spy"

    def _spy_data(self) -> dict[str, Any]:
        """Return normalized SPY quote data."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("spy", {})

    @property
    def native_value(self) -> float | None:
        """Return last traded price in ARS."""
        return self._spy_data().get("ultimo_precio")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return market quote attributes for SPY."""
        data = self._spy_data()
        return {
            "variacion_diaria": data.get("variacion_diaria"),
            "punta_compradora": data.get("punta_compradora"),
            "punta_vendedora": data.get("punta_vendedora"),
            "volumen_nominal": data.get("volumen_nominal"),
            "precio_apertura": data.get("precio_apertura"),
            "precio_maximo": data.get("precio_maximo"),
            "precio_minimo": data.get("precio_minimo"),
            "ultimo_cierre": data.get("ultimo_cierre"),
        }


class IOLAccountTotalArsSensor(IOLEntity, SensorEntity):
    """Sensor representing total account valuation in ARS."""

    _attr_name = "Total Cuenta ARS"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the total ARS account sensor."""
        super().__init__(coordinator, "cuenta_total_ars")
        self.entity_id = "sensor.iol_cuenta_total_ars"

    def _account_data(self) -> dict[str, Any]:
        """Return consolidated account summary."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("account", {})

    @property
    def native_value(self) -> float | None:
        """Return total account valuation in ARS."""
        return self._account_data().get("total_ars")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return ARS balance breakdown."""
        data = self._account_data()
        return {
            "disponible_pesos": data.get("disponible_pesos"),
            "tenencia_titulos_pesos": data.get("tenencia_titulos_pesos"),
            "numero_cuenta": data.get("numero_cuenta"),
        }


class IOLAccountTotalUsdMepSensor(IOLEntity, SensorEntity):
    """Sensor representing total account valuation in USD MEP."""

    _attr_name = "Total Cuenta USD MEP"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the total USD MEP account sensor."""
        super().__init__(coordinator, "cuenta_total_usd_mep")
        self.entity_id = "sensor.iol_cuenta_total_usd_mep"

    @property
    def native_value(self) -> float | None:
        """Return total account valuation converted at Dólar MEP."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_usd_mep")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return MEP rate and liquid USD balance."""
        if not self.coordinator.data:
            return {}
        account = self.coordinator.data.get("account", {})
        return {
            "cotizacion_mep_utilizada": self.coordinator.data.get("dolar_mep"),
            "disponible_dolares": account.get("disponible_dolares"),
        }


class IOLAccountTotalUsdCclSensor(IOLEntity, SensorEntity):
    """Sensor representing total account valuation in USD CCL."""

    _attr_name = "Total Cuenta USD CCL"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the total USD CCL account sensor."""
        super().__init__(coordinator, "cuenta_total_usd_ccl")
        self.entity_id = "sensor.iol_cuenta_total_usd_ccl"

    @property
    def native_value(self) -> float | None:
        """Return total account valuation converted at Dólar CCL."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_usd_ccl")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return CCL rate and resolution source."""
        if not self.coordinator.data:
            return {}
        return {
            "cotizacion_ccl_implicita": self.coordinator.data.get("dolar_ccl"),
            "fuente_ccl": self.coordinator.data.get("fuente_ccl"),
        }


class IOLExtraTickerSensor(IOLEntity, SensorEntity):
    """Dynamic sensor for additional user-configured tickers via OptionsFlow."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(
        self,
        coordinator: IOLDataUpdateCoordinator,
        mercado: str,
        simbolo: str,
    ) -> None:
        """Initialize a configurable ticker sensor."""
        self._mercado = mercado
        self._simbolo = simbolo.upper()
        self._key = f"{mercado}:{self._simbolo}"

        slug = (
            self._simbolo.lower()
            if mercado == DEFAULT_MARKET
            else f"{mercado.lower()}_{self._simbolo.lower()}"
        )
        super().__init__(coordinator, f"ticker_{slug}")
        self._attr_name = f"Ticker {self._simbolo}"
        self.entity_id = f"sensor.iol_ticker_{slug}"

    def _quote_data(self) -> dict[str, Any]:
        """Return normalized quote data for this ticker."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("extra_tickers", {}).get(self._key, {})

    @property
    def native_unit_of_measurement(self) -> str:
        """Return currency unit of the ticker."""
        return str(
            self._quote_data().get("moneda")
            or ("ARS" if self._mercado == DEFAULT_MARKET else "USD")
        )

    @property
    def native_value(self) -> float | None:
        """Return last traded price."""
        return self._quote_data().get("ultimo_precio")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return market quote attributes."""
        data = self._quote_data()
        return {
            "variacion_diaria": data.get("variacion_diaria"),
            "punta_compradora": data.get("punta_compradora"),
            "punta_vendedora": data.get("punta_vendedora"),
            "volumen_nominal": data.get("volumen_nominal"),
            "precio_apertura": data.get("precio_apertura"),
            "precio_maximo": data.get("precio_maximo"),
            "precio_minimo": data.get("precio_minimo"),
            "ultimo_cierre": data.get("ultimo_cierre"),
            "moneda": data.get("moneda"),
            "mercado": self._mercado,
        }


class _IOLInflacionBaseSensor(IOLEntity, SensorEntity):
    """Base sensor for ArgentinaDatos inflation indicators."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: IOLDataUpdateCoordinator,
        data_key: str,
        suffix: str,
        name: str,
        entity_id: str,
        icon: str,
    ) -> None:
        """Initialize an inflation sensor."""
        super().__init__(coordinator, suffix)
        self._data_key = data_key
        self._attr_name = name
        self._attr_icon = icon
        self.entity_id = entity_id

    def _inflacion_data(self) -> dict[str, Any]:
        """Return inflation payload from coordinator data."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get(self._data_key) or {}

    @property
    def native_value(self) -> float | None:
        """Return latest inflation percentage."""
        return self._inflacion_data().get("valor")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return publication date, prior period value, and source."""
        data = self._inflacion_data()
        return {
            "fecha": data.get("fecha"),
            "valor_anterior": data.get("valor_anterior"),
            "fecha_anterior": data.get("fecha_anterior"),
            "fuente": data.get("fuente"),
        }


class IOLInflacionMensualSensor(_IOLInflacionBaseSensor):
    """Sensor representing the latest monthly inflation in Argentina."""

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the monthly inflation sensor."""
        super().__init__(
            coordinator=coordinator,
            data_key="inflacion_mensual",
            suffix="inflacion_mensual",
            name="Inflación Mensual",
            entity_id="sensor.iol_inflacion_mensual",
            icon="mdi:trending-up",
        )


class IOLInflacionInteranualSensor(_IOLInflacionBaseSensor):
    """Sensor representing 12-month accumulated (interannual) inflation in Argentina."""

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the 12-month accumulated inflation sensor."""
        super().__init__(
            coordinator=coordinator,
            data_key="inflacion_interanual",
            suffix="inflacion_interanual",
            name="Inflación Interanual 12M",
            entity_id="sensor.iol_inflacion_interanual",
            icon="mdi:calendar-range",
        )


class IOLInflacionMensualUsdSensor(_IOLInflacionBaseSensor):
    """Sensor representing the latest monthly inflation in Argentina measured in USD MEP."""

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the monthly USD inflation sensor."""
        super().__init__(
            coordinator=coordinator,
            data_key="inflacion_mensual_usd",
            suffix="inflacion_mensual_usd",
            name="Inflación Mensual USD",
            entity_id="sensor.iol_inflacion_mensual_usd",
            icon="mdi:currency-usd",
        )


class IOLInflacionInteranualUsdSensor(_IOLInflacionBaseSensor):
    """Sensor representing 12-month accumulated inflation in Argentina measured in USD MEP."""

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the 12-month accumulated USD inflation sensor."""
        super().__init__(
            coordinator=coordinator,
            data_key="inflacion_interanual_usd",
            suffix="inflacion_interanual_usd",
            name="Inflación Interanual 12M USD",
            entity_id="sensor.iol_inflacion_interanual_usd",
            icon="mdi:calendar-range",
        )


class IOLPortfolioSensor(IOLEntity, SensorEntity):
    """Optional opt-in sensor exposing full portfolio holdings (disabled by default)."""

    _attr_name = "Portafolio"
    _attr_native_unit_of_measurement = "activos"
    _attr_icon = "mdi:briefcase-outline"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the opt-in portfolio sensor."""
        super().__init__(coordinator, "portafolio")
        self.entity_id = "sensor.iol_portafolio"

    def _portfolio_data(self) -> dict[str, Any]:
        """Return normalized portfolio dictionary from coordinator."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("portafolio") or {}

    @property
    def native_value(self) -> int | None:
        """Return count of portfolio holdings."""
        return self._portfolio_data().get("cantidad_activos")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return normalized holdings list and totals for dashboards."""
        data = self._portfolio_data()
        return {
            "total_valorizado": data.get("total_valorizado"),
            "ganancia_total": data.get("ganancia_total"),
            "distribucion_por_tipo": data.get("distribucion_por_tipo"),
            "activos": data.get("activos", []),
        }


class IOLDolarMepSensor(IOLEntity, SensorEntity):
    """Sensor representing the resolved Dólar MEP exchange rate in ARS."""

    _attr_name = "Dólar MEP"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the Dólar MEP rate sensor."""
        super().__init__(coordinator, "dolar_mep")
        self.entity_id = "sensor.iol_dolar_mep"

    @property
    def native_value(self) -> float | None:
        """Return Dólar MEP rate in ARS."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("dolar_mep")


class IOLDolarCclSensor(IOLEntity, SensorEntity):
    """Sensor representing the resolved Dólar CCL exchange rate in ARS."""

    _attr_name = "Dólar CCL"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the Dólar CCL rate sensor."""
        super().__init__(coordinator, "dolar_ccl")
        self.entity_id = "sensor.iol_dolar_ccl"

    @property
    def native_value(self) -> float | None:
        """Return Dólar CCL rate in ARS."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("dolar_ccl")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return CCL resolution source."""
        if not self.coordinator.data:
            return {}
        return {"fuente_ccl": self.coordinator.data.get("fuente_ccl")}


class IOLDisponibleArsSensor(IOLEntity, SensorEntity):
    """Sensor representing liquid available ARS balance."""

    _attr_name = "Disponible ARS"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the available ARS balance sensor."""
        super().__init__(coordinator, "disponible_ars")
        self.entity_id = "sensor.iol_disponible_ars"

    def _account_data(self) -> dict[str, Any]:
        """Return consolidated account summary."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("account", {})

    @property
    def native_value(self) -> float | None:
        """Return available ARS cash balance."""
        return self._account_data().get("disponible_pesos")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return committed ARS balance and account number."""
        data = self._account_data()
        return {
            "comprometido": data.get("comprometido_pesos"),
            "numero_cuenta": data.get("numero_cuenta"),
        }


class IOLDisponibleUsdSensor(IOLEntity, SensorEntity):
    """Sensor representing liquid available USD balance."""

    _attr_name = "Disponible USD"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the available USD balance sensor."""
        super().__init__(coordinator, "disponible_usd")
        self.entity_id = "sensor.iol_disponible_usd"

    def _account_data(self) -> dict[str, Any]:
        """Return consolidated account summary."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("account", {})

    @property
    def native_value(self) -> float | None:
        """Return available USD cash balance."""
        return self._account_data().get("disponible_dolares")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return committed USD balance and account number."""
        data = self._account_data()
        return {
            "comprometido": data.get("comprometido_dolares"),
            "numero_cuenta": data.get("numero_cuenta"),
        }


class IOLPortafolioGananciaSensor(IOLEntity, SensorEntity):
    """Sensor representing total unrealized gain/loss of the portfolio in ARS."""

    _attr_name = "Ganancia Portafolio"
    _attr_native_unit_of_measurement = "ARS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the portfolio total gain/loss sensor."""
        super().__init__(coordinator, "portafolio_ganancia")
        self.entity_id = "sensor.iol_portafolio_ganancia"

    def _portfolio_data(self) -> dict[str, Any]:
        """Return normalized portfolio dictionary from coordinator."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("portafolio") or {}

    @property
    def native_value(self) -> float | None:
        """Return total portfolio gain/loss in ARS."""
        return self._portfolio_data().get("ganancia_total")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return total valued amount and holdings count."""
        data = self._portfolio_data()
        return {
            "total_valorizado": data.get("total_valorizado"),
            "cantidad_activos": data.get("cantidad_activos"),
        }


class IOLUltimaActualizacionSensor(IOLEntity, SensorEntity):
    """Timestamp sensor indicating the exact date/time of the last real IOL API poll."""

    _attr_name = "Última Actualización"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: IOLDataUpdateCoordinator) -> None:
        """Initialize the last-update timestamp sensor."""
        super().__init__(coordinator, "ultima_actualizacion")
        self.entity_id = "sensor.iol_ultima_actualizacion"

    @property
    def native_value(self) -> datetime | None:
        """Return timezone-aware datetime of the last real IOL API update."""
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get("ultima_actualizacion")
        return val if isinstance(val, datetime) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return local ISO timestamp and polling window status."""
        dt = self.native_value
        return {
            "fecha_hora_local": (
                dt.astimezone(self.coordinator.market_tz).isoformat(timespec="seconds")
                if dt is not None
                else None
            ),
            "en_ventana_sondeo": is_within_market_window(tz=self.coordinator.market_tz),
        }
