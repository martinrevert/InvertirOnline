# Directivas de Desarrollo para Agentes AI: Integración InvertirOnline (IOL) para Home Assistant

Este documento establece las especificaciones mandatorias, estándares de arquitectura, restricciones de seguridad y directivas de implementación que todo Agente de Inteligencia Artificial (Claude Code, Cursor, Copilot, Windsurf, OpenCode o equivalentes) debe acatar de forma estricta al generar, refactorizar o mantener el código de la integración personalizada de InvertirOnline (IOL) para Home Assistant.

---

## 1. Principios de Operación y Reglas Mandatorias para Agentes AI

Los agentes de desarrollo autónomo deben operar bajo estrictas directivas de contención técnica y calidad arquitectónica para asegurar la máxima estabilidad del sistema domótico, evitando bloqueos en el bucle de eventos principal (*event loop*) de Home Assistant y previniendo la degradación o suspensión de la cuenta por exceso de cuota en los servidores de InvertirOnline.

### Lo que está estrictamente PERMITIDO y FOMENTADO
* **Arquitectura Asíncrona Pura:** Implementar todos los métodos de red y procesamiento de datos mediante `async/await`.
* **Inyección de Sesión de Red:** Utilizar exclusivamente la sesión HTTP compartida provista por el núcleo de Home Assistant mediante `homeassistant.helpers.aiohttp_client.async_get_clientsession`.
* **Coordinación Centralizada de Sondeo:** Implementar un único `DataUpdateCoordinator` que agrupe las peticiones a la API en lotes periódicos y distribuya los datos a todas las entidades sensoras dependientes.
* **Manejo Defensivo de Excepciones:** Capturar anomalías de red (`aiohttp.ClientError`), tiempos de espera agotados (`asyncio.TimeoutError`) y códigos de error HTTP mapeándolos a excepciones nativas de Home Assistant (`ConfigEntryNotReady`, `ConfigEntryAuthFailed`, `UpdateFailed`).
* **Soporte Completo de Calidad (Bronze/Silver):** Incluir identificadores únicos determinísticos (`unique_id`), nombres canónicos compatibles con traducciones (`has_entity_name = True`), soporte para reautenticación fluida y suites de prueba automatizadas mediante `pytest-homeassistant`.

### Lo que está estrictamente PROHIBIDO (Hard Constraints)
* **PROHIBICIÓN TOTAL DE TRADING (Modo Solo Lectura):** Queda terminantemente prohibido implementar llamadas a los endpoints de operación (compra, venta, suscripción de fondos o cancelación de órdenes). La integración debe operar única y exclusivamente en modo de consulta y monitoreo financiero.
* **PROHIBICIÓN DE LLAMADAS BLOQUEANTES:** Nunca utilizar librerías síncronas (`requests`, `urllib`, `time.sleep`) dentro del hilo principal de ejecución ni dentro de los métodos del coordinador.
* **PROHIBICIÓN DE ALMACENAMIENTO DE CREDENCIALES EN TEXTO PLANO:** Queda prohibido persistir claves, tokens o contraseñas en archivos temporales, registros de depuración (*logs*) o archivos YAML en disco. Todos los datos de autenticación deben residir gestionados en el `ConfigEntry` cifrado de Home Assistant.
* **PROHIBICIÓN DE SONDEO AGRESIVO (Control Estricto de Rate Limiting):** No configurar intervalos de actualización inferiores a 15 minutos en el coordinador. La API de IOL asigna una cuota mensual bonificada de 25.000 llamadas; sondeos indiscriminados provocarán bloqueos temporales de IP o recargos tarifarios en la cuenta comitente del usuario.

---

## 2. Stack Tecnológico y Estándares de Arquitectura

El desarrollo debe alinearse rigurosamente con las especificaciones de Home Assistant Core (versión 2026.11 o superior):

