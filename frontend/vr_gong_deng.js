/*
 * vr_gong_deng.js — 公众虚拟操作宫灯体验组件
 * 职责：
 *   1. 加载 VR Schema 并渲染滑块 + 燃料/灯型选择器
 *   2. 参数实时校验（分级、颜色、建议文案）
 *   3. 滑块操作 → 预测净化效果 delta（请求后端 /predict-delta）
 *   4. 教育科普内容渲染（按灯型，历史/原理/考古/对比）
 *   5. 与 3D 视图联动（setFlameIntensity / setBlockageVisual）
 * 与后端 VRGongDeng 模块对应。
 */
(function (global) {
  "use strict";

  function getEl(id) { return document.getElementById(id); }

  // ------------------------------------------------------------------
  // 1. 渲染 VR 控制面板（Schema 驱动）
  // ------------------------------------------------------------------
  function renderVrPanel(schema, onChangeHandlers) {
    const root = getEl("vr-panel");
    if (!root || !schema) return;
    const fi = schema.flame_intensity;
    const bd = schema.blockage_degree;
    const fuels = schema.fuel_types || [];
    const lamps = schema.lamp_types || [];

    // 滑块渲染
    function sliderRow(info) {
      const grades = (info.grades || []).map((g, i) =>
        `<div style="flex:1;text-align:center;padding:2px;font-size:10px;
                     background:${g.color}33;border-left:${i === 0 ? "none" : "1px solid #222"};
                     color:${g.color};font-weight:bold">${g.label}</div>`
      ).join("");
      return `
        <div class="vr-slider-row" style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <strong style="color:#E0B040">🔥 ${info.name}</strong>
            <span class="slider-feedback" id="feedback-${info.key}"
                  style="padding:2px 8px;border-radius:10px;font-size:11px;background:#333;">加载中...</span>
            <span class="info-icon" data-tip="${info.description}"
                  style="cursor:help;color:#8899bb;margin-left:6px" title="${info.description}">?</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:11px;color:#888;width:28px">${info.min}</span>
            <input type="range" id="${info.key}-slider" min="${info.min}" max="${info.max}"
                   step="0.01" value="${info.default}" style="flex:1">
            <span id="${info.key}-val" style="font-family:monospace;width:42px;text-align:right;color:#FFC107">${parseFloat(info.default).toFixed(2)}</span>
          </div>
          <div style="display:flex;margin-top:2px;border-radius:4px;overflow:hidden">${grades}</div>
          <div style="margin-top:4px;font-size:11px;color:#99aac5">
            推荐区间 [<strong style="color:#4CAF50">${info.recommended_range[0]}</strong>,
            <strong style="color:#4CAF50">${info.recommended_range[1]}</strong>]
          </div>
        </div>`;
    }

    // 燃料选择器
    const fuelHtml = `
      <div class="vr-select-row" style="margin-bottom:10px">
        <strong style="color:#81C784">🛢️ 灯油燃料</strong>
        <select id="fuel-select" style="width:100%;padding:4px;margin-top:4px">
          ${fuels.map(f => `<option value="${f.key}" data-smoke="${f.smoke_factor}">${f.name}</option>`).join("")}
        </select>
        <div id="fuel-historical-note" style="margin-top:4px;font-size:11px;color:#99aac5;font-style:italic"></div>
      </div>`;

    // 灯型切换
    const lampHtml = `
      <div class="vr-select-row" style="margin-bottom:10px">
        <strong style="color:#64B5F6">🏮 灯具类型</strong>
        <select id="lamp-select" style="width:100%;padding:4px;margin-top:4px">
          ${lamps.map(l => `<option value="${l.key}">${l.dynasty || ""}${l.name || l.key}</option>`).join("")}
        </select>
      </div>`;

    root.innerHTML = `
      <div class="vr-panel-inner" style="padding:8px">
        <h4 style="margin:0 0 8px 0;color:#FFB74D">🎮 虚拟操作宫灯</h4>
        ${sliderRow(fi)}
        ${sliderRow(bd)}
        ${fuelHtml}
        ${lampHtml}
        <button id="btn-apply-vr"
                style="width:100%;padding:8px;margin-top:6px;
                       background:linear-gradient(135deg,#E0B040,#FF8A65);
                       border:none;border-radius:4px;color:#fff;font-weight:bold;cursor:pointer">
          ✨ 应用到仿真并实时观察
        </button>
      </div>`;

    // 绑定事件
    _bindVrEvents(schema, onChangeHandlers || {});
    // 渲染初始燃料说明
    if (fuels[0]) {
      const note = getEl("fuel-historical-note");
      if (note) note.textContent = fuels[0].historical_note || "";
    }
  }

  // ------------------------------------------------------------------
  // 2. 绑定 VR 交互事件
  // ------------------------------------------------------------------
  function _bindVrEvents(schema, handlers) {
    const fiSlider = getEl("flame_intensity-slider");
    const bdSlider = getEl("blockage_degree-slider");
    const fiVal = getEl("flame_intensity-val");
    const bdVal = getEl("blockage_degree-val");
    const fuelSel = getEl("fuel-select");
    const lampSel = getEl("lamp-select");
    const applyBtn = getEl("btn-apply-vr");

    // 火焰滑块
    if (fiSlider) {
      fiSlider.addEventListener("input", (e) => {
        const v = parseFloat(e.target.value);
        fiVal.textContent = v.toFixed(2);
        updateFlameFeedback(v, schema);
        if (typeof window.setFlameIntensity === "function") window.setFlameIntensity(v);
        if (handlers.onFlameChange) handlers.onFlameChange(v);
      });
      // 触发初始
      setTimeout(() => updateFlameFeedback(parseFloat(fiSlider.value), schema), 50);
    }
    // 堵塞滑块
    if (bdSlider) {
      bdSlider.addEventListener("input", (e) => {
        const v = parseFloat(e.target.value);
        bdVal.textContent = v.toFixed(2);
        updateBlockageFeedback(v, schema);
        if (typeof window.setBlockageVisual === "function") window.setBlockageVisual(v);
        if (handlers.onBlockageChange) handlers.onBlockageChange(v);
      });
      setTimeout(() => updateBlockageFeedback(parseFloat(bdSlider.value), schema), 50);
    }
    // 燃料切换
    if (fuelSel) {
      fuelSel.addEventListener("change", (e) => {
        const op = fuelSel.querySelector("option:checked");
        const note = getEl("fuel-historical-note");
        const fuels = schema.fuel_types || [];
        const f = fuels.find(x => x.key === e.target.value);
        if (note && f) note.textContent = f.historical_note || "";
        if (handlers.onFuelChange) handlers.onFuelChange(e.target.value, op ? parseFloat(op.dataset.smoke) : 1.0);
      });
    }
    // 灯型切换 → 3D 视图 + 教育内容
    if (lampSel) {
      lampSel.addEventListener("change", (e) => {
        if (typeof window.switchLampType === "function") window.switchLampType(e.target.value);
        if (handlers.onLampChange) handlers.onLampChange(e.target.value);
        // 加载教育内容
        VRGongDengUI.loadEducation(e.target.value);
      });
    }
    // 应用按钮
    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        if (handlers.onApply) {
          handlers.onApply({
            flame_intensity: parseFloat(fiSlider.value),
            blockage_degree: parseFloat(bdSlider.value),
            fuel_type: fuelSel.value,
            lamp_type: lampSel.value,
          });
        }
      });
    }
  }

  // ------------------------------------------------------------------
  // 3. 滑块反馈文字 + 颜色
  // ------------------------------------------------------------------
  function updateFlameFeedback(val, schema) {
    const el = getEl("feedback-flame_intensity");
    if (!el) return;
    const info = schema.flame_intensity;
    const grades = info.grades || [];
    let label = "未知", color = "#888";
    for (const g of grades) {
      if (val <= g.threshold) { label = g.label; color = g.color; break; }
    }
    let level;
    if (val < info.warning_range[0]) level = "偏低";
    else if (val > info.warning_range[1]) level = "过高";
    else if (val >= info.recommended_range[0] && val <= info.recommended_range[1]) level = "推荐";
    else level = "可接受";
    el.textContent = `${label} · ${level}`;
    el.style.background = color + "33";
    el.style.color = color;
    el.style.border = `1px solid ${color}`;
  }

  function updateBlockageFeedback(val, schema) {
    const el = getEl("feedback-blockage_degree");
    if (!el) return;
    const info = schema.blockage_degree;
    const grades = info.grades || [];
    let label = "未知", color = "#888";
    for (const g of grades) {
      if (val <= g.threshold) { label = g.label; color = g.color; break; }
    }
    let level;
    if (val >= info.warning_range[0] && val <= info.warning_range[1]) level = "需清洁";
    else if (val > info.warning_range[1]) level = "严重堵塞";
    else if (val <= info.recommended_range[1]) level = "良好";
    else level = "一般";
    el.textContent = `${label} · ${level}`;
    el.style.background = color + "33";
    el.style.color = color;
    el.style.border = `1px solid ${color}`;
  }

  // ------------------------------------------------------------------
  // 4. 预测净化效果 delta（用于 slider 拖动实时反馈）
  // ------------------------------------------------------------------
  async function predictDelta(apiBase, params) {
    const url = (apiBase || "/api") + "/comparison/vr/predict-delta";
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!resp.ok) throw new Error("Delta 请求失败: " + resp.status);
    return await resp.json();
  }

  // 渲染 delta 反馈条
  function renderDeltaFeedback(delta) {
    const root = getEl("vr-delta-feedback");
    if (!root || !delta) return;
    const colorMap = {
      improvement: "#4CAF50", neutral: "#9E9E9E",
      degradation: "#FF9800", warning: "#F44336",
    };
    const c = colorMap[delta.feedback_level] || "#888";
    const iconMap = {
      improvement: "✅", neutral: "➖", degradation: "⚠️", warning: "🚨",
    };
    const html = `
      <div style="background:${c}22;padding:6px 10px;border-left:4px solid ${c};
                  border-radius:4px;font-size:12px;margin-top:8px">
        <strong style="color:${c}">${iconMap[delta.feedback_level] || ""} 变化：</strong>
        ${delta.feedback_text || ""}
        <div style="margin-top:4px;opacity:0.85">
          沉降效率 ${delta.delta_settling_efficiency_pct > 0 ? "+" : ""}${delta.delta_settling_efficiency_pct}%，
          PM2.5 ${delta.delta_pm25_ugm3 > 0 ? "+" : ""}${delta.delta_pm25_ugm3} μg/m³
        </div>
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 5. 加载并渲染教育科普内容
  // ------------------------------------------------------------------
  async function loadEducation(lampType, apiBase) {
    const root = getEl("vr-education-panel");
    if (!root) return;
    root.innerHTML = '<div style="padding:10px;color:#8899bb">📚 加载科普内容中...</div>';
    try {
      const url = (apiBase || "/api") + "/comparison/vr/education/" + encodeURIComponent(lampType);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(resp.status);
      const facts = await resp.json();
      _renderEducationFacts(facts);
    } catch (e) {
      root.innerHTML = `<div style="padding:10px;color:#F44336">❌ 科普内容加载失败: ${e.message}</div>`;
    }
  }

  function _renderEducationFacts(facts) {
    const root = getEl("vr-education-panel");
    if (!root) return;
    const sections = [
      { key: "general_history", title: "🏛️ 历史背景", color: "#E0B040" },
      { key: "fluid_mechanics_principle", title: "🔬 流体力学原理", color: "#2196F3" },
      { key: "archaeological_findings", title: "📜 考古发现", color: "#9C27B0" },
      { key: "modern_comparison", title: "⚖️ 现代对比", color: "#4CAF50" },
    ];
    let html = `<h4 style="margin:0 0 8px 0;color:#FFB74D">📚 科普教育 · ${facts.lamp_type}</h4>`;
    sections.forEach((s) => {
      const items = facts[s.key] || [];
      if (!items.length) return;
      html += `<details open style="margin:4px 0;background:#1f2536;border-radius:4px;padding:6px 8px">
        <summary style="cursor:pointer;color:${s.color};font-weight:bold;font-size:13px">${s.title}</summary>
        <ul style="margin:6px 0 2px 0;padding-left:18px;font-size:12px;color:#cdd6e8;line-height:1.7">`;
      items.forEach((i) => { html += `<li>${i}</li>`; });
      html += "</ul></details>";
    });
    // 参数特定科普
    const ps = facts.parameter_specific || {};
    const paramKeys = {
      flame_intensity: "🔥 火焰强度的影响",
      blockage_degree: "🧹 烟道堵塞的影响",
      fuel_type: "🛢️ 燃料差异",
    };
    for (const [k, items] of Object.entries(ps)) {
      if (!items.length) continue;
      html += `<details style="margin:4px 0;background:#1f2536;border-radius:4px;padding:6px 8px">
        <summary style="cursor:pointer;color:#FF9800;font-weight:bold;font-size:13px">${paramKeys[k] || k}</summary>
        <ul style="margin:6px 0 2px 0;padding-left:18px;font-size:12px;color:#cdd6e8;line-height:1.7">`;
      items.forEach((i) => { html += `<li>${i}</li>`; });
      html += "</ul></details>";
    }
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 6. 加载 VR Schema
  // ------------------------------------------------------------------
  async function loadVrSchema(apiBase) {
    const url = (apiBase || "/api") + "/comparison/vr/schema";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("Schema 请求失败: " + resp.status);
    return await resp.json();
  }

  // 暴露公共接口
  global.VRGongDengUI = {
    renderVrPanel,
    updateFlameFeedback,
    updateBlockageFeedback,
    predictDelta,
    renderDeltaFeedback,
    loadEducation,
    loadVrSchema,
  };
})(typeof window !== "undefined" ? window : this);
