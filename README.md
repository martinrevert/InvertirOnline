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
2. En **Tickers adicionales**, escribí los símbolos separados por coma:
   - Bolsa local (`bCBA` por defecto): `GGAL, AL30, YPFD`
   - Mercados del exterior: `NYSE:AAPL, NASDAQ:NVDA`
3. Opcionalmente ajustá el intervalo de actualización (`>= 15` minutos) y guardá. La integración se recargará automáticamente creando los nuevos sensores `sensor.iol_ticker_<simbolo>`.

---

## Consultas por Voz con Assist / LLM (`invertironline.get_quote`)

Para consultar cualquier activo bajo demanda sin llenar Home Assistant de sensores fijos, la integración expone la acción **`invertironline.get_quote`** (`SupportsResponse.ONLY`).

- **Parámetros:**
  - `simbolo` (obligatorio): ej. `GGAL`, `AL30`, `AAPL`, `YPFD`.
  - `mercado` (opcional, por defecto `bCBA`): `bCBA`, `NYSE`, `NASDAQ`.
- **Ejemplos de uso con Assist / Agente LLM:**
  - *"¿A cuánto cotiza Galicia en InvertirOnline?"*
  - *"Consultá el precio del bono AL30 hoy."*
  - *"¿Qué variación tuvo YPFD?"*

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