* **Lenguaje:** Python 3.12 o superior, con tipado estricto (*type hints*) en todas las firmas de funciones y métodos.
* **Estructura del Proyecto:** Integración personalizada (*Custom Component*) ubicada bajo el espacio de nombres `custom_components/invertironline/`.
* **Framework de Testing:** `pytest` utilizando el plugin oficial `pytest-homeassistant` y accesorios de mockeo asíncrono para sesiones de red.
* **Estándar de Calidad:** Adherencia estricta a las reglas del *Integration Quality Scale* de Home Assistant:
  * `common-modules`: Modularización limpia entre `coordinator.py`, `config_flow.py`, `sensor.py`, `services.py` y `const.py`.
  * `runtime-data`: Gestión de datos en tiempo de ejecución mediante `entry.runtime_data`.
  * `entity-unique-id`: Asignación determinística de `unique_id` basada en el número de cuenta comitente y el identificador unívoco de cada instrumento financiero.
  * `has-entity-name`: Todas las entidades deben declarar `_attr_has_entity_name = True`.
  * `config-entry-unloading`: Implementación completa de descarga y limpieza de recursos en `async_unload_entry`.

---

## 3. Especificación de la API de InvertirOnline y Gestión de Sesión

La comunicación con los servicios de InvertirOnline se realiza a través de su interfaz REST oficial (versión 2).

### 3.1. Autenticación y Renovación de Token OAuth2
* **Host Base de la API:** Definido centralizadamente como constante `API_BASE_URL`.
* **Endpoint de Autenticación:** `POST /token`
* **Parámetros del formulario de autenticación (application/x-www-form-urlencoded):**
  * Campo de usuario: Identificador de acceso configurado por el usuario en el Config Flow inicial.
  * Campo de contraseña: Clave de acceso a la cuenta comitente.
  * Modo de concesión: Parámetro estándar `grant_type="password"`.
* **Ciclo de Vida y Renovación del Token:**
  * La API devuelve un token de acceso de tipo Bearer con una vigencia típica de 15 minutos, junto con un token de actualización (*refresh token*).
  * El cliente HTTP de la integración debe verificar la caducidad del token antes de emitir ráfagas de sondeo. Cuando reste menos de 1 minuto para expirar, debe emitir una llamada a `POST /token` con `grant_type="refresh_token"`.
  * Si la renovación devuelve un error 400 o 401, el cliente debe elevar la excepción `ConfigEntryAuthFailed`, lo cual instruye a Home Assistant a notificar al usuario para reingresar credenciales sin reiniciar la plataforma.

### 3.2. Catálogo de Endpoints de Monitoreo

| Instrumento / Métrica | Endpoint Relativo | Método | Descripción y Parámetros |
| :--- | :--- | :--- | :--- |
| **Cauciones Bursátiles** | `/api/v2/Cotizaciones/cauciones/todas/argentina` (fallback `/api/v2/Cotizaciones/cauciones/Argentina`) | `GET` | Recupera el panel de cauciones vigente en el mercado argentino; los plazos pueden venir como `plazo` o dentro de `simbolo`/`descripcion` (ej. `"PESOS 1D"`). |
| **CEDEAR SPY** | `/api/v2/bCBA/Titulos/SPY/Cotizacion` | `GET` | Recupera el último precio, puntas compradoras/vendedoras y variación diaria del CEDEAR representativo del índice bursátil. |
| **Dólar MEP** | `/api/v2/Cotizaciones/Dolar/Mep` (fallback `AL30`/`AL30D` o `GD30`/`GD30D`) | `GET` | Si el endpoint directo no está disponible en la cuenta/API, se calcula mediante el ratio implícito `AL30 / AL30D` (o `GD30 / GD30D`). |
| **Estado de Cuenta** | `/api/v2/estadocuenta` | `GET` | Devuelve el desglose de saldos líquidos disponibles y saldos comprometidos por moneda. |
| **Portafolio Consolidado** | `/api/v2/portafolio/Argentina` | `GET` | Devuelve la valorización patrimonial total de las tenencias valorizadas en moneda local y extranjera. |
| **Consulta Dinámica (Assist)** | `/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion` | `GET` | Endpoint parametrizado para resolver cotizaciones de cualquier ticker a petición del usuario. |

---

## 4. Especificación Detallada de Entidades y Plataforma Sensor

