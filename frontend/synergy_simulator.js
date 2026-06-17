/*
 * synergy_simulator.js — 多盏宫灯宴会场景协同净化组件
 * 职责：
 *   1. 场景列表渲染 + 场景切换
 *   2. 算法参数配置面板（叠加策略、衰减指数）
 *   3. 每盏灯详细数据（位置/影响格点/沉降效率）
 *   4. 协同指数分析渲染
 *   5. 触发后端宴会仿真
 * 与后端 SynergySimulator 模块对应。
 */
(function (global) {
  "use strict";

  const LAMP_NAMES = {
    changxin_gongdeng: "长信宫灯",
    yanyu_deng: "雁鱼灯",
    niu_deng: "错银铜牛灯",
  };

  function getEl(id) { return document.getElementById(id); }

  // ------------------------------------------------------------------
  // 1. 渲染场景选择器
  // ------------------------------------------------------------------
  function renderSceneSelector(scenesCfg, currentSceneKey, onChange) {
    const root = getEl("banquet-scene-selector");
    if (!root) return;
    const scenes = scenesCfg.scenes || {};
    const keys = Object.keys(scenes);
    let html = '<label>📐 宴会场景：</label><select id="scene-select" style="padding:4px 8px">';
    keys.forEach((k) => {
      const s = scenes[k];
      const sel = (k === currentSceneKey) ? " selected" : "";
      const desc = s.description ? `（${s.description}）` : "";
      html += `<option value="${k}"${sel}>${s.name || k}${desc}</option>`;
    });
    html += "</select>";
    root.innerHTML = html;
    const sel = root.querySelector("select");
    if (sel && onChange) sel.addEventListener("change", () => onChange(sel.value));
  }

  // ------------------------------------------------------------------
  // 2. 渲染算法参数面板
  // ------------------------------------------------------------------
  function renderAlgorithmPanel(algoParams, onStrategyChange) {
    const root = getEl("banquet-algo-panel");
    if (!root) return;
    const strat = algoParams.overlap_strategy || "min";
    const STRATEGIES = [
      { k: "min", name: "最强净化(min)", desc: "最乐观：取所有可达灯中的最低浓度" },
      { k: "mean", name: "平均净化(mean)", desc: "折中：所有可达灯净化浓度算术平均" },
      { k: "sum", name: "线性叠加(sum)", desc: "假设独立：净化量直接相加" },
      { k: "max", name: "最弱净化(max)", desc: "最保守：取所有可达灯中的最高浓度" },
    ];
    let html = `
      <div class="algo-panel" style="background:#1f2536;padding:10px;border-radius:6px">
        <h5 style="margin:0 0 8px 0;color:#FF9800">⚙️ 算法参数</h5>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px">
          <div>叠加策略：
            <select id="overlap-strategy" style="padding:3px 6px">`;
    STRATEGIES.forEach((s) => {
      html += `<option value="${s.k}"${s.k === strat ? " selected" : ""}>${s.name}</option>`;
    });
    html += `</select>
          </div>
          <div>衰减指数：<code>${algoParams.purification_falloff_exponent || 2.0}</code></div>
          <div>高斯源系数：<code>${algoParams.emission_source_sigma_multiplier || 1.0}</code></div>
          <div>网格：${algoParams.grid_origin || "[0,0,0]"}</div>
        </div>
        <div id="strategy-desc" style="margin-top:6px;font-size:12px;color:#99aac5">
          ${STRATEGIES.find(x => x.k === strat).desc}
        </div>
      </div>`;
    root.innerHTML = html;
    const sel = root.querySelector("#overlap-strategy");
    const descEl = root.querySelector("#strategy-desc");
    if (sel) {
      sel.addEventListener("change", () => {
        const s = STRATEGIES.find(x => x.k === sel.value);
        if (descEl && s) descEl.textContent = s.desc;
        if (onStrategyChange) onStrategyChange(sel.value);
      });
    }
  }

  // ------------------------------------------------------------------
  // 3. 渲染每盏灯数据
  // ------------------------------------------------------------------
  function renderPerLampData(perLampCfd) {
    const root = getEl("banquet-per-lamp-panel");
    if (!root) return;
    if (!perLampCfd || !perLampCfd.length) { root.innerHTML = ""; return; }
    let html = `
      <div class="per-lamp-panel" style="background:#1f2536;padding:10px;border-radius:6px">
        <h5 style="margin:0 0 8px 0;color:#6BCF7C">💡 ${perLampCfd.length} 盏宫灯协同详情</h5>
        <table class="mini-table" style="width:100%;font-size:12px;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid #333">
            <th>灯</th><th>位置(m)</th><th>网格</th><th>沉降率</th><th>影响格点</th><th>局部均浓</th>
          </tr></thead><tbody>`;
    perLampCfd.forEach((p) => {
      const wp = p.world_position || p.position || {};
      const gp = p.grid_position || {};
      const wpx = Array.isArray(wp) ? wp[0] : (wp.x_m || 0);
      const wpy = Array.isArray(wp) ? wp[1] : (wp.y_m || 0);
      const wpz = Array.isArray(wp) ? wp[2] : (wp.z_m || 0);
      const gpi = Array.isArray(gp) ? gp[0] : (gp.i ?? "—");
      const gpj = Array.isArray(gp) ? gp[1] : (gp.j ?? "—");
      const gpk = Array.isArray(gp) ? gp[2] : (gp.k ?? "—");
      const se = p.settling_efficiency || (p.cfd && p.cfd.settling_efficiency) || 0;
      const pts = p.affected_grid_points || "—";
      const avg = p.avg_concentration_in_radius != null ? p.avg_concentration_in_radius.toFixed(2) : "—";
      const name = LAMP_NAMES[p.lamp_type] || p.lamp_type;
      html += `<tr style="border-bottom:1px dotted #2c3348">
        <td style="padding:4px;color:#E0B040">${p.lamp_index || ""}.${name}</td>
        <td>(${wpx},${wpy},${wpz})</td>
        <td>(${gpi},${gpj},${gpk})</td>
        <td style="color:#4CAF50">${(se * 100).toFixed(1)}%</td>
        <td>${pts}</td>
        <td>${avg} μg/m³</td>
      </tr>`;
    });
    html += "</tbody></table></div>";
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 4. 协同指数分析
  // ------------------------------------------------------------------
  function renderSynergyAnalysis(synergy) {
    const root = getEl("banquet-synergy-panel");
    if (!root || !synergy) return;
    const idx = synergy.synergy_index || 0;
    const color = idx > 1.0 ? "#4CAF50" : idx > 0.5 ? "#FF9800" : "#F44336";
    const interp = synergy.synergy_interpretation || "";
    const conc = synergy.conclusion || "";
    const html = `
      <div class="synergy-analysis" style="background:#1f2536;padding:10px;border-radius:6px">
        <h5 style="margin:0 0 8px 0;color:#9C27B0">🔗 协同分析</h5>
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:6px">
          <div style="flex:1">
            <div style="font-size:11px;color:#99aac5">协同指数 SI</div>
            <div style="font-size:32px;font-weight:bold;color:${color}">${idx.toFixed(2)}</div>
            <div style="font-size:11px;color:#99aac5">理想值>1.0 (1+1>2)</div>
          </div>
          <div style="flex:2">
            <div>净化速率：<strong style="color:#6BCF7C">+${synergy.purification_rate_improvement_pct_points} pct</strong></div>
            <div>PM2.5 下降：<strong style="color:#6BCF7C">${synergy.avg_pm25_reduction_ugm3} μg/m³</strong></div>
            <div>叠加策略：<code>${synergy.overlap_strategy}</code> — ${synergy.overlap_strategy_description || ""}</div>
          </div>
        </div>
        <div style="background:#262d44;padding:6px 8px;border-radius:4px;font-size:12px;color:#cdd6e8;line-height:1.6">
          <strong style="color:${color}">${interp}</strong><br>
          ${conc}
        </div>
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 5. 宴会 vs 单灯基线对比卡
  // ------------------------------------------------------------------
  function renderBaselineCompare(banquetResult, singleBaseline) {
    const root = getEl("banquet-baseline-compare");
    if (!root) return;
    function row(label, multi, single, better, fmt) {
      const f = fmt || (v => v.toFixed(2));
      let mc = "#fff", sc = "#fff";
      const mv = (multi != null) ? multi : 0;
      const sv = (single != null) ? single : 0;
      if (better === "low") {
        if (mv < sv) mc = "#4CAF50"; else if (mv > sv) sc = "#4CAF50";
      } else {
        if (mv > sv) mc = "#4CAF50"; else if (mv < sv) sc = "#4CAF50";
      }
      return `<tr><td class="label" style="padding:3px 6px">${label}</td>
              <td style="color:${mc};padding:3px 6px;text-align:center">${f(mv)}</td>
              <td style="color:${sc};padding:3px 6px;text-align:center">${f(sv)}</td></tr>`;
    }
    const html = `
      <div style="background:#1f2536;padding:10px;border-radius:6px">
        <h5 style="margin:0 0 6px 0;color:#2196F3">📊 宴会多灯 vs 单灯基线</h5>
        <table style="width:100%;font-size:12px;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid #333">
            <th>指标</th><th>宴会(${banquetResult ? "多灯" : "-"})</th><th>单灯基线</th>
          </tr></thead><tbody>
            ${row("净化率", banquetResult && banquetResult.purification_rate, singleBaseline && singleBaseline.purification_rate, "high", (v) => (v * 100).toFixed(1) + "%")}
            ${row("平均 PM2.5(μg/m³)", banquetResult && banquetResult.avg_pm25, singleBaseline && singleBaseline.avg_pm25, "low")}
            ${row("AQI 等级", banquetResult && banquetResult.aqi_level, singleBaseline && singleBaseline.aqi_level, "low", v => v || "-")}
          </tbody></table>
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 6. 触发后端宴会仿真
  // ------------------------------------------------------------------
  async function runBanquetSimulation(apiBase, params) {
    const url = (apiBase || "/api") + "/comparison/banquet-simulation";
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {
        scene_key: "royal_banquet",
        base_pm25_ugm3: 45.0,
        air_change_rate_ach: 0.5,
        outdoor_pm25_ugm3: 35.0,
        ambient_temperature_c: 22.0,
        ambient_humidity_percent: 50.0,
        flue_temperature_c: 150.0,
        flue_velocity_ms: 0.4,
        fuel_type: "animal_fat",
        overlap_strategy: "min",
        debug_log: false,
      }),
    });
    if (!resp.ok) throw new Error("宴会仿真请求失败: " + resp.status);
    return await resp.json();
  }

  global.SynergySimulatorUI = {
    renderSceneSelector,
    renderAlgorithmPanel,
    renderPerLampData,
    renderSynergyAnalysis,
    renderBaselineCompare,
    runBanquetSimulation,
  };
})(typeof window !== "undefined" ? window : this);
