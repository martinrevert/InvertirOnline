# InvertirOnline (IOL) para Home Assistant

Integración personalizada **100% solo lectura** para monitorear tu cuenta comitente de **InvertirOnline (IOL)** en Home Assistant: tasas de cauciones BYMA, CEDEAR SPY, valuación patrimonial consolidada (ARS, USD MEP y USD CCL), tickers personalizados y consultas por voz mediante **Assist / LLM**.

> **Seguridad y Modo Solo Lectura:** Esta integración **no implementa ni puede ejecutar** órdenes de compra, venta, suscripción ni cancelación. Tus credenciales se almacenan cifradas en el `ConfigEntry` de Home Assistant y los tokens OAuth2 se renuevan automáticamente en memoria.

---

## Qué incluye (Sensores Base)

Al configurar tu cuenta se crea un dispositivo `InvertirOnline (<N° de cuenta>)` con **9 sensores base**:

| Entidad | Descripción | Unidad | Atributos destacados |
| :--- | :--- | :---: | :--- |
| `sensor.iol_caucion_1d` | Tasa colocadora caución a 1 día (o próximo hábil) | `%` | `tasa_tomadora`, `monto_operado`, `punta_compradora`, `punta_vendedora`, `plazo_dias`, `plazo_dias_real`, `ultima_actualizacion` |
| `sensor.iol_caucion_7d` | Tasa colocadora caución a 7 días | `%` | Mismos atributos |
| `sensor.iol_caucion_14d` | Tasa colocadora caución a 14 días | `%` | Mismos atributos |
| `sensor.iol_caucion_30d` | Tasa colocadora caución a 30 días | `%` | Mismos atributos |
| `sensor.iol_caucion_60d` | Tasa colocadora caución a 60 días | `%` | Mismos atributos |
| `sensor.iol_cedear_spy` | Último precio del CEDEAR SPY en BYMA | `ARS` | `variacion_diaria`, `punta_compradora`, `punta_vendedora`, `volumen_nominal`, `precio_apertura`, `precio_maximo`, `precio_minimo`, `ultimo_cierre` |
| `sensor.iol_cuenta_total_ars` | Valuación total neta (disponible + tenencias) | `ARS` | `disponible_pesos`, `tenencia_titulos_pesos`, `numero_cuenta` |
| `sensor.iol_cuenta_total_usd_mep` | Valuación total expresada en Dólar MEP | `USD` | `cotizacion_mep_utilizada`, `disponible_dolares` |
| `sensor.iol_cuenta_total_usd_ccl` | Valuación total expresada en Dólar CCL | `USD` | `cotizacion_ccl_implicita`, `fuente_ccl` |
| `sensor.iol_inflacion_mensual` | Última inflación mensual publicada (ArgentinaDatos) | `%` | `fecha`, `valor_anterior`, `fecha_anterior`, `fuente` |
| `sensor.iol_inflacion_interanual` | Inflación acumulada últimos 12 meses (ArgentinaDatos) | `%` | `fecha`, `valor_anterior`, `fecha_anterior`, `fuente` |
| `sensor.iol_inflacion_mensual_usd` | Última inflación mensual medida en Dólar MEP | `%` | `fecha`, `valor_anterior`, `fecha_anterior`, `fuente` |
| `sensor.iol_inflacion_interanual_usd` | Inflación acumulada 12 meses medida en Dólar MEP | `%` | `fecha`, `valor_anterior`, `fecha_anterior`, `fuente` |
| `sensor.iol_dolar_mep` | Cotización de referencia Dólar MEP | `ARS` | — |
| `sensor.iol_dolar_ccl` | Cotización de referencia Dólar CCL | `ARS` | `fuente_ccl` |
| `sensor.iol_disponible_ars` | Saldo líquido disponible en pesos | `ARS` | `comprometido`, `numero_cuenta` |
| `sensor.iol_disponible_usd` | Saldo líquido disponible en dólares | `USD` | `comprometido`, `numero_cuenta` |
| `sensor.iol_portafolio_ganancia` | Ganancia/pérdida total no realizada del portafolio | `ARS` | `total_valorizado`, `cantidad_activos` |
| `binary_sensor.iol_mercado_abierto` | Indica si la rueda regular BYMA está abierta (Lun–Vie 11:00–17:00 ART) | — | `en_ventana_sondeo`, `horario_rueda`, `horario_sondeo` |
| `sensor.iol_ultima_actualizacion` | Fecha y hora exacta de la última consulta real a la API de IOL | `timestamp` | `fecha_hora_local`, `en_ventana_sondeo` |