El archivo `sensor.py` debe instanciar y registrar las entidades descritas a continuación, vinculándolas al `DataUpdateCoordinator` central y asignándolas al dispositivo de la cuenta comitente en el registro de dispositivos de Home Assistant.

### 4.1. Sensores de Cauciones Bursátiles (Tasas a Plazo Fijo de Mercado)
Se deben instanciar cinco sensores fijos correspondientes a los plazos bursátiles estándar: 1, 7, 14, 30 y 60 días.

* **Identificador de Entidad (*Entity ID*):** `sensor.iol_caucion_{dias}d` (ejemplos: `sensor.iol_caucion_1d`, `sensor.iol_caucion_7d`, `sensor.iol_caucion_14d`, `sensor.iol_caucion_30d`, `sensor.iol_caucion_60d`).
* **Nombre de Entidad:** `Caución {dias}D` (con `has_entity_name = True`, Home Assistant prefijará el nombre del dispositivo de la cuenta).
* **Estado Canónico (`native_value`):** Tasa Nominal Anual Colocadora (`tasaColocadora` o `tasaPromedio` según disponibilidad del panel), formateada como número flotante redondeado a dos decimales.
* **Unidad de Medida Nativa:** Porcentaje (`%`).
* **Clase de Estado (*State Class*):** `SensorStateClass.MEASUREMENT`.
* **Icono Sugerido:** `mdi:percent-circle-outline`.
* **Regla de Resolución de Plazos en Feriados y Fines de Semana (BYMA):**
  * Cuando el plazo nominal exacto (`1`, `7`, `14`, `30` o `60` días) no opere en la rueda (por ejemplo, los viernes donde la caución a 1 día hábil pasa a liquidarse a 3 días, o feriados largos), el coordinador/sensor debe buscar primero la coincidencia exacta y, en su defecto, seleccionar automáticamente el **plazo hábil inmediato siguiente** dentro de una ventana razonable (ej. 1D → busca en 1..5 días; 7D → 6..11 días; 14D → 12..18 días; 30D → 26..36 días; 60D → 50..70 días).
* **Atributos de Estado Adicionales (*extra_state_attributes*):**
  * `tasa_tomadora`: TNA tomadora registrada en el mercado para ese plazo.
  * `monto_operado`: Monto total transaccionado en pesos argentinos durante la sesión.
  * `punta_compradora`: Mejor tasa de compra presente en el libro de órdenes.
  * `punta_vendedora`: Mejor tasa de venta presente en el libro de órdenes.
  * `plazo_dias`: Número entero que representa el vencimiento nominal del sensor (1, 7, 14, 30 o 60).
  * `plazo_dias_real`: Número entero que representa el plazo real en días corridos encontrado en el mercado (ej. `3` un día viernes para el sensor de `1D`).
  * `ultima_actualizacion`: Marca de tiempo en formato ISO 8601 del último registro provisto por el mercado.

### 4.2. Sensor del CEDEAR SPY (S&P 500 en Pesos)
* **Identificador de Entidad:** `sensor.iol_cedear_spy`
* **Nombre de Entidad:** `CEDEAR SPY`
* **Estado Canónico (`native_value`):** Último precio operado en el mercado local en pesos argentinos.
* **Unidad de Medida:** `ARS`.
* **Clase de Dispositivo (*Device Class*):** `SensorDeviceClass.MONETARY`.
* **Clase de Estado (*State Class*):** `SensorStateClass.MEASUREMENT`.
* **Icono Sugerido:** `mdi:chart-line`.
* **Atributos de Estado Adicionales:**
  * `variacion_diaria`: Porcentaje de variación relativo al cierre anterior.
  * `punta_compradora`: Precio vigente en la punta de compra.
  * `punta_vendedora`: Precio vigente en la punta de venta.
  * `volumen_nominal`: Cantidad de títulos operados en la rueda.
  * `precio_apertura`: Precio de apertura de la jornada.
  * `precio_maximo`: Valor máximo alcanzado durante la sesión.
  * `precio_minimo`: Valor mínimo registrado en la sesión.
  * `ultimo_cierre`: Cotización de liquidación del día hábil anterior.

