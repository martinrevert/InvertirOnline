"""Tests for InvertirOnline (IOL) sensor entities and get_quote service."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.invertironline.const import DOMAIN


async def test_sensor_caucion_attributes(hass: HomeAssistant, mock_iol_api) -> None:
    """Test that caución sensors (1, 7, 14, 30, 60D) expose rate and attributes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for term, expected_rate in (
        (1, "36.5"),
        (7, "38.0"),
        (14, "39.25"),
        (30, "41.0"),
        (60, "42.5"),
    ):
        state = hass.states.get(f"sensor.iol_caucion_{term}d")
        assert state is not None
        assert state.state == expected_rate
        assert state.attributes["plazo_dias"] == term
        assert state.attributes["plazo_dias_real"] == term
        assert "tasa_tomadora" in state.attributes
        assert "monto_operado" in state.attributes
        assert "punta_compradora" in state.attributes
        assert "punta_vendedora" in state.attributes


async def test_sensor_account_and_spy(hass: HomeAssistant, mock_iol_api) -> None:
    """Test CEDEAR SPY and account valuation sensors (ARS, USD MEP, USD CCL)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    spy_state = hass.states.get("sensor.iol_cedear_spy")
    assert spy_state is not None
    assert spy_state.state == "34500.0"
    assert spy_state.attributes["variacion_diaria"] == 1.25

    ars_state = hass.states.get("sensor.iol_cuenta_total_ars")
    assert ars_state is not None
    assert ars_state.state == "2500000.0"
    assert ars_state.attributes["numero_cuenta"] == "987654"

    mep_state = hass.states.get("sensor.iol_cuenta_total_usd_mep")
    assert mep_state is not None
    assert mep_state.attributes["cotizacion_mep_utilizada"] == 1150.0

    ccl_state = hass.states.get("sensor.iol_cuenta_total_usd_ccl")
    assert ccl_state is not None
    assert ccl_state.attributes["cotizacion_ccl_implicita"] == 1200.0
    assert ccl_state.attributes["fuente_ccl"] == "api_directa"

    inf_m_state = hass.states.get("sensor.iol_inflacion_mensual")
    assert inf_m_state is not None
    assert inf_m_state.state == "2.7"
    assert inf_m_state.attributes["fecha"] == "2026-10-01"

    inf_i_state = hass.states.get("sensor.iol_inflacion_interanual")
    assert inf_i_state is not None
    assert inf_i_state.state == "33.13"
    assert inf_i_state.attributes["fuente"] == "ArgentinaDatos"

    inf_m_usd_state = hass.states.get("sensor.iol_inflacion_mensual_usd")
    assert inf_m_usd_state is not None
    assert inf_m_usd_state.state == "1.81"
    assert inf_m_usd_state.attributes["fecha"] == "2026-10-01"

    inf_i_usd_state = hass.states.get("sensor.iol_inflacion_interanual_usd")
    assert inf_i_usd_state is not None
    assert inf_i_usd_state.state == "27.34"
    assert inf_i_usd_state.attributes["fuente"] == "ArgentinaDatos (IPC / Dólar MEP)"


async def test_service_get_quote(hass: HomeAssistant, mock_iol_api) -> None:
    """Test invertironline.get_quote service returns structured payload for Assist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "get_quote",
        {"simbolo": "GGAL", "mercado": "bCBA"},
        blocking=True,
        return_response=True,
    )

    assert response == {
        "simbolo": "GGAL",
        "descripcion": "Activo GGAL",
        "ultimo_precio": 5420.5,
        "moneda": "ARS",
        "variacion_porcentual": 2.15,
        "punta_compradora": 5415.0,
        "punta_vendedora": 5425.0,
        "volumen": 142050.0,
        "fecha_hora": "2026-11-17T15:30:00",
    }