---

## Sutilezas de Funcionamiento (Horarios, Feriados y Cálculos)

### 1. Horarios de actualización y cuidado de la cuota API
InvertirOnline otorga una cuota bonificada de **25.000 llamadas mensuales**. Para protegerla sin perder datos en vivo durante la rueda:
- **Horario activo:** La integración consulta a IOL **únicamente de lunes a viernes entre las 10:30 y las 18:30 hs** (hora Argentina, `America/Argentina/Buenos_Aires`), cubriendo la rueda de BYMA y el cierre de NYSE.
- **Intervalo mínimo:** Nunca menor a **15 minutos** (configurable a un valor mayor desde *Configurar*).
- **Fuera de horario (18:30 a 10:30 hs) y fines de semana:** Se **detienen por completo** las peticiones a la API (0 requests) y los sensores conservan los valores del último cierre del día.
- **Reinicio fuera de horario:** Si reinicias Home Assistant de noche o un fin de semana, la integración ejecuta **una única carga inicial** al arrancar para que los sensores no queden en `Unknown`, y luego vuelve a pausarse hasta el próximo día hábil a las 10:30 hs.
- **Caché intra-ciclo:** Dentro de un mismo ciclo de actualización, si un instrumento (como `AL30` o `SPY`) se necesita en más de un cálculo o también como ticker extra, se consulta una sola vez a la API. Con la configuración base, el consumo mensual queda por debajo de **7.000 llamadas/mes** (< 28% de la cuota).

### 2. Cómo se comporta en viernes, vísperas de feriados y fines de semana (Cauciones BYMA)
En el mercado argentino (BYMA), cuando un día es viernes o previo a un feriado, la caución a "1 día" no se opera como `1D` sino a `3D` o `4D` (al próximo día hábil), y algo similar ocurre con los plazos de `7D`, `14D`, `30D` y `60D`.
- **Resolución inteligente:** Cada sensor busca primero su plazo exacto; si no operó en la rueda, toma automáticamente el **plazo hábil inmediato siguiente** dentro de una ventana segura:
  - `1D` → busca en `1..5` días
  - `7D` → busca en `6..11` días
  - `14D` → busca en `12..18` días
  - `30D` → busca en `26..36` días
  - `60D` → busca en `50..70` días
- **Transparencia:** El atributo `plazo_dias` siempre indica el plazo nominal del sensor (ej. `1`), mientras que `plazo_dias_real` te muestra el plazo real operado ese día (ej. `3` un viernes).
- **Solo cauciones en pesos:** El panel de cauciones se filtra automáticamente para excluir cauciones en dólares y tasas residuales en USD.

### 3. Cómo calcula el Dólar MEP y el Dólar CCL
- **Dólar MEP:** Consulta si el endpoint directo está disponible y, en caso contrario, calcula el tipo de cambio implícito mediante `AL30 / AL30D` (con respaldo en `GD30 / GD30D`), usando `ultimoPrecio` o `cierreAnterior`.
- **Dólar CCL:** Intenta primero obtener la cotización CCL directa si la API la expone (`fuente_ccl: "api_directa"`); si no está disponible, calcula el ratio implícito usando `AL30 / AL30C` o, como segundo respaldo, `SPY (BCBA) * 20 / SPY (NYSE)` (`fuente_ccl: "ratio_implicito"`).

### 4. Actualización de código vs. datos en vivo
- Durante las actualizaciones periódicas **no existe caché de precios**: cada ciclo dentro del horario de mercado trae los valores frescos de IOL.
- Si un endpoint puntual falla momentáneamente (por ejemplo un corte breve de IOL), se aísla el fallo y se conserva el último dato válido del resto para no dejar toda la integración caída.

---

## Tickers Adicionales (`OptionsFlow`)

Podés agregar sensores fijos para otros activos sin tocar YAML:
1. Ve a **Ajustes → Dispositivos y servicios → InvertirOnline (IOL) → Configurar**.
2. En **Tickers adicionales**, escribí los símbolos separados por coma según el mercado:
   - **Bolsa argentina (`bCBA`, por defecto — CEDEARs, Acciones y Bonos en ARS):** escribí solo el símbolo (ej. `NVDA, GGAL, AL30, YPFD`) o explícitamente `bCBA:NVDA`.
   - **CEDEARs y Bonos en dólares (MEP / CCL):** agregá `D` o `C` al final del símbolo local (ej. `NVDAD, AL30D, AL30C`).
   - **Acciones originales de EE.UU. (en USD):** anteponé el mercado `NYSE:` o `NASDAQ:` (ej. `NYSE:KO, NASDAQ:AAPL, NASDAQ:NVDA`).