### 4.3. Sensores de Valuación Patrimonial de la Cuenta Comitente
Representan el valor consolidado de la cartera financiera en las tres denominaciones monetarias requeridas:

1. **Total Cuenta en Pesos Argentinos:**
   * **Identificador:** `sensor.iol_cuenta_total_ars`
   * **Nombre:** `Total Cuenta ARS`
   * **Estado:** Valuación neta total en pesos (saldo líquido disponible más valor de mercado de todas las posiciones abiertas).
   * **Unidad de Medida:** `ARS`.
   * **Atributos:** `disponible_pesos`, `tenencia_titulos_pesos`, `numero_cuenta`.
2. **Total Cuenta en Dólar MEP:**
   * **Identificador:** `sensor.iol_cuenta_total_usd_mep`
   * **Nombre:** `Total Cuenta USD MEP`
   * **Estado:** Valuación neta de la cuenta convertida al tipo de cambio Dólar MEP provisto por el endpoint específico de IOL.
   * **Unidad de Medida:** `USD`.
   * **Atributos:** `cotizacion_mep_utilizada`, `disponible_dolares`.
3. **Total Cuenta en Dólar CCL:**
   * **Identificador:** `sensor.iol_cuenta_total_usd_ccl`
   * **Nombre:** `Total Cuenta USD CCL`
   * **Estado:** Valuación neta de la cuenta valorizada en Dólar Contado con Liquidación.
   * **Jerarquía de Resolución del Tipo de Cambio CCL:**
     1. **Fuente Primaria (API Directa):** Consultar primero si los endpoints de cotización de divisas/estado de cuenta de IOL (`/api/v2/Cotizaciones/Dolar` o `/api/v2/estadocuenta`) exponen directamente la cotización de Dólar CCL o la valuación consolidada en USD CCL.
     2. **Fuente de Respaldo (Cálculo Implícito):** Si la API no devuelve el tipo de cambio CCL directo, calcularlo mediante el ratio implícito de activos duales líquidos (ej. `AL30` en ARS vs `AL30C` en USD Cable, o `SPY` en BCBA vs `SPY` en NYSE ajustado por el ratio de conversión del CEDEAR 20:1).
   * **Unidad de Medida:** `USD`.
   * **Atributos:** `cotizacion_ccl_implicita`, `fuente_ccl` (`"api_directa"` o `"ratio_implicito"`).

### 4.4. Sensores Configurables de Tickers Adicionales (`OptionsFlow`)
Además de los 9 sensores base obligatorios (5 cauciones + CEDEAR SPY + 3 valuaciones de cuenta), la integración debe implementar un `OptionsFlow` que permita al usuario:
1. **Agregar o quitar tickers personalizados** (formato `SIMBOLO` o `MERCADO:SIMBOLO`, por defecto mercado `bCBA`, ej. `GGAL`, `AL30`, `YPFD`, `NYSE:AAPL`).
   * **Identificador de Entidad:** `sensor.iol_ticker_{mercado}_{simbolo}` (o `sensor.iol_ticker_{simbolo}` para `bCBA`).
   * **Nombre de Entidad:** `Ticker {SIMBOLO}` (con los mismos atributos de cotización que el sensor de `CEDEAR SPY`: `variacion_diaria`, `punta_compradora`, `punta_vendedora`, `volumen_nominal`, `precio_apertura`, `precio_maximo`, `precio_minimo`, `ultimo_cierre`, `moneda`, `mercado`).
2. **Ajustar el intervalo de actualización (`scan_interval_minutes`)**, validando estrictamente que **nunca sea menor a 15 minutos** para proteger la cuota mensual de 25.000 llamadas de la API de IOL.
3. Recargar automáticamente la entrada (`async_reload`) al guardar cambios en las opciones para instanciar los nuevos sensores sin requerir reinicio completo de Home Assistant.

---

## 5. Servicio de Consulta Dinámica para Asistente de Voz (Assist / LLM)

