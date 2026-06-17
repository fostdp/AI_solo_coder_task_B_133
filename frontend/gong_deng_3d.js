/* =========================================================
 * gong_deng_3d.js
 * 职责：Three.js 3D 场景、宫灯建模、烟气流线粒子、PM2.5云图、视图切换
 * 暴露：window.GongDeng3D 全局对象，供 air_quality_panel.js 调用
 * ========================================================= */
(function () {
  const ROOM_SIZE = { x: 10, y: 8, z: 3 };

  let scene, camera, renderer, controls;
  let lampGroup, particleSystem, pm25CloudGroup;
  let multiLampGroup, dynastyCompareGroup, banquetRoomGroup;
  let currentView = "lamp";
  let clock;
  const DYNASTY_LAMP_COLORS = {
    changxin_gongdeng: { body: 0xd4a855, accent: 0xffd700, shade: 0xcc2222, base: 0x8b4513 },
    yanyu_deng: { body: 0x7c9a3e, accent: 0xc9b36b, shade: 0xe8d27a, base: 0x3a5a2a },
    niu_deng: { body: 0x6b5b3d, accent: 0xe0d8c0, shade: 0xb8860b, base: 0x4a3a2a },
  };

  function init() {
    const canvas = document.getElementById("three-canvas");

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a1a);
    scene.fog = new THREE.Fog(0x0a0a1a, 15, 40);

    camera = new THREE.PerspectiveCamera(
      50,
      (window.innerWidth - 380) / window.innerHeight,
      0.1,
      1000
    );
    camera.position.set(6, 4, 8);

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(window.innerWidth - 380, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.target.set(0, 1.5, 0);
    controls.minDistance = 2;
    controls.maxDistance = 30;

    clock = new THREE.Clock();

    setupLights();
    createRoom();
    createGongdengModel();
    createParticleSystem();
    createPM25Cloud();
    switchView("lamp");

    window.addEventListener("resize", onWindowResize);
    animate();
    document.getElementById("loading-overlay").style.display = "none";
  }

  function setupLights() {
    const ambientLight = new THREE.AmbientLight(0x404050, 0.5);
    scene.add(ambientLight);

    const mainLight = new THREE.DirectionalLight(0xffffff, 0.8);
    mainLight.position.set(5, 10, 7);
    mainLight.castShadow = true;
    mainLight.shadow.mapSize.width = 2048;
    mainLight.shadow.mapSize.height = 2048;
    mainLight.shadow.camera.near = 0.5;
    mainLight.shadow.camera.far = 50;
    mainLight.shadow.camera.left = -15;
    mainLight.shadow.camera.right = 15;
    mainLight.shadow.camera.top = 15;
    mainLight.shadow.camera.bottom = -15;
    scene.add(mainLight);

    const fillLight = new THREE.DirectionalLight(0x6688ff, 0.3);
    fillLight.position.set(-5, 5, -5);
    scene.add(fillLight);
  }

  function createRoom() {
    const roomGroup = new THREE.Group();

    const floorGeo = new THREE.PlaneGeometry(ROOM_SIZE.x, ROOM_SIZE.y);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x2a2520,
      roughness: 0.9,
      metalness: 0.1,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    roomGroup.add(floor);

    const gridHelper = new THREE.GridHelper(
      Math.max(ROOM_SIZE.x, ROOM_SIZE.y),
      20,
      0x443322,
      0x221100
    );
    gridHelper.position.y = 0.01;
    roomGroup.add(gridHelper);

    const wallMat = new THREE.MeshStandardMaterial({
      color: 0x332a20,
      roughness: 0.95,
      metalness: 0,
      side: THREE.BackSide,
    });

    const backWallGeo = new THREE.PlaneGeometry(ROOM_SIZE.x, ROOM_SIZE.z);
    const backWall = new THREE.Mesh(backWallGeo, wallMat);
    backWall.position.set(0, ROOM_SIZE.z / 2, -ROOM_SIZE.y / 2);
    roomGroup.add(backWall);

    const leftWallGeo = new THREE.PlaneGeometry(ROOM_SIZE.y, ROOM_SIZE.z);
    const leftWall = new THREE.Mesh(leftWallGeo, wallMat);
    leftWall.rotation.y = Math.PI / 2;
    leftWall.position.set(-ROOM_SIZE.x / 2, ROOM_SIZE.z / 2, 0);
    roomGroup.add(leftWall);

    const rightWall = new THREE.Mesh(leftWallGeo, wallMat);
    rightWall.rotation.y = -Math.PI / 2;
    rightWall.position.set(ROOM_SIZE.x / 2, ROOM_SIZE.z / 2, 0);
    roomGroup.add(rightWall);

    scene.add(roomGroup);
  }

  function createGongdengModel() {
    lampGroup = new THREE.Group();

    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.25, 0.15, 32),
      new THREE.MeshStandardMaterial({ color: 0x3a2f1e, metalness: 0.8, roughness: 0.3 })
    );
    base.position.y = 0.075;
    base.castShadow = true;
    lampGroup.add(base);

    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.08, 0.5, 24),
      new THREE.MeshStandardMaterial({ color: 0x8b6914, metalness: 0.9, roughness: 0.2 })
    );
    stem.position.y = 0.4;
    stem.castShadow = true;
    lampGroup.add(stem);

    const body = new THREE.Mesh(
      new THREE.CylinderGeometry(0.25, 0.35, 0.6, 32),
      new THREE.MeshStandardMaterial({ color: 0x7a5c1a, metalness: 0.85, roughness: 0.25 })
    );
    body.position.y = 0.95;
    body.castShadow = true;
    lampGroup.add(body);

    for (let i = 0; i < 6; i++) {
      const angle = (i / 6) * Math.PI * 2;
      const ring = new THREE.Mesh(
        new THREE.SphereGeometry(0.025, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xffc24e, metalness: 0.95, roughness: 0.1 })
      );
      ring.position.set(Math.cos(angle) * 0.38, 0.95, Math.sin(angle) * 0.38);
      lampGroup.add(ring);
    }

    const topRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.35, 0.03, 16, 64),
      new THREE.MeshStandardMaterial({ color: 0xffd700, metalness: 0.95, roughness: 0.1 })
    );
    topRing.position.y = 1.25;
    lampGroup.add(topRing);

    const bottomRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.35 * 0.7, 0.025, 16, 64),
      new THREE.MeshStandardMaterial({ color: 0xffd700, metalness: 0.95, roughness: 0.1 })
    );
    bottomRing.position.y = 0.65;
    bottomRing.rotation.x = Math.PI / 2;
    lampGroup.add(bottomRing);

    const shade = new THREE.Mesh(
      new THREE.CylinderGeometry(0.35, 0.5, 0.5, 32, 1, true),
      new THREE.MeshStandardMaterial({
        color: 0x8b0000,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.7,
        metalness: 0.3,
        roughness: 0.6,
      })
    );
    shade.position.y = 1.7;
    lampGroup.add(shade);

    const top = new THREE.Mesh(
      new THREE.CylinderGeometry(0.15, 0.5, 0.3, 32),
      new THREE.MeshStandardMaterial({ color: 0xffc24e, metalness: 0.9, roughness: 0.15 })
    );
    top.position.y = 2.1;
    lampGroup.add(top);

    const flue = new THREE.Mesh(
      new THREE.CylinderGeometry(0.025, 0.025, 0.8, 24),
      new THREE.MeshStandardMaterial({ color: 0x2a1a1a, metalness: 0.7, roughness: 0.4 })
    );
    flue.position.y = 2.65;
    lampGroup.add(flue);

    const flueTop = new THREE.Mesh(
      new THREE.CylinderGeometry(0.02, 0.04, 0.1, 24),
      new THREE.MeshStandardMaterial({ color: 0xffc24e, metalness: 0.9, roughness: 0.15 })
    );
    flueTop.position.y = 3.1;
    lampGroup.add(flueTop);

    const handle = new THREE.Mesh(
      new THREE.TorusGeometry(0.3, 0.025, 16, 64, Math.PI),
      new THREE.MeshStandardMaterial({ color: 0xffc24e, metalness: 0.9, roughness: 0.15 })
    );
    handle.position.y = 2.4;
    handle.rotation.z = Math.PI;
    handle.rotation.y = Math.PI / 2;
    lampGroup.add(handle);

    const flameGroup = new THREE.Group();
    flameGroup.position.y = 1.1;

    const flameLight = new THREE.PointLight(0xff8833, 1.5, 5, 2);
    flameLight.position.y = 0.2;
    flameGroup.add(flameLight);

    const flame = new THREE.Mesh(
      new THREE.ConeGeometry(0.1, 0.25, 16),
      new THREE.MeshBasicMaterial({ color: 0xff6600, transparent: true, opacity: 0.9 })
    );
    flame.position.y = 0.15;
    flameGroup.add(flame);

    const innerFlame = new THREE.Mesh(
      new THREE.ConeGeometry(0.05, 0.15, 16),
      new THREE.MeshBasicMaterial({ color: 0xffff66 })
    );
    innerFlame.position.y = 0.1;
    flameGroup.add(innerFlame);

    const smokeParticles = [];
    for (let i = 0; i < 30; i++) {
      const smoke = new THREE.Mesh(
        new THREE.SphereGeometry(0.02, 8, 8),
        new THREE.MeshBasicMaterial({ color: 0x888888, transparent: true, opacity: 0.3 })
      );
      smoke.userData = { offset: Math.random() * Math.PI * 2, speed: 0.5 + Math.random() * 0.5 };
      smokeParticles.push(smoke);
      flameGroup.add(smoke);
    }
    flameGroup.userData.smokeParticles = smokeParticles;

    lampGroup.add(flameGroup);
    lampGroup.userData = { flameGroup, flameLight };

    lampGroup.position.set(0, 0, 0);
    scene.add(lampGroup);
  }

  function animateFlame(time) {
    if (!lampGroup || !lampGroup.userData.flameGroup) return;
    const { flameGroup, flameLight } = lampGroup.userData;
    const t = time;
    const flicker = 0.8 + 0.2 * Math.sin(t * 8) + 0.1 * Math.sin(t * 17);
    if (flameLight) flameLight.intensity = 1.2 * flicker;
    if (flameGroup.children[1]) flameGroup.children[1].scale.y = 0.8 + 0.4 * flicker;
    if (flameGroup.children[2]) flameGroup.children[2].scale.y = 0.85 + 0.3 * flicker;

    const smoke = flameGroup.userData.smokeParticles || [];
    smoke.forEach((p) => {
      const d = (t * p.userData.speed + p.userData.offset) % 2;
      p.position.y = d * 0.5;
      p.material.opacity = Math.max(0, 0.3 * (1 - d / 2));
      p.scale.setScalar(1 + d * 1.5);
    });
  }

  function createParticleSystem() {
    particleSystem = new THREE.Group();
    particleSystem.frustumCulled = false;
    particleSystem.userData = {
      trajectoryLines: [],
      flowParticles: [],
      flueWorldOffset: new THREE.Vector3(0, 1.65, 0),
    };
    scene.add(particleSystem);
  }

  function updateParticleTrajectories(trajectories, flueLength, flueDiameter) {
    clearParticleSystem();

    const lampWorldPos = new THREE.Vector3();
    lampGroup.getWorldPosition(lampWorldPos);
    const flueWorldOffset = particleSystem.userData.flueWorldOffset;
    const flueWorldBase = lampWorldPos.clone().add(flueWorldOffset);

    const flueHelper = new THREE.Mesh(
      new THREE.CylinderGeometry(flueDiameter / 2, flueDiameter / 2, flueLength, 16, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x4488ff, wireframe: true, transparent: true, opacity: 0.2 })
    );
    flueHelper.position.copy(flueWorldBase).add(new THREE.Vector3(0, flueLength / 2, 0));
    particleSystem.add(flueHelper);

    const inletMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0x00ff88 })
    );
    inletMarker.position.copy(flueWorldBase);
    particleSystem.add(inletMarker);

    const outletMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0xff66aa })
    );
    outletMarker.position.copy(flueWorldBase).add(new THREE.Vector3(0, flueLength, 0));
    particleSystem.add(outletMarker);

    trajectories.forEach((traj, ti) => {
      const worldPoints = traj.points.map((p) => {
        const localPoint = new THREE.Vector3(p[0], p[1], p[2]);
        return localPoint.add(flueWorldBase);
      });

      const hue = 0.5 + (ti / trajectories.length) * 0.3;
      const color = new THREE.Color().setHSL(hue, 0.8, 0.5);
      const lineGeo = new THREE.BufferGeometry().setFromPoints(worldPoints);
      const lineMat = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity: 0.5,
        depthWrite: false,
      });
      const line = new THREE.Line(lineGeo, lineMat);
      line.frustumCulled = false;
      particleSystem.add(line);
      particleSystem.userData.trajectoryLines.push(line);

      const particleColors = [color, new THREE.Color(0xffffff), new THREE.Color(0xffcc00)];
      for (let pi = 0; pi < 3; pi++) {
        const particle = new THREE.Mesh(
          new THREE.SphereGeometry(0.008, 6, 6),
          new THREE.MeshBasicMaterial({ color: particleColors[pi], transparent: true, opacity: 0.9, depthWrite: false })
        );
        particle.userData = {
          trajectory: worldPoints,
          progress: pi * 0.3,
          speed: 0.003 + pi * 0.001,
        };
        particle.frustumCulled = false;
        particleSystem.add(particle);
        particleSystem.userData.flowParticles.push(particle);
      }
    });
  }

  function clearParticleSystem() {
    if (!particleSystem) return;
    [...particleSystem.userData.trajectoryLines, ...particleSystem.userData.flowParticles].forEach(
      (obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) obj.material.dispose();
        particleSystem.remove(obj);
      }
    );
    while (particleSystem.children.length > 0) {
      const c = particleSystem.children[0];
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
      particleSystem.remove(c);
    }
    particleSystem.userData.trajectoryLines = [];
    particleSystem.userData.flowParticles = [];
  }

  function animateParticles() {
    if (!particleSystem || !particleSystem.userData.flowParticles) return;
    particleSystem.userData.flowParticles.forEach((p) => {
      const { trajectory, speed } = p.userData;
      if (!trajectory || trajectory.length < 2) return;
      p.userData.progress += speed;
      if (p.userData.progress >= 1) p.userData.progress = 0;
      const totalLen = trajectory.length - 1;
      const pos = p.userData.progress * totalLen;
      const i = Math.floor(pos);
      const t = pos - i;
      const p1 = trajectory[i];
      const p2 = trajectory[Math.min(i + 1, totalLen)];
      p.position.lerpVectors(p1, p2, t);
    });
  }

  function createPM25Cloud() {
    pm25CloudGroup = new THREE.Group();
    scene.add(pm25CloudGroup);
  }

  function clearPM25Cloud() {
    if (!pm25CloudGroup) return;
    while (pm25CloudGroup.children.length > 0) {
      const c = pm25CloudGroup.children[0];
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
      pm25CloudGroup.remove(c);
    }
  }

  function updatePM25Cloud(gridData) {
    clearPM25Cloud();
    if (!gridData || !gridData.grid_data) return;
    const N = Math.round(Math.pow(gridData.grid_data.length, 1 / 3));
    if (N < 2) return;

    gridData.grid_data.forEach((p) => {
      const wx = (p.grid_x / (N - 1)) * ROOM_SIZE.x - ROOM_SIZE.x / 2;
      const wy = (p.grid_y / (N - 1)) * ROOM_SIZE.y - ROOM_SIZE.y / 2;
      const wz = (p.grid_z / (N - 1)) * ROOM_SIZE.z;
      const conc = p.concentration;
      const color = getPM25Color(conc);
      const opacity = Math.min(0.7, 0.15 + conc / 200);
      const size = Math.max(0.05, 0.2 + conc / 400);

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(size, 8, 8),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity })
      );
      mesh.position.set(wx, wy, wz);
      pm25CloudGroup.add(mesh);
    });

    const lampMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.15, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xffaa00, transparent: true, opacity: 0.8 })
    );
    lampMarker.position.copy(lampGroup.position).add(new THREE.Vector3(0, 1.0, 0));
    pm25CloudGroup.add(lampMarker);
  }

  function getPM25Color(concentration) {
    if (concentration <= 35) return new THREE.Color(0x00e400);
    if (concentration <= 75) return new THREE.Color(0xffff00);
    if (concentration <= 115) return new THREE.Color(0xff7e00);
    if (concentration <= 150) return new THREE.Color(0xff0000);
    if (concentration <= 250) return new THREE.Color(0x8f3f97);
    return new THREE.Color(0x7e0023);
  }

  // ------------------------------------------------------------------
  // Feature: 朝代灯3D模型 - 通用化的 createAnyLamp 工厂
  // ------------------------------------------------------------------
  function createAnyLampModel(lampType) {
    const colors = DYNASTY_LAMP_COLORS[lampType] || DYNASTY_LAMP_COLORS.changxin_gongdeng;
    const g = new THREE.Group();

    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.2, 0.25, 0.15, 32),
      new THREE.MeshStandardMaterial({ color: colors.base, metalness: 0.8, roughness: 0.3 })
    );
    base.position.y = 0.075;
    base.castShadow = true;
    g.add(base);

    if (lampType === "changxin_gongdeng") {
      const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.05, 0.08, 0.5, 24),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.9, roughness: 0.2 })
      );
      stem.position.y = 0.4;
      stem.castShadow = true;
      g.add(stem);

      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.25, 0.35, 0.6, 32),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.85, roughness: 0.25 })
      );
      body.position.y = 0.95;
      body.castShadow = true;
      g.add(body);

      for (let i = 0; i < 6; i++) {
        const angle = (i / 6) * Math.PI * 2;
        const ring = new THREE.Mesh(
          new THREE.SphereGeometry(0.025, 16, 16),
          new THREE.MeshStandardMaterial({ color: colors.accent, metalness: 0.95, roughness: 0.1 })
        );
        ring.position.set(Math.cos(angle) * 0.38, 0.95, Math.sin(angle) * 0.38);
        g.add(ring);
      }
    } else if (lampType === "yanyu_deng") {
      const gooseBody = new THREE.Mesh(
        new THREE.SphereGeometry(0.35, 32, 32),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.7, roughness: 0.35 })
      );
      gooseBody.scale.set(1.2, 0.8, 0.8);
      gooseBody.position.y = 0.55;
      gooseBody.castShadow = true;
      g.add(gooseBody);

      const gooseNeck = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.1, 0.45, 24),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.7, roughness: 0.35 })
      );
      gooseNeck.position.y = 1.05;
      gooseNeck.position.x = -0.05;
      gooseNeck.rotation.z = -0.3;
      g.add(gooseNeck);

      const gooseHead = new THREE.Mesh(
        new THREE.SphereGeometry(0.1, 20, 20),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.7, roughness: 0.35 })
      );
      gooseHead.position.set(-0.18, 1.3, 0);
      g.add(gooseHead);

      const fishShade = new THREE.Mesh(
        new THREE.ConeGeometry(0.25, 0.45, 16),
        new THREE.MeshStandardMaterial({
          color: colors.shade,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.75,
          metalness: 0.2,
          roughness: 0.55,
        })
      );
      fishShade.rotation.z = Math.PI / 8;
      fishShade.position.set(-0.12, 1.35, 0);
      g.add(fishShade);
    } else if (lampType === "niu_deng") {
      const cowBody = new THREE.Mesh(
        new THREE.SphereGeometry(0.4, 32, 32),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.6, roughness: 0.45 })
      );
      cowBody.scale.set(1.3, 0.85, 0.85);
      cowBody.position.y = 0.55;
      cowBody.castShadow = true;
      g.add(cowBody);

      const cowHead = new THREE.Mesh(
        new THREE.SphereGeometry(0.22, 24, 24),
        new THREE.MeshStandardMaterial({ color: colors.body, metalness: 0.6, roughness: 0.45 })
      );
      cowHead.position.set(-0.35, 0.85, 0);
      g.add(cowHead);

      for (const side of [-1, 1]) {
        const horn = new THREE.Mesh(
          new THREE.CylinderGeometry(0.025, 0.05, 0.35, 16),
          new THREE.MeshStandardMaterial({ color: colors.accent, metalness: 0.85, roughness: 0.25 })
        );
        horn.position.set(-0.28 + side * 0.1, 1.15, side * 0.12);
        horn.rotation.z = side * 0.4;
        g.add(horn);
      }

      const shade = new THREE.Mesh(
        new THREE.CylinderGeometry(0.25, 0.35, 0.35, 32, 1, true),
        new THREE.MeshStandardMaterial({
          color: colors.shade,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.7,
        })
      );
      shade.position.y = 1.15;
      g.add(shade);

      for (let i = 0; i < 3; i++) {
        const deco = new THREE.Mesh(
          new THREE.TorusGeometry(0.38 - i * 0.05, 0.015, 12, 64),
          new THREE.MeshStandardMaterial({ color: colors.accent, metalness: 0.95, roughness: 0.1 })
        );
        deco.position.y = 0.6 + i * 0.15;
        g.add(deco);
      }
    }

    const topRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.32, 0.025, 16, 64),
      new THREE.MeshStandardMaterial({ color: colors.accent, metalness: 0.95, roughness: 0.1 })
    );
    topRing.position.y = 1.25;
    g.add(topRing);

    const flameGroup = new THREE.Group();
    flameGroup.position.y = 1.1;
    const flameLight = new THREE.PointLight(0xff8833, 1.0, 5, 2);
    flameLight.position.y = 0.2;
    flameGroup.add(flameLight);
    const flame = new THREE.Mesh(
      new THREE.ConeGeometry(0.08, 0.2, 16),
      new THREE.MeshBasicMaterial({ color: 0xff6600, transparent: true, opacity: 0.9 })
    );
    flame.position.y = 0.12;
    flameGroup.add(flame);
    const innerFlame = new THREE.Mesh(
      new THREE.ConeGeometry(0.04, 0.12, 16),
      new THREE.MeshBasicMaterial({ color: 0xffff66 })
    );
    innerFlame.position.y = 0.08;
    flameGroup.add(innerFlame);
    g.add(flameGroup);
    g.userData.flameGroup = flameGroup;

    const flue = new THREE.Mesh(
      new THREE.CylinderGeometry(0.025, 0.025, 0.6, 24),
      new THREE.MeshStandardMaterial({ color: 0x2a1a1a, metalness: 0.7, roughness: 0.4 })
    );
    flue.position.y = 1.8;
    g.add(flue);

    g.userData.lampType = lampType;
    return g;
  }

  function clearDynastyCompareGroup() {
    if (!dynastyCompareGroup) return;
    while (dynastyCompareGroup.children.length > 0) {
      const c = dynastyCompareGroup.children[0];
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
      dynastyCompareGroup.remove(c);
    }
  }

  function showDynastyCompareView() {
    clearDynastyCompareGroup();
    if (!dynastyCompareGroup) {
      dynastyCompareGroup = new THREE.Group();
      scene.add(dynastyCompareGroup);
    }
    const types = ["changxin_gongdeng", "yanyu_deng", "niu_deng"];
    const positions = [-3.5, 0, 3.5];
    const nameMap = { changxin_gongdeng: "长信宫灯(西汉)", yanyu_deng: "雁鱼灯(西汉)", niu_deng: "错银铜牛灯(东汉)" };
    types.forEach((t, i) => {
      const lamp = createAnyLampModel(t);
      lamp.position.set(positions[i], 0, 0);
      dynastyCompareGroup.add(lamp);

      const labelCanvas = document.createElement("canvas");
      labelCanvas.width = 256;
      labelCanvas.height = 64;
      const ctx = labelCanvas.getContext("2d");
      ctx.fillStyle = "rgba(10,10,26,0.85)";
      ctx.fillRect(0, 0, 256, 64);
      ctx.strokeStyle = "#e8c87a";
      ctx.lineWidth = 2;
      ctx.strokeRect(0, 0, 256, 64);
      ctx.fillStyle = "#e8c87a";
      ctx.font = "bold 22px Microsoft YaHei";
      ctx.textAlign = "center";
      ctx.fillText(nameMap[t] || t, 128, 40);
      const tex = new THREE.CanvasTexture(labelCanvas);
      const labelMat = new THREE.SpriteMaterial({ map: tex, transparent: true });
      const label = new THREE.Sprite(labelMat);
      label.position.set(positions[i], 2.6, 0);
      label.scale.set(1.4, 0.35, 1);
      dynastyCompareGroup.add(label);
    });
  }

  function clearBanquetScene() {
    if (!multiLampGroup) return;
    while (multiLampGroup.children.length > 0) {
      const c = multiLampGroup.children[0];
      if (c.geometry) c.geometry.dispose();
      if (c.material) c.material.dispose();
      multiLampGroup.remove(c);
    }
    if (banquetRoomGroup) {
      while (banquetRoomGroup.children.length > 0) {
        const c = banquetRoomGroup.children[0];
        if (c.geometry) c.geometry.dispose();
        if (c.material) c.material.dispose();
        banquetRoomGroup.remove(c);
      }
    }
  }

  function showBanquetScene(sceneConfig) {
    clearBanquetScene();
    const rg = sceneConfig && sceneConfig.room_geometry ? sceneConfig.room_geometry : { room_size_x_m: 20, room_size_y_m: 15, room_size_z_m: 5 };
    const lampPositions = sceneConfig && sceneConfig.lamp_positions ? sceneConfig.lamp_positions : [];

    if (!banquetRoomGroup) {
      banquetRoomGroup = new THREE.Group();
      scene.add(banquetRoomGroup);
    }
    if (!multiLampGroup) {
      multiLampGroup = new THREE.Group();
      scene.add(multiLampGroup);
    }

    const floorGeo = new THREE.PlaneGeometry(rg.room_size_x_m, rg.room_size_y_m);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.92, metalness: 0.08 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    banquetRoomGroup.add(floor);

    const grid = new THREE.GridHelper(Math.max(rg.room_size_x_m, rg.room_size_y_m), 30, 0x554433, 0x332211);
    grid.position.y = 0.01;
    banquetRoomGroup.add(grid);

    const wallMat = new THREE.MeshStandardMaterial({ color: 0x332a20, roughness: 0.95, metalness: 0, side: THREE.BackSide });
    const backWall = new THREE.Mesh(new THREE.PlaneGeometry(rg.room_size_x_m, rg.room_size_z_m), wallMat);
    backWall.position.set(0, rg.room_size_z_m / 2, -rg.room_size_y_m / 2);
    banquetRoomGroup.add(backWall);

    const tableGeo = new THREE.BoxGeometry(rg.room_size_x_m * 0.6, 0.1, rg.room_size_y_m * 0.3);
    const tableMat = new THREE.MeshStandardMaterial({ color: 0x5a3a2a, roughness: 0.7, metalness: 0.1 });
    const table = new THREE.Mesh(tableGeo, tableMat);
    table.position.y = 0.8;
    table.castShadow = true;
    table.receiveShadow = true;
    banquetRoomGroup.add(table);

    lampPositions.forEach((lp, idx) => {
      const lampType = lp.lamp_type || "changxin_gongdeng";
      const lamp = createAnyLampModel(lampType);
      const wx = lp.x_m - rg.room_size_x_m / 2;
      const wy = lp.y_m - rg.room_size_y_m / 2;
      lamp.position.set(wx, 0, wy);
      lamp.scale.setScalar(0.7);
      multiLampGroup.add(lamp);

      const labelCanvas = document.createElement("canvas");
      labelCanvas.width = 128;
      labelCanvas.height = 32;
      const ctx = labelCanvas.getContext("2d");
      ctx.fillStyle = "rgba(10,10,26,0.8)";
      ctx.fillRect(0, 0, 128, 32);
      ctx.strokeStyle = "#e8c87a";
      ctx.lineWidth = 1;
      ctx.strokeRect(0, 0, 128, 32);
      ctx.fillStyle = "#e8c87a";
      ctx.font = "bold 12px Microsoft YaHei";
      ctx.textAlign = "center";
      ctx.fillText(`${lampType} #${idx + 1}`, 64, 22);
      const tex = new THREE.CanvasTexture(labelCanvas);
      const labelMat = new THREE.SpriteMaterial({ map: tex, transparent: true });
      const label = new THREE.Sprite(labelMat);
      label.position.set(wx, 2.2, wy);
      label.scale.set(0.8, 0.2, 1);
      multiLampGroup.add(label);
    });
  }

  function updateBanquetPM25Cloud(gridData, roomGeometry) {
    clearPM25Cloud();
    if (!gridData || !gridData.grid_data) return;
    const rg = roomGeometry || { room_size_x_m: ROOM_SIZE.x, room_size_y_m: ROOM_SIZE.y, room_size_z_m: ROOM_SIZE.z };

    gridData.grid_data.forEach((p) => {
      const wx = p.world_x !== undefined ? p.world_x : 0;
      const wy = p.world_y !== undefined ? p.world_y : 0;
      const wz = p.world_z !== undefined ? p.world_z : 0;
      const conc = p.concentration;
      const color = getPM25Color(conc);
      const opacity = Math.min(0.6, 0.1 + conc / 250);
      const size = Math.max(0.08, 0.25 + conc / 500);

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(size, 8, 8),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity })
      );
      mesh.position.set(wx, wy, wz);
      pm25CloudGroup.add(mesh);
    });
  }

  function switchView(viewName) {
    currentView = viewName;
    if (!lampGroup || !particleSystem || !pm25CloudGroup) return;

    const isDefaultView = ["lamp", "particles", "pm25"].indexOf(viewName) >= 0;
    lampGroup.visible = isDefaultView && (viewName === "lamp" || viewName === "particles");
    particleSystem.visible = viewName === "particles";
    pm25CloudGroup.visible = viewName === "pm25" || viewName === "banquet_pm25";

    if (dynastyCompareGroup) dynastyCompareGroup.visible = viewName === "dynasty_compare";
    if (multiLampGroup) multiLampGroup.visible = viewName === "banquet" || viewName === "banquet_pm25";
    if (banquetRoomGroup) banquetRoomGroup.visible = viewName === "banquet" || viewName === "banquet_pm25";

    if (viewName === "dynasty_compare") {
      showDynastyCompareView();
    }
  }

  function setFlameIntensity(intensity) {
    const setInt = (group) => {
      if (!group) return;
      group.traverse((obj) => {
        if (obj.isPointLight) obj.intensity = 0.5 + intensity * 1.8;
        if (obj.isMesh && obj.material && obj.material.color) {
          const hex = obj.material.color.getHex();
          if (hex === 0xff6600 || hex === 0xffff66) {
            obj.scale.setScalar(0.5 + intensity * 0.9);
          }
        }
      });
    };
    setInt(lampGroup);
    setInt(dynastyCompareGroup);
    setInt(multiLampGroup);
  }

  function setBlockageVisual(blockage) {
    const opacity = 0.25 + blockage * 0.55;
    [lampGroup, dynastyCompareGroup, multiLampGroup].forEach((g) => {
      if (!g) return;
      g.traverse((obj) => {
        if (obj.isMesh && obj.material && obj.material.color && obj.material.color.getHex() === 0x888888) {
          obj.material.opacity = opacity;
        }
      });
    });
  }

  function onWindowResize() {
    camera.aspect = (window.innerWidth - 380) / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth - 380, window.innerHeight);
  }

  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();
    controls.update();
    animateFlame(t);
    animateParticles();
    renderer.render(scene, camera);
  }

  // 暴露给外部模块
  window.GongDeng3D = {
    init,
    updateParticleTrajectories,
    updatePM25Cloud,
    clearParticleSystem,
    switchView,
    getCurrentView: () => currentView,
    getROOM_SIZE: () => ROOM_SIZE,
    createAnyLampModel,
    showDynastyCompareView,
    showBanquetScene,
    updateBanquetPM25Cloud,
    setCurrentLampType: () => {},
  };
  window.setFlameIntensity = setFlameIntensity;
  window.setBlockageVisual = setBlockageVisual;
  window.showBanquetScene = showBanquetScene;
  window.updateBanquetPM25Cloud = updateBanquetPM25Cloud;
  window.switchView = switchView;
})();
