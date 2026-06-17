(function () {
  const LAMP_NAMES = {
    changxin_gongdeng: "长信宫灯(西汉)",
    yanyu_deng: "雁鱼灯(西汉)",
    niu_deng: "错银铜牛灯(东汉)",
  };
  const LAMP_ORDER = ["changxin_gongdeng", "yanyu_deng", "niu_deng"];

  let lastDynastyCompare = null;
  let lastAncientModernCompare = null;
  let lastBanquetResult = null;

  function getEl(id) { return document.getElementById(id); }

  function buildDynastyCompareTable(data) {
    const root = getEl("dynasty-compare-table");
    if (!root) return;
    const rows = [
      { key: "dynasty", label: "朝代" },
      { key: "lamp_type", label: "灯具类型" },
      { key: "flue_length_m", label: "烟道长度(m)", fmt: (v) => v.toFixed(2) },
      { key: "flue_diameter_m", label: "烟道内径(m)", fmt: (v) => v.toFixed(3) },
      { key: "bend_count", label: "弯道数" },
      { key: "bend_angle_deg", label: "弯道角度(°)", fmt: (v) => v.toFixed(0) },
      { key: "height_m", label: "通高(m)", fmt: (v) => v.toFixed(2) },
      { key: "material", label: "材质" },
      { key: "base_purification_efficiency", label: "基础净化效率", fmt: (v) => (v * 100).toFixed(1) + "%" },
      { key: "flue_velocity_m_s", label: "烟道流速(m/s)", fmt: (v) => v.toFixed(3) },
      { key: "pressure_drop_pa", label: "沿程阻力(Pa)", fmt: (v) => v.toFixed(1) },
      { key: "particulate_settling_efficiency", label: "烟尘沉降效率", fmt: (v) => (v * 100).toFixed(1) + "%" },
      { key: "purification_efficiency", label: "综合净化效率", fmt: (v) => (v * 100).toFixed(1) + "%" },
      { key: "heat_dissipation_w", label: "散热功率(W)", fmt: (v) => v.toFixed(1) },
      { key: "exit_temperature_c", label: "出口温度(°C)", fmt: (v) => v.toFixed(1) },
    ];

    let html = '<table class="dynasty-table"><thead><tr><th>参数</th>';
    LAMP_ORDER.forEach((t) => { html += `<th>${LAMP_NAMES[t] || t}</th>`; });
    html += "</tr></thead><tbody>";
    rows.forEach((row) => {
      html += `<tr><td class="label">${row.label}</td>`;
      LAMP_ORDER.forEach((t) => {
        const d = (data && data[t]) || {};
        const raw = d[row.key];
        const v = raw === undefined || raw === null ? "—" : (row.fmt ? row.fmt(raw) : raw);
        html += `<td>${v}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    root.innerHTML = html;
  }

  function drawRadarChart(canvasId, title, labels, series) {
    const canvas = getEl(canvasId);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const cx = W / 2;
    const cy = H / 2 + 10;
    const R = Math.min(W, H) / 2 - 55;
    const N = labels.length;
    if (N < 3) return;

    const levels = 5;
    ctx.strokeStyle = "#3a3a5a";
    ctx.lineWidth = 1;
    ctx.font = "11px Microsoft YaHei";
    ctx.fillStyle = "#8899bb";
    for (let lv = 1; lv <= levels; lv++) {
      const r = (R * lv) / levels;
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const a = (Math.PI * 2 * i) / N - Math.PI / 2;
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }

    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const a = (Math.PI * 2 * i) / N - Math.PI / 2;
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + R * Math.cos(a), cy + R * Math.sin(a));
    }
    ctx.stroke();

    ctx.fillStyle = "#e8c87a";
    ctx.font = "bold 12px Microsoft YaHei";
    ctx.textAlign = "center";
    for (let i = 0; i < N; i++) {
      const a = (Math.PI * 2 * i) / N - Math.PI / 2;
      const lx = cx + (R + 20) * Math.cos(a);
      const ly = cy + (R + 20) * Math.sin(a);
      ctx.fillText(labels[i], lx, ly);
    }

    const colors = ["#e8c87a", "#4dc3ff", "#a8d08d", "#ff8c42"];
    series.forEach((s, idx) => {
      ctx.beginPath();
      ctx.strokeStyle = colors[idx % colors.length];
      ctx.lineWidth = 2;
      ctx.fillStyle = colors[idx % colors.length] + "33";
      for (let i = 0; i < N; i++) {
        const a = (Math.PI * 2 * i) / N - Math.PI / 2;
        const val = Math.max(0, Math.min(1, s.values[i] / 100));
        const x = cx + R * val * Math.cos(a);
        const y = cy + R * val * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    });

    ctx.fillStyle = "#e8c87a";
    ctx.font = "bold 14px Microsoft YaHei";
    ctx.textAlign = "center";
    ctx.fillText(title, cx, 20);

    const legendY = H - 22;
    ctx.textAlign = "left";
    ctx.font = "11px Microsoft YaHei";
    series.forEach((s, idx) => {
      const lx = 10 + idx * (W / series.length);
      ctx.fillStyle = colors[idx % colors.length];
      ctx.fillRect(lx, legendY, 10, 10);
      ctx.fillStyle = "#cccccc";
      ctx.fillText(s.name, lx + 14, legendY + 10);
    });
  }

  function drawBarChart(canvasId, title, labels, series) {
    const canvas = getEl(canvasId);
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    ctx.fillStyle = "#e8c87a";
    ctx.font = "bold 13px Microsoft YaHei";
    ctx.textAlign = "center";
    ctx.fillText(title, W / 2, 18);

    const left = 55;
    const right = 20;
    const top = 35;
    const bottom = 55;
    const chartW = W - left - right;
    const chartH = H - top - bottom;

    const nSeries = series.length;
    const nLabels = labels.length;
    let maxVal = 10;
    for (let i = 0; i < nSeries; i++) {
      for (let j = 0; j < nLabels; j++) {
        if (series[i].values[j] > maxVal) maxVal = series[i].values[j];
      }
    }
    const niceMax = Math.ceil(maxVal * 1.1);

    ctx.strokeStyle = "#3a3a5a";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#8899bb";
    ctx.font = "10px Microsoft YaHei";
    const ticks = 5;
    for (let t = 0; t <= ticks; t++) {
      const y = top + (chartH * (ticks - t)) / ticks;
      const v = (niceMax * t) / ticks;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(left + chartW, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(1), left - 5, y + 3);
    }

    const groupW = chartW / nLabels;
    const barW = Math.min(18, (groupW - 20) / nSeries);
    const colors = ["#e8c87a", "#4dc3ff", "#a8d08d", "#ff8c42"];

    for (let j = 0; j < nLabels; j++) {
      const gx = left + groupW * j + groupW / 2;
      for (let i = 0; i < nSeries; i++) {
        const v = series[i].values[j];
        const h = (chartH * v) / niceMax;
        const bx = gx - (nSeries * barW) / 2 + i * barW + 2;
        const by = top + chartH - h;
        ctx.fillStyle = colors[i % colors.length];
        ctx.fillRect(bx, by, barW - 4, h);
        ctx.strokeStyle = colors[i % colors.length] + "99";
        ctx.strokeRect(bx, by, barW - 4, h);
      }
      ctx.fillStyle = "#cccccc";
      ctx.font = "11px Microsoft YaHei";
      ctx.textAlign = "center";
      ctx.fillText(labels[j], gx, top + chartH + 15);
    }

    ctx.font = "11px Microsoft YaHei";
    ctx.textAlign = "left";
    const legendY = top + chartH + 30;
    series.forEach((s, idx) => {
      const lx = 10 + idx * (W / nSeries);
      ctx.fillStyle = colors[idx % colors.length];
      ctx.fillRect(lx, legendY, 10, 10);
      ctx.fillStyle = "#cccccc";
      ctx.fillText(s.name, lx + 14, legendY + 10);
    });
  }

  function renderAncientModernCompare(data) {
    lastAncientModernCompare = data;
    if (!data) return;
    const dimensions = data.dimensions || [];
    const labels = dimensions.map((d) => d.label);
    const series = [
      { name: "古代环保灯(综合)", values: dimensions.map((d) => (d.ancient_score || 0) * 100) },
      { name: "现代HEPA净化器", values: dimensions.map((d) => (d.modern_score || 0) * 100) },
    ];
    drawRadarChart("ancient-modern-radar", "古今空气净化 跨时代综合对比", labels, series);

    const effLabels = ["净化效率", "CADR(m³/h)", "覆盖面积(m²)", "功率(W)", "噪音(dB)"];
    const effSeries = [
      { name: "长信宫灯", values: [
        (data.ancient && data.ancient.purification_efficiency || 0) * 100,
        data.ancient && data.ancient.cadr_m3h || 0,
        data.ancient && data.ancient.coverage_m2 || 0,
        data.ancient && data.ancient.power_w || 0,
        data.ancient && data.ancient.noise_db || 0,
      ]},
      { name: "现代HEPA(H13)", values: [
        (data.modern && data.modern.purification_efficiency || 0) * 100,
        data.modern && data.modern.cadr_m3h || 0,
        data.modern && data.modern.coverage_m2 || 0,
        data.modern && data.modern.power_w || 0,
        data.modern && data.modern.noise_db || 0,
      ]},
    ];
    drawBarChart("ancient-modern-bars", "关键性能指标对比", effLabels, effSeries);

    const summary = getEl("ancient-modern-summary");
    if (summary && data.conclusion) {
      summary.innerHTML = `<h4>对比结论</h4><p class="compare-note">${data.conclusion}</p>`;
    }
  }

  function renderBanquetResult(data) {
    lastBanquetResult = data;
    const info = getEl("banquet-info");
    if (info && data) {
      const stats = data.statistics || {};
      const lamps = (data.lamp_positions || []).length;
      info.innerHTML = `
        <div class="row"><span class="label">场景:</span><span>${data.scene_name || ""}</span></div>
        <div class="row"><span class="label">灯数:</span><span>${lamps}</span></div>
        <div class="row"><span class="label">房间体积:</span><span>${(data.room_volume_m3 || 0).toFixed(0)} m³</span></div>
        <div class="row"><span class="label">仿真步数:</span><span>${data.simulated_steps || 0}</span></div>
        <div class="row"><span class="label">时间窗:</span><span>${(data.time_window_seconds || 0).toFixed(0)}s</span></div>
        <div class="row"><span class="label">平均浓度:</span><span>${(stats.avg_pm25 || 0).toFixed(2)} µg/m³</span></div>
        <div class="row"><span class="label">最大浓度:</span><span>${(stats.max_pm25 || 0).toFixed(2)} µg/m³</span></div>
        <div class="row"><span class="label">浓度标准差:</span><span>${(stats.std_pm25 || 0).toFixed(2)}</span></div>
        <div class="row"><span class="label">达标率(≤35):</span><span>${((stats.under_35_ratio || 0) * 100).toFixed(1)}%</span></div>
      `;
    }
  }

  function attachButtons() {
    const btnRunDynasty = getEl("btn-run-dynasty-compare");
    if (btnRunDynasty) {
      btnRunDynasty.addEventListener("click", async function () {
        btnRunDynasty.disabled = true;
        btnRunDynasty.textContent = "运行中...";
        try {
          const payload = {
            airflow_rate_m3_s: parseFloat(getEl("in-airflow")?.value || "0.012"),
            inlet_temperature_c: parseFloat(getEl("in-temp")?.value || "800.0"),
            inlet_pressure_pa: parseFloat(getEl("in-pressure")?.value || "101325"),
            inlet_pm25_mg_m3: parseFloat(getEl("in-pm25")?.value || "12.0"),
            ambient_temperature_c: parseFloat(getEl("in-ambient")?.value || "25.0"),
            duration_seconds: 60.0,
          };
          const res = await fetch("/api/comparison/dynasty-compare", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          lastDynastyCompare = data;
          buildDynastyCompareTable(data);
          if (window.switchView) window.switchView("dynasty_compare");
        } catch (e) {
          console.error("dynasty compare error", e);
        } finally {
          btnRunDynasty.disabled = false;
          btnRunDynasty.textContent = "运行朝代对比";
        }
      });
    }

    const btnRunAncient = getEl("btn-run-ancient-modern");
    if (btnRunAncient) {
      btnRunAncient.addEventListener("click", async function () {
        btnRunAncient.disabled = true;
        btnRunAncient.textContent = "对比中...";
        try {
          const payload = {
            ancient_lamp_type: getEl("in-ancient-lamp")?.value || "changxin_gongdeng",
            modern_purifier_model: getEl("in-modern-model")?.value || "basic_hepa_h13",
            room_volume_m3: parseFloat(getEl("in-room-vol")?.value || "60"),
            runtime_hours: parseFloat(getEl("in-runtime")?.value || "4"),
          };
          const res = await fetch("/api/comparison/ancient-vs-modern", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          renderAncientModernCompare(data);
        } catch (e) {
          console.error("ancient vs modern error", e);
        } finally {
          btnRunAncient.disabled = false;
          btnRunAncient.textContent = "运行跨时代对比";
        }
      });
    }

    const btnLoadScenes = getEl("btn-load-banquet-scenes");
    if (btnLoadScenes) {
      btnLoadScenes.addEventListener("click", async function () {
        try {
          const res = await fetch("/api/comparison/banquet-scenes");
          const data = await res.json();
          const sel = getEl("in-banquet-scene");
          if (sel && data.scenes) {
            sel.innerHTML = "";
            data.scenes.forEach((s) => {
              const opt = document.createElement("option");
              opt.value = s.scene_id;
              opt.textContent = `${s.scene_name} (${s.lamp_count}盏灯, ${s.room_size_m})`;
              sel.appendChild(opt);
            });
          }
        } catch (e) { console.error(e); }
      });
    }

    const btnRunBanquet = getEl("btn-run-banquet");
    if (btnRunBanquet) {
      btnRunBanquet.addEventListener("click", async function () {
        btnRunBanquet.disabled = true;
        btnRunBanquet.textContent = "仿真中...";
        try {
          const sceneId = getEl("in-banquet-scene")?.value || "royal_banquet";
          const payload = {
            scene_id: sceneId,
            base_pm25_ug_m3: parseFloat(getEl("in-banquet-base")?.value || "50.0"),
            time_window_seconds: parseFloat(getEl("in-banquet-window")?.value || "1800"),
          };
          const res = await fetch("/api/comparison/banquet-simulation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          renderBanquetResult(data);

          if (window.showBanquetScene && data.scene_config) {
            window.showBanquetScene(data.scene_config);
          }
          if (window.switchView) window.switchView("banquet");
          setTimeout(() => {
            if (window.updateBanquetPM25Cloud && data.grid_data) {
              window.updateBanquetPM25Cloud(data.grid_data, data.scene_config && data.scene_config.room_geometry);
              if (window.switchView) window.switchView("banquet_pm25");
            }
          }, 1500);
        } catch (e) {
          console.error("banquet error", e);
        } finally {
          btnRunBanquet.disabled = false;
          btnRunBanquet.textContent = "运行宴会协同仿真";
        }
      });
    }
  }

  window.ComparisonUI = {
    buildDynastyCompareTable,
    renderAncientModernCompare,
    renderBanquetResult,
    drawRadarChart,
    drawBarChart,
    init: attachButtons,
    getLastDynastyCompare: () => lastDynastyCompare,
    getLastAncientModernCompare: () => lastAncientModernCompare,
    getLastBanquetResult: () => lastBanquetResult,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachButtons);
  } else {
    attachButtons();
  }
})();