Para posibilitar la interacción fluida con el Asistente de Voz de Home Assistant (Assist, LLM Conversation Agents) y permitir consultar cualquier activo en tiempo real sin crear miles de sensores estáticos innecesarios, los agentes deben implementar una Acción (*Service*) personalizada con respuesta estructurada (`SupportsResponse.ONLY`).

### 5.1. Definición de la Acción: `invertironline.get_quote`
* **Módulo de Registro:** `services.py`
* **Definición de Esquema:** `services.yaml`
* **Parámetros de Entrada:**
  * `simbolo` (string, obligatorio): Ticker o código del instrumento a consultar (ejemplos: `AL30`, `GGAL`, `AAPL`, `SPY`, `YPFD`).
  * `mercado` (string, opcional, valor por defecto `"bCBA"`): Mercado correspondiente (`bCBA` para bolsa local, `NYSE`, `NASDAQ` para activos internacionales).
* **Flujo de Ejecución:**
  1. Validar la estructura del parámetro recibido.
  2. Obtener el cliente API desde `entry.runtime_data`.
  3. Ejecutar la llamada asíncrona hacia el endpoint de cotización individual del título.
  4. Mapear la respuesta a un diccionario plano con claves descriptivas.
  5. Retornar el payload estructurado.

### 5.2. Estructura del Payload de Respuesta para el Asistente
```json
{
  "simbolo": "GGAL",
  "descripcion": "Grupo Financiero Galicia S.A.",
  "ultimo_precio": 5420.50,
  "moneda": "ARS",
  "variacion_porcentual": 2.15,
  "punta_compradora": 5415.00,
  "punta_vendedora": 5425.00,
  "volumen": 142050,
  "fecha_hora": "2026-11-17T15:30:00"
}
```

Al exponer esta acción al motor de LLM de Home Assistant, cualquier usuario podrá formular consultas conversacionales tales como:
* *"¿A cuánto cotiza Galicia en InvertirOnline?"*
* *"Consultá el precio del CEDEAR de Apple en la bolsa."*
* *"¿Qué variación tuvo el bono AL30 hoy?"*

El LLM invocará `invertironline.get_quote` y generará una respuesta hablada contextualizada a través de las canalizaciones de Assist.

---

## 6. Organización de Archivos y Repositorio del Proyecto

La estructura del repositorio debe cumplir con los requisitos formales del catálogo del Marketplace de Home Assistant:

```text
custom_components/invertironline/
├── __init__.py               # Inicialización de la integración y registro de acciones
├── api.py                   # Cliente asíncrono puro para la API REST de IOL
├── config_flow.py           # Formulario visual de configuración y reautenticación
├── const.py                 # Constantes de dominio, intervalos, timeouts y claves
├── coordinator.py           # DataUpdateCoordinator con rate limiting y refresco de tokens
├── entity.py                # Clase base común con vinculación de DeviceInfo
├── manifest.json            # Metadatos del componente, dependencias e identificadores
├── sensor.py                # Instanciación de sensores (Cauciones, SPY, Valuación)
├── services.py              # Implementación y registro de invertironline.get_quote
├── services.yaml            # Esquema y documentación de la acción para la interfaz y LLM
├── brand/
│   ├── icon.png             # Icono distintivo en resolución 256x256 px
│   └── logo.png             # Logotipo en resolución horizontal
└── translations/
    ├── en.json              # Traducción al inglés requerida por el validador oficial
    └── es.json              # Traducción nativa al idioma español
hacs.json                    # Manifiesto para el catálogo del Marketplace
README.md                    # Documentación técnica, tarjetas visuales y automatizaciones
.devcontainer/
    └── devcontainer.json    # Configuración de contenedor de desarrollo para VS Code
tests/
    ├── __init__.py
    ├── conftest.py          # Fixtures de pytest-homeassistant y emuladores de API
    ├── test_config_flow.py  # Pruebas unitarias del flujo de configuración
    ├── test_coordinator.py  # Pruebas de actualización de datos y ciclo de token
    └── test_sensor.py       # Pruebas de renderizado de estados y atributos
```

