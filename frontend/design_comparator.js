/*
 * design_comparator.js — 朝代环保灯设计对比组件
 * 职责：
 *   1. 渲染三灯设计参数对比表（含考古来源）
 *   2. 渲染设计洞察卡片
 *   3. 渲染三维并列视图按钮
 * 与后端 DesignComparator 模块对应。
 */
(function (global) {
  "use strict";

  const LAMP_ORDER = ["changxin_gongdeng", "yanyu_deng", "niu_deng"];
  const LAMP_NAMES = {
    changxin_gongdeng: "长信宫灯",
    yanyu_deng: "雁鱼灯",
    niu_deng: "错银铜牛灯",
  };
  const LAMP_COLORS = {
    changxin_gongdeng: "#E0B040",
    yanyu_deng: "#6BAA7B",
    niu_deng: "#B08C5A",
  };

  // ------------------------------------------------------------------
  // 对比表参数行
  // ------------------------------------------------------------------
  const COMPARE_ROWS = [
    { section: "文物考古", key: "dynasty", label: "朝代" },
    { section: "文物考古", key: "height_m", label: "通高(m)", fmt: (v) => v.toFixed(2) },
    { section: "文物考古", key: "weight_kg", label: "重量(kg)", fmt: (v) => v.toFixed(2) },
    { section: "文物考古", key: "material", label: "材质" },
    { section: "文物考古", key: ["archaeological_info", "current_collection"], label: "馆藏单位" },
    { section: "文物考古", key: ["archaeological_info", "cultural_relic_level"], label: "文物等级" },
    { section: "烟道设计", key: ["flue_geometry", "total_length_m"], label: "烟道总长(m)", fmt: (v) => v.toFixed(3) },
    { section: "烟道设计", key: ["flue_geometry", "inner_diameter_m"], label: "烟道内径(m)", fmt: (v) => v.toFixed(3) },
    { section: "烟道设计", key: ["flue_geometry", "bend_count"], label: "弯道数" },
    { section: "烟道设计", key: ["flue_geometry", "water_capacity_l"], label: "水容量(L)", fmt: (v) => v.toFixed(2) },
    { section: "净化特性", key: ["purification_characteristics", "base_purification_efficiency"], label: "基础净化效率", fmt: (v) => (v * 100).toFixed(1) + "%" },
    { section: "净化特性", key: ["purification_characteristics", "flue_sedimentation_ratio"], label: "烟道沉降比", fmt: (v) => (v * 100).toFixed(1) + "%" },
    { section: "净化特性", key: ["purification_characteristics", "water_filter_ratio"], label: "水滤比", fmt: (v) => (v * 100).toFixed(1) + "%" },
    { section: "净化特性", key: ["purification_characteristics", "local_purification_radius_m"], label: "净化半径(m)", fmt: (v) => v.toFixed(1) },
    { section: "评分", key: "design_score", label: "综合设计分", fmt: (v) => v.toFixed(1), cls: "score-cell" },
    { section: "评分", key: "rank", label: "排名", fmt: (v) => "第" + v + "名", cls: "rank-cell" },
  ];

  function getEl(id) { return document.getElementById(id); }

  function deepGet(obj, path) {
    if (!obj) return undefined;
    if (Array.isArray(path)) {
      let cur = obj;
      for (const k of path) {
        if (cur == null) return undefined;
        cur = cur[k];
      }
      return cur;
    }
    return obj[path];
  }

  // ------------------------------------------------------------------
  // 1. 渲染对比表（从 /dynasty-lamps + /dynasty-compare 结果合并）
  // ------------------------------------------------------------------
  function renderDesignCompareTable(lampsList, dynCompareData) {
    const root = getEl("dynasty-compare-table");
    if (!root) return;

    // 建立 lamp_type -> {静态cfg, 仿真结果, 评分} 映射
    const index = {};
    (lampsList || []).forEach((l) => { index[l.lamp_type] = Object.assign({}, l); });
    ((dynCompareData && dynCompareData.comparison) || []).forEach((r) => {
      if (index[r.lamp_type]) Object.assign(index[r.lamp_type], r);
    });

    let lastSection = null;
    let html = '<table class="dynasty-table"><thead><tr><th style="width:22%">参数维度</th>';
    LAMP_ORDER.forEach((t) => {
      html += `<th style="background:${LAMP_COLORS[t]}22; border-left:2px solid ${LAMP_COLORS[t]}">${LAMP_NAMES[t] || t}</th>`;
    });
    html += "</tr></thead><tbody>";

    COMPARE_ROWS.forEach((row) => {
      if (row.section !== lastSection) {
        lastSection = row.section;
        html += `<tr class="section-row"><td colspan="${LAMP_ORDER.length + 1}"><strong>▌ ${row.section}</strong></td></tr>`;
      }
      html += `<tr><td class="label">${row.label}</td>`;
      LAMP_ORDER.forEach((t) => {
        const d = index[t] || {};
        const raw = deepGet(d, row.key);
        let v;
        if (raw === undefined || raw === null || raw === "") {
          v = '<span style="color:#aaa">—</span>';
        } else if (row.fmt) {
          try { v = row.fmt(typeof raw === "string" ? parseFloat(raw) : raw); }
          catch (e) { v = raw; }
        } else {
          v = raw;
        }
        const cls = row.cls ? ` class="${row.cls}"` : "";
        html += `<td${cls}>${v}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 2. 渲染设计洞察
  // ------------------------------------------------------------------
  function renderDesignInsights(insights) {
    const root = getEl("design-insights-panel");
    if (!root) return;
    if (!insights || !insights.length) { root.innerHTML = ""; return; }
    let html = '<div class="insights-panel"><h4>🔍 设计洞察</h4><ul>';
    insights.forEach((ins) => {
      html += `<li>${ins}</li>`;
    });
    html += "</ul></div>";
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 3. 渲染考古来源卡片（从 lamp_type 的 archaeological_info）
  // ------------------------------------------------------------------
  function renderArchaeologyCard(lampCfg) {
    const root = getEl("archaeology-card");
    if (!root || !lampCfg) return;
    const ai = lampCfg.archaeological_info || {};
    const cl = ai.data_confidence_level || {};
    const confidenceBadge = (k) => {
      const v = cl[k] || "C";
      const color = v === "A" ? "#4CAF50" : v === "B" ? "#FF9800" : "#F44336";
      return `<span class="conf-badge" style="background:${color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">${v}</span>`;
    };
    let html = `
      <div class="archaeology-card">
        <h4>📜 考古来源</h4>
        <p><strong>出土地点：</strong>${ai.unearthed_location || "待考"}</p>
        <p><strong>出土年份：</strong>${ai.unearthed_year || "待考"}</p>
        <p><strong>馆藏单位：</strong>${ai.current_collection || "待考"}</p>
        <p><strong>文物等级：</strong>${ai.cultural_relic_level || "待考"}</p>
        <p><strong>考古报告：</strong>${ai.archaeological_reference || "待考"}</p>
        <div style="margin-top:10px">
          <strong>数据可信度：</strong>
          几何${confidenceBadge("flue_geometry")}
          尺寸${confidenceBadge("dimensions")}
          材质${confidenceBadge("material")}
          净化率${confidenceBadge("purification_efficiency")}
        </div>
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 4. 渲染 CFD 对比柱状图（基于 dynasty-compare 的 cfd 结果）
  // ------------------------------------------------------------------
  function renderDynastyCfdBarChart(canvasId, dynCompareData) {
    const canvas = getEl(canvasId);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    if (!dynCompareData || !dynCompareData.comparison) return;

    const METRICS = [
      { key: ["cfd", "settling_efficiency"], label: "沉降效率(×100)", color: "#4CAF50", fmt: (v) => (v * 100).toFixed(1) },
      { key: ["cfd", "outlet_velocity"], label: "出口流速(m/s)", color: "#2196F3", fmt: (v) => v.toFixed(2) },
      { key: ["cfd", "pressure_drop_pa"], label: "阻力(Pa)", color: "#FF9800", fmt: (v) => v.toFixed(1) },
      { key: ["cfd", "outlet_temperature_c"], label: "出口温度(°C)", color: "#E91E63", fmt: (v) => v.toFixed(1) },
      { key: ["air_quality", "purification_rate"], label: "净化率(×100)", color: "#9C27B0", fmt: (v) => (v * 100).toFixed(1) },
    ];

    const data = dynCompareData.comparison;
    const groupW = W / METRICS.length;
    const barW = (groupW - 20) / LAMP_ORDER.length;
    const maxVals = METRICS.map((m) => {
      let mx = 0.0001;
      data.forEach((d) => {
        let v = deepGet(d, m.key);
        if (typeof v === "number") {
          if (m.key[0] === "cfd" && (m.key[1] === "settling_efficiency")) v *= 100;
          if (m.key[1] === "purification_rate") v *= 100;
          mx = Math.max(mx, v);
        }
      });
      return mx * 1.2;
    });
    const baseY = H - 30;
    const topY = 20;

    ctx.font = "10px Microsoft YaHei";
    METRICS.forEach((m, i) => {
      const gx = i * groupW;
      data.forEach((d, di) => {
        const lt = d.lamp_type;
        const li = LAMP_ORDER.indexOf(lt);
        if (li < 0) return;
        let v = deepGet(d, m.key) || 0;
        if (m.key[0] === "cfd" && (m.key[1] === "settling_efficiency")) v *= 100;
        if (m.key[1] === "purification_rate") v *= 100;
        const bh = ((baseY - topY) * v) / maxVals[i];
        const bx = gx + 10 + li * barW;
        const by = baseY - bh;
        ctx.fillStyle = LAMP_COLORS[lt] || "#888";
        ctx.fillRect(bx, by, barW - 3, bh);
        ctx.fillStyle = "#111";
        ctx.textAlign = "center";
        ctx.fillText(m.fmt ? m.fmt(deepGet(d, m.key)) : v, bx + barW / 2, by - 3);
      });
      ctx.fillStyle = "#445577";
      ctx.textAlign = "center";
      ctx.fillText(m.label, gx + groupW / 2, baseY + 16);
    });
  }

  // ------------------------------------------------------------------
  // 5. 触发后端朝代对比
  // ------------------------------------------------------------------
  async function runDynastyCompare(apiBase, params) {
    const url = (apiBase || "/api") + "/comparison/dynasty-compare";
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {
        lamp_types: LAMP_ORDER,
        flue_temperature: 150.0, flue_velocity: 0.4,
        ambient_temperature: 22.0, ambient_humidity: 50.0,
        oil_consumption: 1.5, fuel_type: "animal_fat",
      }),
    });
    if (!resp.ok) throw new Error("朝代对比请求失败: " + resp.status);
    return await resp.json();
  }

  // 暴露公共接口
  global.DesignComparatorUI = {
    LAMP_ORDER, LAMP_NAMES, LAMP_COLORS,
    renderDesignCompareTable,
    renderDesignInsights,
    renderArchaeologyCard,
    renderDynastyCfdBarChart,
    runDynastyCompare,
    deepGet,
  };
})(typeof window !== "undefined" ? window : this);
