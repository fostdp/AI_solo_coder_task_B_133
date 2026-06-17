/* =========================================================
 * air_quality_panel.js
 * 职责：UI控制面板、事件监听、API调用、数据轮询、DOM更新、告警面板、AQI显示
 * 依赖：window.GongDeng3D（由 gong_deng_3d.js 暴露）
 * ========================================================= */
(function () {
  const API_BASE = window.location.origin;

  let particleCount = 50;
  let fuelType = "animal_fat";
  let airChangeRate = 1.0;
  let outdoorPm25 = 25.0;
  let autoUpdate = true;
  let currentSensorData = null;
  let currentFlueSim = null;
  let currentAirQuality = null;
  let flameIntensity = 0.8;
  let blockageDegree = 0.0;
  let currentLampType = "changxin_gongdeng";

  const GUIDE_KEY = "gongdeng_guide_completed";
  let currentGuideStep = 1;
  const TOTAL_GUIDE_STEPS = 6;

  const LAMP_TYPE_DESC = {
    changxin_gongdeng: "长信宫灯(西汉)：采用宫女跪坐造型，双弯曲烟道结构，内部清水过滤烟尘，烟道可拆卸清洗，被誉为中华第一灯。",
    yanyu_deng: "雁鱼灯(西汉)：鸿雁回首衔鱼造型，雁颈为S型烟道，鱼腹为灯罩，烟尘经雁颈导入雁腹水中，构思巧妙。",
    niu_deng: "错银铜牛灯(东汉)：牛形灯座，双牛角为烟道通向牛腹盛水器，器身饰错银云纹，工艺精湛，净化效率更优。",
  };

  function init() {
    setupEventListeners();
    setupGuideSystem();
    setupTooltips();
    setupSliderFeedback();
    startDataPolling();
    if (typeof window.setFlameIntensity === "function") {
      window.setFlameIntensity(flameIntensity);
    }
    if (typeof window.setBlockageVisual === "function") {
      window.setBlockageVisual(blockageDegree);
    }
  }

  function setupSliderFeedback() {
    updateFlameFeedback(flameIntensity);
    updateBlockageFeedback(blockageDegree);
  }

  function updateFlameFeedback(val) {
    const feedback = document.getElementById("flame-feedback");
    if (!feedback) return;
    if (val >= 0.6 && val <= 0.8) {
      feedback.textContent = "推荐";
      feedback.className = "slider-feedback good";
    } else if (val > 0.8 && val <= 0.9) {
      feedback.textContent = "较亮";
      feedback.className = "slider-feedback warn";
    } else if (val > 0.9) {
      feedback.textContent = "烟雾大";
      feedback.className = "slider-feedback bad";
    } else if (val < 0.6 && val >= 0.3) {
      feedback.textContent = "节能";
      feedback.className = "slider-feedback good";
    } else {
      feedback.textContent = "昏暗";
      feedback.className = "slider-feedback warn";
    }
  }

  function updateBlockageFeedback(val) {
    const feedback = document.getElementById("blockage-feedback");
    if (!feedback) return;
    if (val === 0) {
      feedback.textContent = "通畅";
      feedback.className = "slider-feedback good";
    } else if (val > 0 && val <= 0.3) {
      feedback.textContent = "轻微积灰";
      feedback.className = "slider-feedback good";
    } else if (val > 0.3 && val <= 0.6) {
      feedback.textContent = "需要清洁";
      feedback.className = "slider-feedback warn";
    } else {
      feedback.textContent = "严重堵塞";
      feedback.className = "slider-feedback bad";
    }
  }

  function setupTooltips() {
    const tooltip = document.getElementById("global-tooltip");
    if (!tooltip) return;

    document.querySelectorAll(".info-icon").forEach((el) => {
      el.addEventListener("mouseenter", (e) => {
        const tip = el.getAttribute("data-tip") || "";
        if (!tip) return;
        tooltip.textContent = tip;
        tooltip.classList.add("show");
        const rect = el.getBoundingClientRect();
        tooltip.style.left = (rect.left + rect.width + 10) + "px";
        tooltip.style.top = (rect.top - 5) + "px";
      });
      el.addEventListener("mouseleave", () => {
        tooltip.classList.remove("show");
      });
    });
  }

  function setupGuideSystem() {
    const overlay = document.getElementById("guide-overlay");
    const helpBtn = document.getElementById("help-btn");
    if (!overlay || !helpBtn) return;

    buildGuideProgress();

    const hasCompleted = localStorage.getItem(GUIDE_KEY);
    if (!hasCompleted) {
      setTimeout(() => {
        showGuide(1);
      }, 800);
    }

    helpBtn.addEventListener("click", () => {
      showGuide(1);
    });

    const prevBtn = document.getElementById("guide-prev");
    const nextBtn = document.getElementById("guide-next");
    const closeBtn = document.getElementById("guide-close");

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (currentGuideStep > 1) {
          showGuide(currentGuideStep - 1);
        }
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (currentGuideStep < TOTAL_GUIDE_STEPS) {
          showGuide(currentGuideStep + 1);
        }
      });
    }
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        hideGuide();
        localStorage.setItem(GUIDE_KEY, "1");
      });
    }

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        hideGuide();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (!overlay.classList.contains("active")) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === " ") {
        if (currentGuideStep < TOTAL_GUIDE_STEPS) showGuide(currentGuideStep + 1);
        e.preventDefault();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        if (currentGuideStep > 1) showGuide(currentGuideStep - 1);
        e.preventDefault();
      } else if (e.key === "Escape" || e.key === "Enter") {
        hideGuide();
        localStorage.setItem(GUIDE_KEY, "1");
        e.preventDefault();
      }
    });
  }

  function buildGuideProgress() {
    const progress = document.getElementById("guide-progress");
    if (!progress) return;
    progress.innerHTML = "";
    for (let i = 1; i <= TOTAL_GUIDE_STEPS; i++) {
      const dot = document.createElement("div");
      dot.className = "guide-dot" + (i === 1 ? " active" : "");
      dot.dataset.step = i;
      progress.appendChild(dot);
    }
  }

  function showGuide(step) {
    const overlay = document.getElementById("guide-overlay");
    const steps = document.querySelectorAll(".guide-step");
    const dots = document.querySelectorAll(".guide-dot");
    const prevBtn = document.getElementById("guide-prev");
    const nextBtn = document.getElementById("guide-next");
    const closeBtn = document.getElementById("guide-close");

    if (!overlay) return;

    currentGuideStep = step;
    steps.forEach((s) => s.classList.remove("active"));
    dots.forEach((d) => d.classList.remove("active"));

    const activeStep = document.querySelector(`.guide-step[data-step="${step}"]`);
    const activeDot = document.querySelector(`.guide-dot[data-step="${step}"]`);
    if (activeStep) activeStep.classList.add("active");
    if (activeDot) activeDot.classList.add("active");

    if (prevBtn) prevBtn.disabled = step === 1;
    if (nextBtn) nextBtn.style.display = step === TOTAL_GUIDE_STEPS ? "none" : "inline-block";
    if (closeBtn) closeBtn.style.display = step === TOTAL_GUIDE_STEPS ? "inline-block" : "none";

    overlay.classList.add("active");
  }

  function hideGuide() {
    const overlay = document.getElementById("guide-overlay");
    if (overlay) overlay.classList.remove("active");
  }

  function setupEventListeners() {
    document.querySelectorAll(".view-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const view = tab.dataset.view;
        GongDeng3D.switchView(view);
        const showLegend = view === "pm25" || view === "banquet_pm25";
        const legend = document.getElementById("pm25-legend");
        if (legend) legend.style.display = showLegend ? "block" : "none";
        if (view === "particles") {
          loadParticles();
        } else if (view === "pm25") {
          loadPM25Cloud();
        }
      });
    });

    document.querySelectorAll("#compare-tabs .sub-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#compare-tabs .sub-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const sub = tab.dataset.subtab;
        ["dynasty", "modern", "banquet"].forEach((k) => {
          const panel = document.getElementById("subpanel-" + k);
          if (panel) panel.classList.toggle("hidden", sub !== k);
        });
      });
    });

    const lampTypeSelect = document.getElementById("lamp-type-select");
    if (lampTypeSelect) {
      lampTypeSelect.addEventListener("change", (e) => {
        currentLampType = e.target.value;
        const desc = document.getElementById("lamp-type-desc");
        if (desc && LAMP_TYPE_DESC[currentLampType]) {
          desc.textContent = LAMP_TYPE_DESC[currentLampType];
        }
        if (typeof GongDeng3D.setCurrentLampType === "function") {
          GongDeng3D.setCurrentLampType(currentLampType);
        }
        if (GongDeng3D.getCurrentView() === "particles") loadParticles();
      });
    }

    document.getElementById("fuel-select").addEventListener("change", (e) => {
      fuelType = e.target.value;
      if (GongDeng3D.getCurrentView() === "particles") {
        loadParticles();
      }
    });

    document.getElementById("flame-slider").addEventListener("input", (e) => {
      flameIntensity = parseFloat(e.target.value);
      document.getElementById("flame-val").textContent = flameIntensity.toFixed(2);
      updateFlameFeedback(flameIntensity);
      if (typeof window.setFlameIntensity === "function") {
        window.setFlameIntensity(flameIntensity);
      }
    });

    document.getElementById("blockage-slider").addEventListener("input", (e) => {
      blockageDegree = parseFloat(e.target.value);
      document.getElementById("blockage-val").textContent = blockageDegree.toFixed(2);
      updateBlockageFeedback(blockageDegree);
      if (typeof window.setBlockageVisual === "function") {
        window.setBlockageVisual(blockageDegree);
      }
    });

    document.getElementById("ach-slider").addEventListener("input", (e) => {
      airChangeRate = parseFloat(e.target.value);
      document.getElementById("ach-val").textContent = airChangeRate.toFixed(1);
    });

    document.getElementById("outdoor-pm25-slider").addEventListener("input", (e) => {
      outdoorPm25 = parseFloat(e.target.value);
      document.getElementById("outdoor-pm25-val").textContent = Math.round(outdoorPm25);
    });

    document.getElementById("particles-slider").addEventListener("input", (e) => {
      particleCount = parseInt(e.target.value);
      document.getElementById("particles-val").textContent = particleCount;
      if (GongDeng3D.getCurrentView() === "particles") {
        loadParticles();
      }
    });

    document.getElementById("btn-simulate").addEventListener("click", () => {
      triggerManualSimulation();
    });

    document.getElementById("btn-auto-toggle").addEventListener("click", (e) => {
      autoUpdate = !autoUpdate;
      e.target.textContent = autoUpdate ? "暂停自动" : "启动自动";
    });
  }

  function useMockData() {
    const now = new Date();
    currentSensorData = {
      time: now,
      lamp_id: 1,
      oil_consumption: 1.6,
      flue_temperature: 125,
      flue_velocity: 0.45,
      indoor_pm25: 52,
      oil_level: 420,
      ambient_temperature: 24,
      ambient_humidity: 55,
    };
    currentFlueSim = {
      time: now,
      lamp_id: 1,
      reynolds_number: 850,
      prandtl_number: 0.71,
      nusselt_number: 4.8,
      heat_transfer_coeff: 2.5,
      pressure_drop: 0.8,
      settling_efficiency: 42,
      outlet_temperature: 58,
      outlet_velocity: 0.38,
      flow_regime: "laminar",
    };
    currentAirQuality = {
      time: now,
      lamp_id: 1,
      pm25_diffusion_coeff: 0.00000015,
      pm25_gradient_x: 0.5,
      pm25_gradient_y: 0.4,
      pm25_gradient_z: 0.8,
      purification_rate: 1.2,
      air_change_efficiency: 65,
      aqi_level: "良",
      health_risk: "空气质量可接受",
    };

    updateDashboard({
      sensor: currentSensorData,
      flue_simulation: currentFlueSim,
      air_quality: currentAirQuality,
      alerts: [],
    });
  }

  async function triggerManualSimulation() {
    const oil = 1.5 + flameIntensity * 1.5;
    const blockageFactor = 1 + blockageDegree * 2;
    const temp = 25 + (180 - 25) * flameIntensity * blockageFactor * 0.8;
    const velocity = (0.3 + flameIntensity * 0.4) / blockageFactor;
    const pm25 = 35 + flameIntensity * 20 - velocity * 5 + blockageDegree * 25;

    const payload = {
      lamp_id: 1,
      lamp_type: currentLampType,
      oil_consumption: oil,
      flue_temperature: temp,
      flue_velocity: velocity,
      indoor_pm25: pm25,
      oil_level: 450,
      ambient_temperature: 24,
      ambient_humidity: 55,
      fuel_type: fuelType,
      air_change_rate: airChangeRate,
      outdoor_pm25: outdoorPm25,
    };

    try {
      const res = await fetch("/api/sensor/data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.status === "success") {
        await fetchLatestData();
      }
    } catch (e) {
      console.error("手动仿真失败", e);
    }
  }

  async function fetchLatestData() {
    try {
      const res = await fetch("/api/sensor/data/latest?lamp_id=1");
      if (res.ok) {
        const data = await res.json();
        currentSensorData = data.sensor;
        currentFlueSim = data.flue_simulation;
        currentAirQuality = data.air_quality;
        updateDashboard(data);
        updateStatus(data);

        if (GongDeng3D.getCurrentView() === "particles") loadParticles();
        if (GongDeng3D.getCurrentView() === "pm25") loadPM25Cloud();
      }
    } catch (e) {
      useMockData();
    }

    try {
      const statRes = await fetch("/api/statistics?lamp_id=1&hours=24");
      if (statRes.ok) {
        const stats = await statRes.json();
        updateStatistics(stats);
      }
    } catch (e) {}
  }

  async function loadParticles() {
    const vel = currentSensorData?.flue_velocity || 0.5;
    const temp = currentSensorData?.flue_temperature || 120;

    try {
      const res = await fetch(
        `/api/simulation/particles?flue_velocity=${vel}&flue_temperature=${temp}&num_particles=${particleCount}&fuel_type=${fuelType}`
      );
      const data = await res.json();
      GongDeng3D.updateParticleTrajectories(data.trajectories, data.flue_length, data.flue_diameter);
      const simInfo = document.getElementById("sim-info");
      if (data.fuel_name && simInfo) {
        let fuelDiv = simInfo.querySelector(".fuel-info");
        if (!fuelDiv) {
          fuelDiv = document.createElement("div");
          fuelDiv.className = "fuel-info";
          simInfo.insertBefore(fuelDiv, simInfo.firstChild);
        }
        const fuelSpan = fuelDiv.querySelector("span") || document.createElement("span");
        fuelSpan.textContent = data.fuel_name;
        if (!fuelDiv.querySelector("span")) {
          fuelDiv.textContent = "燃料: ";
          fuelDiv.appendChild(fuelSpan);
        } else {
          fuelDiv.firstChild.textContent = "燃料: ";
        }
      }
    } catch (e) {
      console.warn("加载粒子数据失败，使用模拟数据");
      const mockTrajectories = generateMockTrajectories(particleCount);
      GongDeng3D.updateParticleTrajectories(mockTrajectories, 0.8, 0.05);
    }
  }

  function generateMockTrajectories(count) {
    const trajectories = [];
    for (let i = 0; i < count; i++) {
      const points = [];
      let x = (Math.random() - 0.5) * 0.04;
      let z = (Math.random() - 0.5) * 0.04;
      for (let j = 0; j <= 50; j++) {
        const y = (j / 50) * 0.8;
        x += (Math.random() - 0.5) * 0.002;
        z += (Math.random() - 0.5) * 0.002;
        const r = Math.sqrt(x * x + z * z);
        if (r > 0.025) {
          const scale = 0.025 / r;
          x *= scale;
          z *= scale;
        }
        points.push([x, y, z]);
      }
      trajectories.push({ particle_id: i, points });
    }
    return trajectories;
  }

  async function loadPM25Cloud() {
    try {
      const res = await fetch("/api/simulation/pm25-grid/latest?lamp_id=1");
      const data = await res.json();
      const ROOM_SIZE = GongDeng3D.getROOM_SIZE();
      const nx = 5,
        ny = 5,
        nz = 5;
      const gridData = {
        grid_data: (data.grid_data || []).map((p) => ({
          ...p,
          world_x: (p.grid_x / (nx - 1)) * ROOM_SIZE.x - ROOM_SIZE.x / 2,
          world_y: (p.grid_y / (ny - 1)) * ROOM_SIZE.y - ROOM_SIZE.y / 2,
          world_z: (p.grid_z / (nz - 1)) * ROOM_SIZE.z,
        })),
      };
      GongDeng3D.updatePM25Cloud(gridData);
    } catch (e) {
      console.warn("加载PM2.5云图失败，使用模拟数据");
      GongDeng3D.updatePM25Cloud({ grid_data: generateMockPM25Grid() });
    }
  }

  function generateMockPM25Grid() {
    const data = [];
    const ROOM_SIZE = GongDeng3D.getROOM_SIZE();
    const nx = 5,
      ny = 5,
      nz = 5;
    const basePm25 = currentSensorData?.indoor_pm25 || 50;

    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) {
        for (let k = 0; k < nz; k++) {
          const wx = (i / (nx - 1)) * ROOM_SIZE.x - ROOM_SIZE.x / 2;
          const wy = (j / (ny - 1)) * ROOM_SIZE.y - ROOM_SIZE.y / 2;
          const wz = (k / (nz - 1)) * ROOM_SIZE.z;

          const distToLamp = Math.sqrt(wx * wx + wy * wy + (wz - 1.5) * (wz - 1.5));
          const concentration =
            basePm25 + 30 * Math.exp(-distToLamp / 2) + (Math.random() - 0.5) * 10;

          data.push({
            grid_x: i,
            grid_y: j,
            grid_z: k,
            concentration: Math.max(10, concentration),
            world_x: wx,
            world_y: wy,
            world_z: wz,
          });
        }
      }
    }
    return data;
  }

  function updateDashboard(data) {
    const s = data.sensor;
    if (s) {
      const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      setText("metric-oil", s.oil_consumption?.toFixed(2) || "--");
      setText("metric-oil-level", s.oil_level?.toFixed(0) || "--");
      setText("metric-temp", s.flue_temperature?.toFixed(1) || "--");
      setText("metric-velocity", s.flue_velocity?.toFixed(3) || "--");
      setText("metric-pm25", s.indoor_pm25?.toFixed(1) || "--");
      setText("metric-amb-temp", s.ambient_temperature?.toFixed(1) || "--");

      const pm25Card = document.getElementById("card-pm25");
      if (pm25Card) {
        pm25Card.classList.remove("good", "warning", "danger");
        if (s.indoor_pm25 <= 35) pm25Card.classList.add("good");
        else if (s.indoor_pm25 <= 75) pm25Card.classList.add("warning");
        else pm25Card.classList.add("danger");
      }

      const tempCard = document.getElementById("card-temp");
      if (tempCard) {
        tempCard.classList.remove("warning", "danger");
        if (s.flue_temperature > 200) tempCard.classList.add("danger");
        else if (s.flue_temperature > 150) tempCard.classList.add("warning");
      }

      const velCard = document.getElementById("card-velocity");
      if (velCard) {
        velCard.classList.remove("warning", "danger");
        if (s.flue_velocity < 0.1) velCard.classList.add("danger");
        else if (s.flue_velocity < 0.2) velCard.classList.add("warning");
      }
    }

    const fs = data.flue_simulation;
    if (fs) {
      const regimeMap = { laminar: "层流", transitional: "过渡流", turbulent: "湍流" };
      const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      setText("info-regime", regimeMap[fs.flow_regime] || fs.flow_regime);
      setText("info-re", fs.reynolds_number?.toFixed(0) || "-");
      setText("info-nu", fs.nusselt_number?.toFixed(2) || "-");
      setText("info-settle", fs.settling_efficiency?.toFixed(1) || "-");
    }

    const aq = data.air_quality;
    if (aq) {
      const el = document.getElementById("info-purify");
      if (el) el.textContent = aq.purification_rate?.toFixed(2) || "-";
      updateAQIBadge(aq.aqi_level, aq.health_risk);
    }

    updateAlerts(data.alerts || []);
  }

  function updateAQIBadge(level, risk) {
    const container = document.getElementById("aqi-container");
    if (!container) return;
    const classMap = {
      优: "aqi-good",
      良: "aqi-moderate",
      轻度污染: "aqi-unhealthy-sensitive",
      中度污染: "aqi-unhealthy",
      重度污染: "aqi-very-unhealthy",
      严重污染: "aqi-hazardous",
    };
    const cls = classMap[level] || "aqi-good";
    container.innerHTML = "";
    const badge = document.createElement("div");
    badge.className = `aqi-badge ${cls}`;
    badge.textContent = `AQI: ${level} - ${risk || ""}`;
    container.appendChild(badge);
  }

  function updateStatus(data) {
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");
    if (!dot || !text) return;

    const hasDanger = data.alerts?.some((a) => a.severity === "CRITICAL");
    const hasWarning = data.alerts?.some((a) => a.severity === "WARNING");

    dot.classList.remove("warning", "danger");
    if (hasDanger) {
      dot.classList.add("danger");
      text.textContent = "存在严重告警，请立即处理";
    } else if (hasWarning) {
      dot.classList.add("warning");
      text.textContent = "存在警告信息";
    } else {
      text.textContent = "系统运行正常";
    }
  }

  function updateAlerts(alerts) {
    const list = document.getElementById("alert-list");
    if (!list) return;
    list.innerHTML = "";

    if (!alerts || alerts.length === 0) {
      const empty = document.createElement("div");
      empty.className = "alert-empty";
      empty.textContent = "暂无告警";
      list.appendChild(empty);
      return;
    }

    const typeMap = {
      FLUE_BLOCKAGE: "烟道堵塞",
      PM25_EXCEEDED: "PM2.5超标",
      TEMPERATURE_HIGH: "温度过高",
    };

    alerts.forEach((alert) => {
      const isWarning = alert.severity === "WARNING";
      const item = document.createElement("div");
      item.className = `alert-item ${isWarning ? "warning" : ""}`;

      const typeDiv = document.createElement("div");
      typeDiv.className = "alert-type";
      typeDiv.textContent = `${typeMap[alert.alert_type] || alert.alert_type} [${alert.severity}]`;
      item.appendChild(typeDiv);

      const msgDiv = document.createElement("div");
      msgDiv.textContent = alert.message;
      item.appendChild(msgDiv);

      const timeDiv = document.createElement("div");
      timeDiv.className = "alert-time";
      try {
        timeDiv.textContent = new Date(alert.time).toLocaleString("zh-CN");
      } catch {
        timeDiv.textContent = String(alert.time);
      }
      item.appendChild(timeDiv);

      list.appendChild(item);
    });
  }

  function updateStatistics(stats) {
    const setText = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };
    setText("stat-avg-pm25", stats.avg_pm25?.toFixed(1) || "--");
    setText("stat-max-pm25", stats.max_pm25?.toFixed(1) || "--");
    setText("stat-avg-temp", stats.avg_flue_temperature?.toFixed(1) || "--");
    setText("stat-count", stats.data_points || "--");
  }

  function updateTimeDisplay() {
    const el = document.getElementById("current-time");
    if (el) el.textContent = new Date().toLocaleString("zh-CN");
  }

  function startDataPolling() {
    fetchLatestData();
    setInterval(() => {
      updateTimeDisplay();
      if (autoUpdate) {
        fetchLatestData();
      }
    }, 5000);
  }

  window.AirQualityPanel = {
    init,
    fetchLatestData,
    loadParticles,
    loadPM25Cloud,
    triggerManualSimulation,
    getCurrentSensorData: () => currentSensorData,
    getCurrentFlueSim: () => currentFlueSim,
    getCurrentAirQuality: () => currentAirQuality,
  };
})();