### Configuración Mandatoria del `manifest.json`
```json
{
  "domain": "invertironline",
  "name": "InvertirOnline (IOL)",
  "codeowners": ["@desarrollador"],
  "config_flow": true,
  "documentation": "https://example.com/docs/invertironline",
  "issue_tracker": "https://example.com/docs/invertironline/issues",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "categories": ["finance"],
  "version": "1.0.0"
}
```

### Configuración Mandatoria de `hacs.json`
```json
{
  "name": "InvertirOnline (IOL)",
  "render_readme": true,
  "homeassistant": "2026.11.0"
}
```

---

## 7. Estrategia de Pruebas Automatizadas con `pytest-homeassistant`

Para garantizar que el componente alcance el estándar de calidad y no sufra regresiones, los agentes deben proveer una cobertura de pruebas mínima en la lógica de negocio y flujos de interfaz de usuario.

* **Herramienta Obligatoria:** Utilizar el paquete oficial `pytest-homeassistant`.
* **Aislamiento de Red:** Queda prohibido realizar llamadas HTTP reales a servidores externos durante la ejecución de los tests. Todos los intercambios deben simularse mediante fixtures de mockeo asíncrono.
* **Casos de Prueba Obligatorios:**
  1. `test_config_flow_success`: Simula el ingreso correcto de usuario y contraseña en el formulario, valida la recepción simulada de los tokens y confirma la creación del `ConfigEntry`.
  2. `test_config_flow_invalid_auth`: Simula una respuesta HTTP 400/401 en la autenticación y comprueba que la interfaz presenta el mensaje de error `invalid_auth`.
  3. `test_coordinator_token_refresh`: Valida que el coordinador detecta la proximidad de expiración del token y dispara correctamente la solicitud de refresco con `grant_type="refresh_token"`.
  4. `test_sensor_caucion_attributes`: Verifica que los sensores de cauciones (1, 7, 14, 30 y 60 días) cargan correctamente tanto la tasa colocadora en el estado como las puntas y el volumen en sus atributos.
  5. `test_service_get_quote`: Verifica que la acción `invertironline.get_quote` procesa los parámetros de entrada y devuelve el diccionario estructurado esperado.

---

## 8. Automatizaciones de Referencia para el Usuario Final

Los agentes AI deben proveer en la documentación del repositorio los ejemplos prácticos de automatización en formato YAML para que el usuario pueda vincular los datos financieros con sus altavoces inteligentes y dispositivos móviles.

### 8.1. Notificación Diaria de Cauciones y Cotizaciones al Teléfono Móvil
```yaml
alias: "Finanzas: Reporte Matutino de Cauciones y Dólar"
description: "Envía un resumen de tasas de caución y cotización MEP al celular a las 11:30 hs."
trigger:
  - platform: time
    at: "11:30:00"
condition:
  - condition: time
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
action:
  - action: notify.notify
    data:
      title: "Reporte de Mercado IOL"
      message: >
        Tasa Caución 1D: {{ states('sensor.iol_caucion_1d') }}% (Tomadora: {{ state_attr('sensor.iol_caucion_1d', 'tasa_tomadora') }}%)
        Tasa Caución 7D: {{ states('sensor.iol_caucion_7d') }}%
        Tasa Caución 30D: {{ states('sensor.iol_caucion_30d') }}%
        CEDEAR SPY: ${{ states('sensor.iol_cedear_spy') }} ARS ({{ state_attr('sensor.iol_cedear_spy', 'variacion_diaria') }}%)
        Dólar MEP: ${{ states('sensor.iol_cuenta_total_usd_mep') }}
```

### 8.2. Anuncio por Voz (TTS) del Estado de Cuenta al Llegar al Hogar
```yaml
alias: "Finanzas: Balance por Voz en Altavoces al Llegar"
trigger:
  - platform: state
    entity_id: person.usuario
    to: "home"
action:
  - action: tts.speak
    target:
      entity_id: media_player.altavoces_living
    data:
      media_player_entity_id: media_player.altavoces_living
      message: >
        Hola. Tu cuenta comitente en Invertir Online totaliza actualmente 
        {{ states('sensor.iol_cuenta_total_ars') }} pesos argentinos, 
        equivalentes a {{ states('sensor.iol_cuenta_total_usd_mep') }} dólares MEP. 
        La caución a un día está rindiendo una tasa colocadora del {{ states('sensor.iol_caucion_1d') }} por ciento.
```

