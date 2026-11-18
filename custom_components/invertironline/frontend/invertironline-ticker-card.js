const CARD_TAG = "invertironline-ticker-card";
const DEFAULT_ENTITIES = [
  "sensor.iol_cedear_spy",
  "sensor.iol_dolar_mep",
  "sensor.iol_dolar_ccl",
  "sensor.iol_caucion_1d",
  "sensor.iol_caucion_7d",
  "sensor.iol_caucion_14d",
  "sensor.iol_caucion_30d",
  "sensor.iol_caucion_60d",
  "sensor.iol_cuenta_total_ars",
  "sensor.iol_cuenta_total_usd_mep",
  "sensor.iol_portafolio_ganancia",
  "sensor.iol_inflacion_mensual",
  "sensor.iol_inflacion_mensual_usd",
];

const SHORT_LABELS = {
  "sensor.iol_cedear_spy": "SPY",
  "sensor.iol_dolar_mep": "USD MEP",
  "sensor.iol_dolar_ccl": "USD CCL",
  "sensor.iol_caucion_1d": "CAU 1D",
  "sensor.iol_caucion_7d": "CAU 7D",
  "sensor.iol_caucion_14d": "CAU 14D",
  "sensor.iol_caucion_30d": "CAU 30D",
  "sensor.iol_caucion_60d": "CAU 60D",
  "sensor.iol_cuenta_total_ars": "CUENTA ARS",
  "sensor.iol_cuenta_total_usd_mep": "CUENTA MEP",
  "sensor.iol_cuenta_total_usd_ccl": "CUENTA CCL",
  "sensor.iol_disponible_ars": "DISP ARS",
  "sensor.iol_disponible_usd": "DISP USD",
  "sensor.iol_portafolio_ganancia": "GANANCIA",
  "sensor.iol_inflacion_mensual": "IPC MES",
  "sensor.iol_inflacion_interanual": "IPC 12M",
  "sensor.iol_inflacion_mensual_usd": "IPC USD MES",
  "sensor.iol_inflacion_interanual_usd": "IPC USD 12M",
};

class InvertirOnlineTickerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._renderedSignature = "";
    this._prevValues = new Map();
  }

  static getStubConfig() {
    return {
      title: "INVERTIRONLINE • BYMA",
      speed: 35,
      show_header: true,
      priority: [
        "sensor.iol_dolar_mep",
        "sensor.iol_dolar_ccl",
        "sensor.iol_cedear_spy",
      ],
    };
  }

  setConfig(config) {
    this._config = {
      title: config?.title ?? "INVERTIRONLINE • BYMA",
      speed: Number(config?.speed) > 0 ? Number(config.speed) : 35,
      show_header: config?.show_header !== false,
      entities: Array.isArray(config?.entities) ? config.entities : null,
      priority: Array.isArray(config?.priority) ? config.priority : [],
    };
    this._renderedSignature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 2;
  }

  _isValidState(entityId) {
    const stateObj = this._hass?.states?.[entityId];
    if (!stateObj) return false;
    const raw = stateObj.state;
    return (
      raw !== "unknown" &&
      raw !== "unavailable" &&
      raw !== null &&
      raw !== undefined &&
      String(raw).trim() !== ""
    );
  }

  _resolveEntities() {
    if (!this._hass?.states) return [];
    let ordered;
    if (this._config.entities && this._config.entities.length > 0) {
      ordered = this._config.entities.filter((id) => this._isValidState(id));
    } else {
      const base = DEFAULT_ENTITIES.filter((id) => this._isValidState(id));
      const extras = Object.keys(this._hass.states)
        .filter((id) => id.startsWith("sensor.iol_ticker_") && this._isValidState(id))
        .sort();
      ordered = [...base, ...extras];
    }

    if (this._config.priority && this._config.priority.length > 0) {
      const priorityValid = this._config.priority.filter((id) => this._isValidState(id));
      const prioritySet = new Set(priorityValid);
      ordered = [...priorityValid, ...ordered.filter((id) => !prioritySet.has(id))];
    }
    return ordered;
  }

  _formatLabel(entityId, stateObj) {
    if (SHORT_LABELS[entityId]) return SHORT_LABELS[entityId];
    if (entityId.startsWith("sensor.iol_ticker_")) {
      return entityId
        .replace("sensor.iol_ticker_", "")
        .replace(/^(bcba|nyse|nasdaq)_/i, "")
        .toUpperCase();
    }
    return (stateObj.attributes?.friendly_name || entityId).toUpperCase();
  }

  _formatValue(stateObj) {
    const raw = stateObj.state;
    if (raw === "unavailable" || raw === "unknown" || raw === null || raw === undefined) {
      return "--";
    }
    const num = Number(raw);
    const unit = stateObj.attributes?.unit_of_measurement || "";
    if (!Number.isFinite(num)) {
      return `${raw}${unit ? " " + unit : ""}`;
    }
    const formatted = num.toLocaleString("es-AR", {
      minimumFractionDigits: unit === "%" ? 2 : 0,
      maximumFractionDigits: 2,
    });
    if (unit === "ARS") return `$${formatted}`;
    if (unit === "USD") return `US$${formatted}`;
    if (unit === "%") return `${formatted}%`;
    return `${formatted}${unit ? " " + unit : ""}`;
  }

  _buildItemData(entityId) {
    const stateObj = this._hass.states[entityId];
    if (!stateObj) return null;

    const label = this._formatLabel(entityId, stateObj);
    const value = this._formatValue(stateObj);
    const varDaily = stateObj.attributes?.variacion_diaria;
    const hasVar = varDaily !== undefined && varDaily !== null && Number.isFinite(Number(varDaily));
    const varNum = hasVar ? Number(varDaily) : null;

    let trendClass = "neutral";
    let trendText = "";
    if (varNum !== null) {
      if (varNum > 0) {
        trendClass = "up";
        trendText = `▲ ${varNum.toFixed(2)}%`;
      } else if (varNum < 0) {
        trendClass = "down";
        trendText = `▼ ${Math.abs(varNum).toFixed(2)}%`;
      } else {
        trendClass = "flat";
        trendText = `• 0.00%`;
      }
    }

    return { entityId, label, value, trendClass, trendText };
  }

  _openMoreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId },
      })
    );
  }

  _render() {
    if (!this.shadowRoot || !this._hass) return;

    const entityIds = this._resolveEntities();
    const items = entityIds.map((id) => this._buildItemData(id)).filter(Boolean);

    const marketState = this._hass.states["binary_sensor.iol_mercado_abierto"]?.state;
    const isMarketOpen = marketState === "on";
    const lastUpdState = this._hass.states["sensor.iol_ultima_actualizacion"];
    const lastUpdLocal = lastUpdState?.attributes?.fecha_hora_local
      ? lastUpdState.attributes.fecha_hora_local.slice(11, 19)
      : "";

    const signature = `${this._config.title}|${this._config.speed}|${this._config.show_header}|${entityIds.join(",")}`;

    if (signature !== this._renderedSignature) {
      this._renderedSignature = signature;
      this.shadowRoot.innerHTML = `
        <style>
          :host {
            display: block;
          }
          ha-card {
            background: #06090e;
            border: 1px solid #1b2838;
            border-radius: 12px;
            overflow: hidden;
            position: relative;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.55);
          }
          .led-screen {
            position: relative;
            background: radial-gradient(circle at 50% 50%, #0d1520 0%, #05080d 100%);
            padding: ${this._config.show_header ? "8px 0 10px" : "10px 0"};
            font-family: "Consolas", "Monaco", "Courier New", monospace;
          }
          /* LED pixel dot-matrix grid overlay */
          .led-screen::after {
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background-image:
              linear-gradient(rgba(0, 0, 0, 0.42) 1px, transparent 1px),
              linear-gradient(90deg, rgba(0, 0, 0, 0.42) 1px, transparent 1px);
            background-size: 3px 3px;
            z-index: 2;
          }
          .header {
            display: ${this._config.show_header ? "flex" : "none"};
            align-items: center;
            justify-content: space-between;
            padding: 0 14px 6px;
            border-bottom: 1px solid rgba(0, 229, 255, 0.14);
            margin-bottom: 8px;
            font-size: 11px;
            letter-spacing: 1.4px;
            color: #00e5ff;
            text-shadow: 0 0 6px rgba(0, 229, 255, 0.55);
          }
          .status-group {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #94a3b8;
            font-size: 10px;
          }
          .last-upd {
            cursor: pointer;
          }
          .last-upd:hover {
            color: #00e5ff;
          }
          .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-weight: 700;
          }
          .status-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #ff3b5c;
            box-shadow: 0 0 6px #ff3b5c;
          }
          .status-dot.open {
            background: #00ff66;
            box-shadow: 0 0 8px #00ff66;
          }
          .marquee-viewport {
            overflow: hidden;
            white-space: nowrap;
            width: 100%;
            position: relative;
          }
          .marquee-track {
            display: inline-flex;
            align-items: center;
            animation: iol-marquee ${this._config.speed}s linear infinite;
          }
          .marquee-viewport:hover .marquee-track {
            animation-play-state: paused;
          }
          @keyframes iol-marquee {
            0% {
              transform: translate3d(0, 0, 0);
            }
            100% {
              transform: translate3d(-50%, 0, 0);
            }
          }
          @keyframes iol-flash {
            0% {
              background: rgba(0, 229, 255, 0.25);
            }
            100% {
              background: transparent;
            }
          }
          .marquee-group {
            display: inline-flex;
            align-items: center;
          }
          .ticker-item {
            display: inline-flex;
            align-items: baseline;
            gap: 7px;
            padding: 2px 18px;
            cursor: pointer;
            border-right: 1px solid rgba(148, 163, 184, 0.16);
          }
          .ticker-item.flash {
            animation: iol-flash 1.4s ease-out;
          }
          .ticker-item:hover {
            background: rgba(0, 229, 255, 0.08);
          }
          .sym {
            color: #00e5ff;
            font-weight: 800;
            font-size: 14px;
            letter-spacing: 1px;
            text-shadow: 0 0 7px rgba(0, 229, 255, 0.65);
          }
          .val {
            color: #f8fafc;
            font-weight: 700;
            font-size: 15px;
            letter-spacing: 0.6px;
            text-shadow: 0 0 6px rgba(248, 250, 252, 0.45);
          }
          .trend {
            font-weight: 800;
            font-size: 13px;
            letter-spacing: 0.5px;
          }
          .trend.up {
            color: #00ff66;
            text-shadow: 0 0 8px rgba(0, 255, 102, 0.7);
          }
          .trend.down {
            color: #ff3b5c;
            text-shadow: 0 0 8px rgba(255, 59, 92, 0.7);
          }
          .trend.flat {
            color: #ffd166;
            text-shadow: 0 0 6px rgba(255, 209, 102, 0.55);
          }
          .empty {
            padding: 8px 16px;
            color: #ffd166;
            font-size: 13px;
            text-shadow: 0 0 6px rgba(255, 209, 102, 0.5);
          }
        </style>
        <ha-card>
          <div class="led-screen">
            <div class="header">
              <span class="title"></span>
              <span class="status-group">
                <span class="last-upd" title="Última actualización real"></span>
                <span class="status-pill">
                  <span class="status-dot"></span>
                  <span class="status-text"></span>
                </span>
              </span>
            </div>
            <div class="marquee-viewport">
              <div class="marquee-track">
                <div class="marquee-group" data-group="a"></div>
                <div class="marquee-group" data-group="b"></div>
              </div>
            </div>
          </div>
        </ha-card>
      `;

      const titleEl = this.shadowRoot.querySelector(".title");
      if (titleEl) titleEl.textContent = this._config.title;

      const lastUpdElInit = this.shadowRoot.querySelector(".last-upd");
      if (lastUpdElInit) {
        lastUpdElInit.addEventListener("click", () =>
          this._openMoreInfo("sensor.iol_ultima_actualizacion")
        );
      }

      const buildGroup = (groupEl) => {
        if (!groupEl) return;
        groupEl.innerHTML = "";
        if (items.length === 0) {
          const emptyEl = document.createElement("span");
          emptyEl.className = "empty";
          emptyEl.textContent = "SIN ENTIDADES IOL DISPONIBLES";
          groupEl.appendChild(emptyEl);
          return;
        }
        for (const item of items) {
          const el = document.createElement("div");
          el.className = "ticker-item";
          el.dataset.entity = item.entityId;
          el.innerHTML = `
            <span class="sym"></span>
            <span class="val"></span>
            <span class="trend"></span>
          `;
          el.addEventListener("click", () => this._openMoreInfo(item.entityId));
          groupEl.appendChild(el);
        }
      };

      buildGroup(this.shadowRoot.querySelector('[data-group="a"]'));
      buildGroup(this.shadowRoot.querySelector('[data-group="b"]'));
    }

    // Update live values in-place on every hass state push
    const dotEl = this.shadowRoot.querySelector(".status-dot");
    const statusTextEl = this.shadowRoot.querySelector(".status-text");
    const lastUpdEl = this.shadowRoot.querySelector(".last-upd");
    if (dotEl && statusTextEl) {
      dotEl.classList.toggle("open", isMarketOpen);
      statusTextEl.textContent = isMarketOpen ? "BYMA ABIERTA" : "CERRADO";
      statusTextEl.style.color = isMarketOpen ? "#00ff66" : "#ff3b5c";
    }
    if (lastUpdEl) {
      lastUpdEl.textContent = lastUpdLocal ? `ACT ${lastUpdLocal}` : "";
    }

    const itemMap = new Map(items.map((it) => [it.entityId, it]));
    for (const node of this.shadowRoot.querySelectorAll(".ticker-item")) {
      const entityId = node.dataset.entity;
      const data = itemMap.get(entityId);
      if (!data) continue;

      const prevKey = this._prevValues.get(entityId);
      const currKey = `${data.value}|${data.trendText}`;
      const symEl = node.querySelector(".sym");
      const valEl = node.querySelector(".val");
      const trendEl = node.querySelector(".trend");
      if (symEl) symEl.textContent = data.label;
      if (valEl) valEl.textContent = data.value;
      if (trendEl) {
        trendEl.textContent = data.trendText;
        trendEl.className = `trend ${data.trendClass}`;
        trendEl.style.display = data.trendText ? "inline" : "none";
      }

      if (prevKey !== undefined && prevKey !== currKey) {
        node.classList.remove("flash");
        void node.offsetWidth;
        node.classList.add("flash");
      }
    }

    for (const item of items) {
      this._prevValues.set(item.entityId, `${item.value}|${item.trendText}`);
    }
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, InvertirOnlineTickerCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "InvertirOnline LED Ticker",
    description: "Marquesina LED horizontal estilo Wall Street con cotizaciones y tasas de IOL en vivo.",
    preview: true,
  });
}
