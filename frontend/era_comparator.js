/*
 * era_comparator.js — 古代宫灯 vs 现代空气净化器 跨时代对比组件
 * 职责：
 *   1. 7 维度雷达图渲染（净化/覆盖/能耗/噪音/环保/艺术/历史）
 *   2. 关键指标对比柱状图
 *   3. 国家标准引用卡片
 *   4. 跨时代洞察文案渲染
 * 与后端 EraComparator 模块对应。
 */
(function (global) {
  "use strict";

  // 7 个维度 + 显示名
  const RADAR_DIMS = [
    { key: "purification_efficiency", label: "净化效率", higher_is_better: true },
    { key: "coverage_area_m2", label: "覆盖面积", higher_is_better: true },
    { key: "energy_consumption_w", label: "低能耗", higher_is_better: false, invert: true, invert_max: 150 },
    { key: "noise_level_db", label: "低噪音", higher_is_better: false, invert: true, invert_max: 80 },
    { key: "environmental_impact_score", label: "环保友好", higher_is_better: true },
    { key: "aesthetic_value_score", label: "艺术价值", higher_is_better: true },
    { key: "historical_significance_score", label: "历史意义", higher_is_better: true },
  ];
  const SCALE_MAX = 100;
  const SCALE_BENCHMARKS = {
    purification_efficiency: 99.97,    // HEPA H13 效率
    coverage_area_m2: 80.0,             // 大型净化器覆盖
  };

  function getEl(id) { return document.getElementById(id); }

  // 分数归一化到 [0, 100]
  function normalizeScore(dim, raw) {
    if (dim.invert) {
      const max = dim.invert_max || 100;
      return Math.max(0, Math.min(100, (1 - raw / max) * 100));
    }
    const bench = SCALE_BENCHMARKS[dim.key] || 100;
    return Math.max(0, Math.min(100, (raw / bench) * 100));
  }

  // 计算一组 score 的 7 维归一化值
  function toRadarValues(scoreObj) {
    return RADAR_DIMS.map((d) => normalizeScore(d, scoreObj[d.key] || 0));
  }

  // ------------------------------------------------------------------
  // 1. 7 维度雷达图
  // ------------------------------------------------------------------
  function drawRadarChart(canvasId, ancientScores, modernScores, ancientName, modernName) {
    const canvas = getEl(canvasId);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const cx = W / 2;
    const cy = H / 2 + 20;
    const R = Math.min(W, H) / 2 - 70;
    const N = RADAR_DIMS.length;
    if (N < 3) return;

    // 画网格（5 层）
    const levels = 5;
    ctx.strokeStyle = "#3a3a5a";
    ctx.lineWidth = 1;
    for (let lv = 1; lv <= levels; lv++) {
      const r = (R * lv) / levels;
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const a = (Math.PI * 2 * i) / N - Math.PI / 2;
        const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }
    // 网格线
    for (let i = 0; i < N; i++) {
      const a = (Math.PI * 2 * i) / N - Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + R * Math.cos(a), cy + R * Math.sin(a));
      ctx.stroke();
    }

    // 画单组多边形
    function drawPolygon(values, color, fillAlpha) {
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const a = (Math.PI * 2 * i) / N - Math.PI / 2;
        const r = (R * values[i]) / SCALE_MAX;
        const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = color + fillAlpha;
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    const aVals = toRadarValues(ancientScores || {});
    const mVals = toRadarValues(modernScores || {});
    drawPolygon(mVals, "#2196F3", "33");   // 现代：蓝
    drawPolygon(aVals, "#E0B040", "55");   // 古代：金

    // 画顶点
    for (let i = 0; i < N; i++) {
      const a = (Math.PI * 2 * i) / N - Math.PI / 2;
      // 古代顶点
      let r = (R * aVals[i]) / SCALE_MAX;
      ctx.fillStyle = "#E0B040";
      ctx.beginPath();
      ctx.arc(cx + r * Math.cos(a), cy + r * Math.sin(a), 4, 0, Math.PI * 2);
      ctx.fill();
      // 现代顶点
      r = (R * mVals[i]) / SCALE_MAX;
      ctx.fillStyle = "#2196F3";
      ctx.beginPath();
      ctx.arc(cx + r * Math.cos(a), cy + r * Math.sin(a), 4, 0, Math.PI * 2);
      ctx.fill();
      // 标签
      r = R + 22;
      const tx = cx + r * Math.cos(a), ty = cy + r * Math.sin(a);
      ctx.fillStyle = "#e0e6f0";
      ctx.font = "12px Microsoft YaHei";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(RADAR_DIMS[i].label, tx, ty);
    }

    // 标题 + 图例
    ctx.fillStyle = "#f0f3fa";
    ctx.font = "bold 14px Microsoft YaHei";
    ctx.textAlign = "center";
    ctx.fillText("跨时代 7 维度能力雷达图（归一化 0-100）", cx, 18);
    // 图例
    ctx.fillStyle = "#E0B040";
    ctx.fillRect(W - 175, 20, 14, 14);
    ctx.fillStyle = "#f0f3fa";
    ctx.font = "12px Microsoft YaHei";
    ctx.textAlign = "left";
    ctx.fillText(ancientName || "古代宫灯", W - 155, 31);
    ctx.fillStyle = "#2196F3";
    ctx.fillRect(W - 175, 40, 14, 14);
    ctx.fillStyle = "#f0f3fa";
    ctx.fillText(modernName || "现代净化器", W - 155, 51);
  }

  // ------------------------------------------------------------------
  // 2. 关键指标对比柱状图
  // ------------------------------------------------------------------
  function drawEraBarChart(canvasId, ancientScores, modernScores, ancientName, modernName) {
    const canvas = getEl(canvasId);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const BARS = [
      { key: "estimated_cadr_m3h", label: "CADR(m³/h)", bench: 800, color_a: "#E0B040", color_m: "#2196F3", fmt: (v) => v.toFixed(0) },
      { key: "purification_efficiency", label: "净化效率(%)", bench: 100, color_a: "#E0B040", color_m: "#2196F3", fmt: (v) => v.toFixed(1) },
      { key: "coverage_area_m2", label: "覆盖(m²)", bench: 80, color_a: "#E0B040", color_m: "#2196F3", fmt: (v) => v.toFixed(1) },
      { key: "energy_consumption_w", label: "能耗(W)", bench: 150, color_a: "#E0B040", color_m: "#2196F3", fmt: (v) => v.toFixed(1), lower_better: true },
      { key: "noise_level_db", label: "噪音(dB)", bench: 80, color_a: "#E0B040", color_m: "#2196F3", fmt: (v) => v.toFixed(1), lower_better: true },
    ];

    const groupW = W / BARS.length;
    const barW = (groupW - 30) / 2;
    const baseY = H - 35;
    const topY = 40;

    BARS.forEach((m, i) => {
      const gx = i * groupW;
      const a = (ancientScores || {})[m.key] || 0;
      const mv = (modernScores || {})[m.key] || 0;
      // 能耗/噪音是越低越好，仍然画原始高度，用颜色区分
      const aH = ((baseY - topY) * Math.min(a, m.bench)) / m.bench;
      const mH = ((baseY - topY) * Math.min(mv, m.bench)) / m.bench;
      // 古代柱
      ctx.fillStyle = m.color_a;
      ctx.fillRect(gx + 10, baseY - aH, barW, aH);
      ctx.fillStyle = "#f0f3fa";
      ctx.font = "10px Microsoft YaHei";
      ctx.textAlign = "center";
      ctx.fillText(m.fmt(a), gx + 10 + barW / 2, baseY - aH - 4);
      // 现代柱
      ctx.fillStyle = m.color_m;
      ctx.fillRect(gx + 10 + barW + 3, baseY - mH, barW, mH);
      ctx.fillStyle = "#f0f3fa";
      ctx.fillText(m.fmt(mv), gx + 10 + barW + 3 + barW / 2, baseY - mH - 4);
      // X 轴标签
      ctx.fillStyle = "#aab5c9";
      ctx.fillText(m.label, gx + groupW / 2, baseY + 14);
      // 越低越好标记
      if (m.lower_better) {
        ctx.fillStyle = "#FF9800";
        ctx.font = "9px Microsoft YaHei";
        ctx.fillText("↓越好", gx + groupW / 2, baseY + 26);
      }
    });
    // 图例
    ctx.fillStyle = "#E0B040";
    ctx.fillRect(10, 10, 14, 14);
    ctx.fillStyle = "#f0f3fa";
    ctx.font = "11px Microsoft YaHei";
    ctx.textAlign = "left";
    ctx.fillText(ancientName || "古代", 28, 21);
    ctx.fillStyle = "#2196F3";
    ctx.fillRect(95, 10, 14, 14);
    ctx.fillStyle = "#f0f3fa";
    ctx.fillText(modernName || "现代", 113, 21);
  }

  // ------------------------------------------------------------------
  // 3. 国家标准引用卡
  // ------------------------------------------------------------------
  function renderStandardsCard(standardsRef, unifiedCondition) {
    const root = getEl("standards-reference-card");
    if (!root) return;
    let body = "";
    if (standardsRef) {
      for (const [k, v] of Object.entries(standardsRef)) {
        body += `<li><strong>${k}：</strong>${v}</li>`;
      }
    }
    const html = `
      <div class="standards-card">
        <h4>📏 引用标准 & 统一测试条件</h4>
        ${body ? `<ul style="font-size:12px;margin:8px 0;padding-left:20px;line-height:1.7">${body}</ul>` : ""}
        ${unifiedCondition ? `<div style="background:#fff8e1;padding:8px;border-left:3px solid #FF9800;font-size:12px;margin-top:8px">${unifiedCondition}</div>` : ""}
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 4. 跨时代洞察
  // ------------------------------------------------------------------
  function renderEraInsights(summary) {
    const root = getEl("era-insights-panel");
    if (!root || !summary) return;
    const qc = (summary.quantitative_comparison || {});
    function listHtml(title, items, color) {
      let s = `<div style="margin:6px 0"><h5 style="color:${color};margin:4px 0">${title}</h5><ul style="margin:0;padding-left:20px;font-size:12px;line-height:1.7">`;
      (items || []).forEach((i) => { s += `<li>${i}</li>`; });
      s += "</ul></div>";
      return s;
    }
    const html = `
      <div class="era-insights" style="background:#1a1f2e;padding:10px;border-radius:6px">
        <h4 style="margin:0 0 6px 0;color:#E0B040">⚖️ 跨时代洞察</h4>
        <div style="display:flex;gap:8px">
          <div style="flex:1">
            ${listHtml("🏮 古代宫灯优势", summary.ancient_advantages, "#E0B040")}
          </div>
          <div style="flex:1">
            ${listHtml("⚡ 现代净化器优势", summary.modern_advantages, "#2196F3")}
          </div>
        </div>
        <div style="background:#262d44;padding:8px;border-radius:4px;margin-top:6px">
          <strong style="color:#FF9800">📊 定量对比：</strong>
          <span style="font-size:12px;color:#cdd6e8;line-height:1.7">
            CADR 古代约为现代的 ${(qc.cadr_ratio_ancient_vs_modern * 100).toFixed(1)}%，
            噪音差 ${qc.noise_difference_db} dB(A)，
            环保分差 ${qc.eco_score_difference} 分。
          </span>
        </div>
        <div style="margin-top:8px;font-style:italic;color:#99aac5;font-size:12px;border-left:3px solid #9C27B0;padding-left:8px">
          ${summary.cross_era_insight || ""}
        </div>
      </div>`;
    root.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // 5. 触发后端古今对比
  // ------------------------------------------------------------------
  async function runAncientVsModern(apiBase, params) {
    const url = (apiBase || "/api") + "/comparison/ancient-vs-modern";
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {
        lamp_type: "changxin_gongdeng",
        modern_purifier: "basic_hepa_h13",
        room_area_m2: 30.0, room_height_m: 3.0,
        ambient_temperature: 22.0,
      }),
    });
    if (!resp.ok) throw new Error("古今对比请求失败: " + resp.status);
    return await resp.json();
  }

  global.EraComparatorUI = {
    RADAR_DIMS,
    drawRadarChart,
    drawEraBarChart,
    renderStandardsCard,
    renderEraInsights,
    runAncientVsModern,
  };
})(typeof window !== "undefined" ? window : this);