---

## 9. Flujo de Despliegue Local, Pruebas en Vivo y Evolución para Agentes AI

### 9.1. Despliegue y Actualización Remota por Red Local (Samba / SSH)
El flujo de entrega elegido para probar y actualizar la integración en la instancia de Home Assistant del usuario es **copia directa por red local** hacia `/config/custom_components/invertironline`:
* **Script de Despliegue (`scripts/deploy_to_ha.ps1`):** Automatiza desde Windows PowerShell la sincronización de `custom_components/invertironline/` hacia el servidor de Home Assistant mediante:
  1. **Samba Share (UNC Path):** Ej. `\\homeassistant.local\config\custom_components\invertironline` o `\\<IP_HA>\config\custom_components\invertironline`.
  2. **SSH / SCP:** Ej. `scp -r custom_components/invertironline root@<IP_HA>:/config/custom_components/`.
  3. **Recarga Remota Opcional (HA REST API):** Si se provee un *Long-Lived Access Token* (`HA_TOKEN`) y URL (`HA_URL`), el script puede invocar automáticamente `POST /api/services/homeassistant/reload_config_entry` (o `homeassistant/restart` cuando cambien `manifest.json` o `services.yaml`) sin tocar la interfaz web.
* **Archivo `.deploy.env` (Ignorado en Git):** Si el usuario guarda la IP/ruta Samba o token de su Home Assistant en `.deploy.env`, este archivo **debe estar siempre incluido en `.gitignore`** para cumplir con la prohibición estricta de almacenar credenciales en el repositorio.

### 9.2. Guía de Diagnóstico y Mantenimiento para Futuros Agentes AI
1. **Inspección de Payloads Reales de IOL:** La API v2 de IOL puede presentar variaciones de nombres de campos según el instrumento o estado del mercado (ej. `tasaColocadora` vs `tasaPromedio`, `ultimoPrecio` vs `ultimo`, o `puntas` como lista o diccionario). Todo parseo en `api.py` y `coordinator.py` debe usar accesos defensivos (`.get()`) con fallbacks seguros y nunca lanzar `KeyError` que derriben la actualización completa del coordinador.
2. **Aislamiento de Fallos Parciales:** Si un endpoint secundario falla temporalmente (por ejemplo, la cotización de un ticker personalizado o el cálculo implícito de CCL), el `DataUpdateCoordinator` debe registrar un `warning` en el logger y conservar los datos del resto de los endpoints (estado de cuenta, cauciones, MEP, SPY) en lugar de invalidar toda la integración.
3. **Presupuesto de Cuota API (25.000 llamadas/mes) y Ventana Horaria:**
   * El coordinador solo ejecuta sondeos periódicos de **lunes a viernes de 10:30 a 18:30 hs (hora Argentina, `America/Argentina/Buenos_Aires`)**, manteniendo el último cierre fuera de horario y fines de semana (permitiendo siempre la carga inicial si `coordinator.data is None` al reiniciar HA).
   * Dentro de cada ciclo, `IOLDataUpdateCoordinator` reutiliza un `quote_cache` intra-ciclo para no consultar dos veces un mismo instrumento (ej. `AL30` compartido entre MEP, CCL y tickers extra).
   * Con 15 minutos en ventana de 8 horas hábiles (~33 ciclos/día × ~22 días hábiles/mes ≈ 726 ciclos/mes), el consumo base se mantiene por debajo de **7.000 llamadas/mes** (< 28% de la cuota).
4. **Mantenimiento de `AGENTS.md`:** Cualquier cambio en los esquemas de respuesta reales de la API de IOL, nuevos endpoints descubiertos durante pruebas en vivo o ajustes en las entidades debe documentarse aquí inmediatamente para mantener la memoria técnica del proyecto actualizada.