3. Opcionalmente ajustá el intervalo de actualización (`>= 15` minutos) y guardá. La integración se recargará automáticamente creando los nuevos sensores `sensor.iol_ticker_<simbolo>` (y limpiando los que hayas quitado).

---

## Tarjeta LED Marquee Prearmada (`invertironline-ticker-card`)

La integración registra automáticamente una tarjeta Lovelace estilo marquesina LED de Wall Street (`custom:invertironline-ticker-card`), sin necesidad de instalar recursos manuales:

```yaml
type: custom:invertironline-ticker-card
title: INVERTIRONLINE • BYMA
speed: 35
show_header: true
```

* Detecta automáticamente tus sensores `sensor.iol_*` (incluidos los `extra_tickers`) y actualiza los valores en tiempo real con cada refresco del coordinador sin reiniciar el desplazamiento.
* Podés pasarle una lista opcional `entities:` si querés mostrar solo ciertos activos.

---

## Consultas por Voz con Assist / LLM y Portafolio a Demanda

Para consultar activos o tu cartera bajo demanda sin llenar Home Assistant de sensores fijos, la integración expone cinco acciones (`SupportsResponse.ONLY`) y un sensor opcional:

### 1. `invertironline.get_quote`
- **Parámetros:**
  - `simbolo` (obligatorio): ej. `GGAL`, `AL30`, `AAPL`, `YPFD`.
  - `mercado` (opcional, por defecto `bCBA`): `bCBA`, `NYSE`, `NASDAQ`.
- **Ejemplos de uso con Assist / Agente LLM:**
  - *"¿A cuánto cotiza Galicia en InvertirOnline?"*
  - *"Consultá el precio del bono AL30 hoy."*

### 2. `invertironline.get_portfolio` (Cartera Completa a Demanda)
Consulta en vivo la cartera completa ordenada por monto valorizado, con ganancia y peso porcentual de cada activo:
- **Parámetros opcionales:**
  - `pais`: `Argentina` (por defecto) o `Estados_Unidos`.
  - `tipo`: filtro por tipo de instrumento (ej. `CEDEAR`, `Acciones`, `TitulosPublicos`, `FCI`).
- **Ejemplos de uso con Assist / Agente LLM:**
  - *"¿Cómo está compuesto mi portafolio de InvertirOnline?"*
  - *"Mostrame mis CEDEARs en InvertirOnline y cuánto gané."*

### 3. `invertironline.get_operations`
Consulta el historial de órdenes y operaciones en modo solo lectura (`estado`, `fecha_desde`, `fecha_hasta`, `pais`, `limite`).

### 4. `invertironline.get_market_panel`
Obtiene un panel completo del mercado (ej. `Acciones` / `Merval`, `CEDEARs`) ordenado por variación o volumen en una sola llamada (`instrumento`, `panel`, `pais`, `ordenar_por`, `limite`).

### 5. `invertironline.get_historical_quotes`
Obtiene la serie histórica OHLCV y la variación acumulada de un título entre dos fechas (`simbolo`, `fecha_desde`, `fecha_hasta`, `mercado`, `ajustada`).

### 6. Sensor opcional `sensor.iol_portafolio` (para Dashboards)
- Viene **deshabilitado por defecto** en el registro de entidades para no recargar tu interfaz si no lo necesitás.
- Si querés armar un dashboard con tu tenencia completa, habilitalo con 1 clic en **Ajustes → Dispositivos y servicios → InvertirOnline → Entidades** (no consume llamadas extra a la API porque reutiliza el portafolio que el coordinador ya trae).
- Podés mostrarlo en una **Tarjeta Markdown**:
  ```yaml
  type: markdown
  title: Mi Portafolio IOL
  content: |
    **Total:** ${{ state_attr('sensor.iol_portafolio', 'total_valorizado') }} ARS
    | Activo | Cant. | Valorizado | % |
    | :--- | ---: | ---: | ---: |
    {% for a in state_attr('sensor.iol_portafolio', 'activos') or [] -%}
    | {{ a.simbolo }} | {{ a.cantidad }} | ${{ a.valorizado }} | {{ a.peso_porcentaje }}% |
    {% endfor %}
  ```

