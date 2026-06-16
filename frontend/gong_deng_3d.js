/* =========================================================
 * gong_deng_3d.js
 * 职责：Three.js 3D 场景、宫灯建模、烟气流线粒子、PM2.5云图、视图切换
 * 暴露：window.GongDeng3D 全局对象，供 air_quality_panel.js 调用
 * ========================================================= */
(function () {
  const ROOM_SIZE = { x: 10, y: 8, z: 3 };

  let scene, camera, renderer, controls;
  let lampGroup, particleSystem, pm25CloudGroup;
  let currentView = "lamp";
  let clock;

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

  function switchView(viewName) {
    currentView = viewName;
    if (!lampGroup || !particleSystem || !pm25CloudGroup) return;
    lampGroup.visible = viewName === "lamp" || viewName === "particles";
    particleSystem.visible = viewName === "particles";
    pm25CloudGroup.visible = viewName === "pm25";
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
  };
})();