async def test_service_get_portfolio_and_opt_in_sensor(
    hass: HomeAssistant, mock_iol_api
) -> None:
    """Test invertironline.get_portfolio service and disabled-by-default portfolio sensor."""
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Portfolio sensor is registered but disabled by default
    ent_reg = er.async_get(hass)
    reg_entry = ent_reg.async_get("sensor.iol_portafolio")
    assert reg_entry is not None
    assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.iol_portafolio") is None

    # On-demand service returns full normalized portfolio (sorted by valorizado)
    full = await hass.services.async_call(
        DOMAIN,
        "get_portfolio",
        {"pais": "Argentina"},
        blocking=True,
        return_response=True,
    )
    assert full["cantidad_activos"] == 2
    assert full["total_valorizado"] == 2000000.0
    assert full["activos"][0]["simbolo"] == "SPY"
    assert full["activos"][0]["peso_porcentaje"] == 75.0

    # Filtered by tipo
    filtered = await hass.services.async_call(
        DOMAIN,
        "get_portfolio",
        {"pais": "Argentina", "tipo": "CEDEAR"},
        blocking=True,
        return_response=True,
    )
    assert filtered["cantidad_activos"] == 1
    assert filtered["activos"][0]["simbolo"] == "SPY"


async def test_phase1_derived_sensors_and_binary_sensor(
    hass: HomeAssistant, mock_iol_api
) -> None:
    """Test Phase 1 derived sensors (MEP, CCL, cash, portfolio gain) and binary sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mep_rate = hass.states.get("sensor.iol_dolar_mep")
    assert mep_rate is not None
    assert mep_rate.state == "1150.0"

    ccl_rate = hass.states.get("sensor.iol_dolar_ccl")
    assert ccl_rate is not None
    assert ccl_rate.state == "1200.0"
    assert ccl_rate.attributes["fuente_ccl"] == "api_directa"

    disp_ars = hass.states.get("sensor.iol_disponible_ars")
    assert disp_ars is not None
    assert disp_ars.state == "500000.0"
    assert disp_ars.attributes["numero_cuenta"] == "987654"

    disp_usd = hass.states.get("sensor.iol_disponible_usd")
    assert disp_usd is not None
    assert disp_usd.state == "250.0"

    gain = hass.states.get("sensor.iol_portafolio_ganancia")
    assert gain is not None
    assert gain.state == "150000.0"
    assert gain.attributes["total_valorizado"] == 2000000.0
    assert gain.attributes["cantidad_activos"] == 2

    market_open = hass.states.get("binary_sensor.iol_mercado_abierto")
    assert market_open is not None
    assert market_open.state in ("on", "off")
    assert "horario_rueda" in market_open.attributes


async def test_phase2_assist_services(hass: HomeAssistant, mock_iol_api) -> None:
    """Test get_operations, get_market_panel, and get_historical_quotes services."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="InvertirOnline (987654)",
        data={CONF_USERNAME: "usuario_iol", CONF_PASSWORD: "secret_password"},
        unique_id="iol_987654",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ops = await hass.services.async_call(
        DOMAIN,
        "get_operations",
        {"estado": "terminadas"},
        blocking=True,
        return_response=True,
    )
    assert ops["cantidad"] == 1
    assert ops["operaciones"][0]["simbolo"] == "AL30"

    panel = await hass.services.async_call(
        DOMAIN,
        "get_market_panel",
        {"instrumento": "Acciones", "panel": "Merval"},
        blocking=True,
        return_response=True,
    )
    assert panel["total_instrumentos"] == 2
    assert panel["titulos"][0]["simbolo"] == "GGAL"

    hist = await hass.services.async_call(
        DOMAIN,
        "get_historical_quotes",
        {
            "simbolo": "GGAL",
            "fecha_desde": "2026-11-01",
            "fecha_hasta": "2026-11-17",
        },
        blocking=True,
        return_response=True,
    )
    assert hist["cantidad_ruedas"] == 2
    assert hist["precio_inicial"] == 5050.0
    assert hist["precio_final"] == 5420.5
    assert hist["maximo_periodo"] == 5450.0
    assert hist["minimo_periodo"] == 4950.0