---

## Instalación y Actualización Remota (Red Local)

1. Copia `.deploy.env.example` a `.deploy.env` (ignorado en `.gitignore`) y configurá tu IP y credenciales de Samba o SSH.
2. Ejecutá desde PowerShell:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\deploy_to_ha.ps1
   ```
3. **Importante al actualizar código Python:** Home Assistant mantiene los módulos `.py` en memoria hasta que se reinicia el proceso. Después de desplegar cambios de código con `deploy_to_ha.ps1`, hacé un **Reiniciar Home Assistant** completo (*Ajustes → Sistema → Reiniciar*).
4. En la primera instalación, agregá la integración desde **Ajustes → Dispositivos y servicios → Añadir integración → InvertirOnline (IOL)**.

---

## Tarjeta de Ejemplo para tu Dashboard (Lovelace)

```yaml
type: entities
title: InvertirOnline (IOL)
entities:
  - entity: sensor.iol_cuenta_total_ars
    name: Total en Pesos
  - entity: sensor.iol_cuenta_total_usd_mep
    name: Total en USD MEP
  - entity: sensor.iol_cuenta_total_usd_ccl
    name: Total en USD CCL
  - type: divider
  - entity: sensor.iol_cedear_spy
    name: CEDEAR SPY
  - entity: sensor.iol_caucion_1d
    name: Caución 1D
  - entity: sensor.iol_caucion_7d
    name: Caución 7D
  - entity: sensor.iol_caucion_14d
    name: Caución 14D
  - entity: sensor.iol_caucion_30d
    name: Caución 30D
```

---

## Automatizaciones de Referencia

### Reporte Matutino de Cauciones y Dólar
```yaml
alias: "Finanzas: Reporte Matutino de Cauciones y Dólar"
description: "Envía un resumen de tasas de caución y valuación MEP al celular a las 11:30 hs."
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
        Tasa Caución 1D: {{ states('sensor.iol_caucion_1d') }}% (Plazo real: {{ state_attr('sensor.iol_caucion_1d', 'plazo_dias_real') }}D)
        Tasa Caución 7D: {{ states('sensor.iol_caucion_7d') }}%
        Tasa Caución 30D: {{ states('sensor.iol_caucion_30d') }}%
        CEDEAR SPY: ${{ states('sensor.iol_cedear_spy') }} ARS ({{ state_attr('sensor.iol_cedear_spy', 'variacion_diaria') }}%)
        Cuenta USD MEP: ${{ states('sensor.iol_cuenta_total_usd_mep') }}
```

### Balance por Voz (TTS) al Llegar al Hogar
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

## Aviso Legal y Descargo de Responsabilidad (Disclaimer)

- **Integración no oficial:** Este proyecto es un desarrollo comunitario e independiente. **No es una integración oficial** ni está afiliada, asociada, autorizada, respaldada ni vinculada de ninguna manera con **InvertirOnline (IOL)** ni con sus empresas relacionadas. Todas las marcas comerciales, nombres de productos y logotipos pertenecen a sus respectivos propietarios.
- **Privacidad y alcance de los datos:** La integración se ejecuta localmente dentro de la instancia de Home Assistant configurada por el usuario y **no envía ni comparte credenciales, tokens ni información financiera fuera de dicho entorno**, operando bajo las premisas de seguridad, cifrado y control de acceso que disponga el propio ambiente Home Assistant del usuario (limitándose únicamente a consultar los endpoints públicos de IOL y de indicadores macroeconómicos configurados).
- **Alcance actual (solo lectura) y evolución futura:** En su versión actual, la integración opera **exclusivamente en modo solo lectura**, orientada a la exposición de indicadores financieros para monitoreo, alertas y toma de decisiones del usuario, sin ejecutar órdenes ni transacciones. No obstante, el proyecto no descarta evolucionar en versiones futuras para habilitar operaciones autenticadas por el usuario (tanto con confirmación *human-in-the-loop* como automatizadas sin *human-in-the-loop*), bajo estricta responsabilidad y configuración explícita del usuario.
- **Uso bajo propio riesgo:** La información mostrada tiene fines exclusivamente informativos y no constituye asesoramiento financiero ni recomendación de inversión. El autor y los colaboradores no asumen responsabilidad por demoras, interrupciones de servicio de terceros, diferencias de cotización ni decisiones tomadas a partir de los datos expuestos.

