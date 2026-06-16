const API_BASE = window.location.origin;

let scene, camera, renderer, controls;
let lampGroup, particleSystem, pm25CloudGroup;
let currentView = 'lamp';
let flameIntensity = 0.8;
let blockageDegree = 0.0;
let particleCount = 50;
let fuelType = 'animal_fat';
let airChangeRate = 1.0;
let outdoorPm25 = 25.0;
let autoUpdate = true;
let currentSensorData = null;
let currentFlueSim = null;
let currentAirQuality = null;

const ROOM_SIZE = { x: 10, y: 8, z: 3 };

function init() {
    const canvas = document.getElementById('three-canvas');

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a1a);
    scene.fog = new THREE.Fog(0x0a0a1a, 15, 40);

    camera = new THREE.PerspectiveCamera(
        50,
        window.innerWidth / window.innerHeight,
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

    setupLights();
    createRoom();
    createGongdengModel();
    createParticleSystem();
    createPM25Cloud();

    window.addEventListener('resize', onWindowResize);
    setupEventListeners();

    animate();
    startDataPolling();

    document.getElementById('loading-overlay').style.display = 'none';
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
        metalness: 0.1
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
        side: THREE.BackSide
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

    scene.add(roomGroup);
}

function createGongdengModel() {
    lampGroup = new THREE.Group();

    const bronzeMat = new THREE.MeshStandardMaterial({
        color: 0xb08050,
        roughness: 0.5,
        metalness: 0.7
    });

    const darkBronzeMat = new THREE.MeshStandardMaterial({
        color: 0x604020,
        roughness: 0.7,
        metalness: 0.6
    });

    const goldMat = new THREE.MeshStandardMaterial({
        color: 0xd4a84a,
        roughness: 0.3,
        metalness: 0.9
    });

    const baseGeo = new THREE.CylinderGeometry(0.2, 0.25, 0.15, 32);
    const base = new THREE.Mesh(baseGeo, darkBronzeMat);
    base.position.y = 0.075;
    base.castShadow = true;
    base.receiveShadow = true;
    lampGroup.add(base);

    const stemGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.5, 24);
    const stem = new THREE.Mesh(stemGeo, bronzeMat);
    stem.position.y = 0.4;
    stem.castShadow = true;
    lampGroup.add(stem);

    const bodyGeo = new THREE.CylinderGeometry(0.35, 0.25, 0.6, 32);
    const body = new THREE.Mesh(bodyGeo, bronzeMat);
    body.position.y = 0.85;
    body.castShadow = true;
    lampGroup.add(body);

    const ringGeo = new THREE.TorusGeometry(0.35, 0.03, 16, 48);
    const topRing = new THREE.Mesh(ringGeo, goldMat);
    topRing.rotation.x = Math.PI / 2;
    topRing.position.y = 1.15;
    lampGroup.add(topRing);

    const bottomRing = new THREE.Mesh(ringGeo, goldMat);
    bottomRing.rotation.x = Math.PI / 2;
    bottomRing.position.y = 0.55;
    bottomRing.scale.set(0.7, 0.7, 0.7);
    lampGroup.add(bottomRing);

    const lampShadeGeo = new THREE.CylinderGeometry(0.5, 0.35, 0.4, 32, 1, true);
    const lampShadeMat = new THREE.MeshStandardMaterial({
        color: 0x884422,
        roughness: 0.6,
        metalness: 0.5,
        side: THREE.DoubleSide
    });
    const lampShade = new THREE.Mesh(lampShadeGeo, lampShadeMat);
    lampShade.position.y = 1.4;
    lampShade.castShadow = true;
    lampGroup.add(lampShade);

    const topGeo = new THREE.CylinderGeometry(0.15, 0.5, 0.1, 32);
    const top = new THREE.Mesh(topGeo, goldMat);
    top.position.y = 1.65;
    top.castShadow = true;
    lampGroup.add(top);

    const flueGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.8, 24);
    const flueMat = new THREE.MeshStandardMaterial({
        color: 0x403020,
        roughness: 0.8,
        metalness: 0.4
    });
    const flue = new THREE.Mesh(flueGeo, flueMat);
    flue.position.y = 2.1;
    flue.castShadow = true;
    lampGroup.add(flue);

    const flueTopGeo = new THREE.CylinderGeometry(0.08, 0.04, 0.06, 24);
    const flueTop = new THREE.Mesh(flueTopGeo, goldMat);
    flueTop.position.y = 2.53;
    lampGroup.add(flueTop);

    const handleShape = new THREE.TorusGeometry(0.15, 0.025, 16, 32, Math.PI);
    const handle = new THREE.Mesh(handleShape, goldMat);
    handle.rotation.z = Math.PI;
    handle.position.set(0, 2.6, 0);
    lampGroup.add(handle);

    const flameLight = new THREE.PointLight(0xff8833, 0.8 * flameIntensity, 3, 2);
    flameLight.position.set(0, 1.3, 0);
    flameLight.castShadow = true;
    lampGroup.add(flameLight);
    lampGroup.userData.flameLight = flameLight;

    createFlameEffect(lampGroup);

    for (let i = 0; i < 6; i++) {
        const angle = (i / 6) * Math.PI * 2;
        const r = 0.3;
        const decoGeo = new THREE.SphereGeometry(0.025, 16, 16);
        const deco = new THREE.Mesh(decoGeo, goldMat);
        deco.position.set(
            Math.cos(angle) * r,
            0.85,
            Math.sin(angle) * r
        );
        lampGroup.add(deco);
    }

    lampGroup.position.set(0, 0, 0);
    scene.add(lampGroup);
}

function createFlameEffect(parent) {
    const flameGroup = new THREE.Group();

    const flameGeo = new THREE.ConeGeometry(0.08, 0.25, 16);
    const flameMat = new THREE.MeshBasicMaterial({
        color: 0xff6622,
        transparent: true,
        opacity: 0.9
    });
    const flame = new THREE.Mesh(flameGeo, flameMat);
    flame.position.y = 1.3;
    flameGroup.add(flame);

    const innerFlameGeo = new THREE.ConeGeometry(0.04, 0.18, 16);
    const innerFlameMat = new THREE.MeshBasicMaterial({
        color: 0xffff88,
        transparent: true,
        opacity: 0.95
    });
    const innerFlame = new THREE.Mesh(innerFlameGeo, innerFlameMat);
    innerFlame.position.y = 1.28;
    flameGroup.add(innerFlame);

    const particleCount = 30;
    const smokeGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 0.1;
        positions[i * 3 + 1] = Math.random() * 0.3;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 0.1;
        sizes[i] = Math.random() * 0.05 + 0.02;
    }

    smokeGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    smokeGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    const smokeMat = new THREE.PointsMaterial({
        color: 0x665544,
        size: 0.04,
        transparent: true,
        opacity: 0.4,
        sizeAttenuation: true
    });

    const smokeParticles = new THREE.Points(smokeGeo, smokeMat);
    smokeParticles.position.y = 1.4;
    flameGroup.add(smokeParticles);

    flameGroup.userData = { flame, innerFlame, smokeParticles, baseParticles: positions.slice() };
    parent.userData.flameGroup = flameGroup;
    parent.add(flameGroup);
}

function createParticleSystem() {
    particleSystem = new THREE.Group();

    const trajectoryLines = [];
    const flowParticles = [];

    particleSystem.userData = {
        trajectoryLines,
        flowParticles,
        flueWorldOffset: new THREE.Vector3(0, 1.65, 0)
    };
    particleSystem.visible = false;

    scene.add(particleSystem);
}

function updateParticleTrajectories(trajectories, flueLength, flueDiameter) {
    const { trajectoryLines, flowParticles, flueWorldOffset } = particleSystem.userData;

    trajectoryLines.forEach(line => particleSystem.remove(line));
    flowParticles.forEach(p => particleSystem.remove(p));
    trajectoryLines.length = 0;
    flowParticles.length = 0;

    const flowColors = [0xff6633, 0xff8844, 0xffaa55, 0xffcc66, 0xddaa44];

    const lampWorldPos = new THREE.Vector3();
    lampGroup.getWorldPosition(lampWorldPos);
    const flueWorldBase = lampWorldPos.clone().add(flueWorldOffset);

    trajectories.forEach((traj, idx) => {
        const worldPoints = traj.points.map(p => {
            const localPoint = new THREE.Vector3(p[0], p[1], p[2]);
            return localPoint.add(flueWorldBase);
        });

        const geometry = new THREE.BufferGeometry().setFromPoints(worldPoints);

        const color = flowColors[idx % flowColors.length];
        const material = new THREE.LineBasicMaterial({
            color: color,
            transparent: true,
            opacity: 0.5
        });

        const line = new THREE.Line(geometry, material);
        line.userData.isWorldSpace = true;
        line.frustumCulled = false;
        trajectoryLines.push(line);
        particleSystem.add(line);

        for (let i = 0; i < 3; i++) {
            const particleGeo = new THREE.SphereGeometry(0.008, 8, 8);
            const particleMat = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.8,
                depthWrite: false
            });
            const particle = new THREE.Mesh(particleGeo, particleMat);
            particle.userData = {
                trajectory: worldPoints,
                progress: Math.random(),
                speed: 0.003 + Math.random() * 0.003,
                isWorldSpace: true
            };
            particle.frustumCulled = false;
            flowParticles.push(particle);
            particleSystem.add(particle);
        }
    });

    const flueGeo = new THREE.CylinderGeometry(
        flueDiameter / 2 + 0.005,
        flueDiameter / 2 + 0.005,
        flueLength,
        24,
        1,
        true
    );
    const flueMat = new THREE.MeshBasicMaterial({
        color: 0x66aaff,
        transparent: true,
        opacity: 0.15,
        side: THREE.DoubleSide,
        wireframe: true,
        depthWrite: false
    });
    const flueWire = new THREE.Mesh(flueGeo, flueMat);
    flueWire.position.copy(flueWorldBase);
    flueWire.position.y += flueLength / 2;
    flueWire.userData.isWorldSpace = true;
    flueWire.frustumCulled = false;
    particleSystem.add(flueWire);
    trajectoryLines.push(flueWire);

    const startMarkerGeo = new THREE.SphereGeometry(0.02, 16, 16);
    const startMarkerMat = new THREE.MeshBasicMaterial({
        color: 0x00ff88,
        transparent: true,
        opacity: 0.8
    });
    const startMarker = new THREE.Mesh(startMarkerGeo, startMarkerMat);
    startMarker.position.copy(flueWorldBase);
    startMarker.userData.isWorldSpace = true;
    particleSystem.add(startMarker);
    trajectoryLines.push(startMarker);

    const endMarkerGeo = new THREE.SphereGeometry(0.015, 16, 16);
    const endMarkerMat = new THREE.MeshBasicMaterial({
        color: 0xff4488,
        transparent: true,
        opacity: 0.8
    });
    const endMarker = new THREE.Mesh(endMarkerGeo, endMarkerMat);
    endMarker.position.copy(flueWorldBase);
    endMarker.position.y += flueLength;
    endMarker.userData.isWorldSpace = true;
    particleSystem.add(endMarker);
    trajectoryLines.push(endMarker);
}

function createPM25Cloud() {
    pm25CloudGroup = new THREE.Group();
    pm25CloudGroup.visible = false;
    scene.add(pm25CloudGroup);
}

function updatePM25Cloud(gridData) {
    while (pm25CloudGroup.children.length > 0) {
        const child = pm25CloudGroup.children[0];
        pm25CloudGroup.remove(child);
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
    }

    const nx = 5, ny = 5, nz = 5;
    const cellSizeX = ROOM_SIZE.x / (nx - 1);
    const cellSizeY = ROOM_SIZE.y / (ny - 1);
    const cellSizeZ = ROOM_SIZE.z / (nz - 1);

    gridData.forEach(point => {
        const wx = point.world_x !== undefined ? point.world_x : (point.grid_x * cellSizeX - ROOM_SIZE.x / 2);
        const wy = point.world_y !== undefined ? point.world_y : (point.grid_y * cellSizeY - ROOM_SIZE.y / 2);
        const wz = point.world_z !== undefined ? point.world_z : (point.grid_z * cellSizeZ);

        const color = getPM25Color(point.concentration);

        const sizeFactor = Math.min(1.5, 0.3 + point.concentration / 100);
        const opacity = Math.min(0.8, 0.1 + point.concentration / 200);

        const geo = new THREE.SphereGeometry(0.25 * sizeFactor, 12, 12);
        const mat = new THREE.MeshBasicMaterial({
            color: color,
            transparent: true,
            opacity: opacity
        });
        const sphere = new THREE.Mesh(geo, mat);

        sphere.position.set(wx, wz, wy);

        pm25CloudGroup.add(sphere);
    });

    const lampMarkerGeo = new THREE.SphereGeometry(0.3, 16, 16);
    const lampMarkerMat = new THREE.MeshBasicMaterial({
        color: 0xff8833,
        transparent: true,
        opacity: 0.8
    });
    const lampMarker = new THREE.Mesh(lampMarkerGeo, lampMarkerMat);
    lampMarker.position.set(0, 1.5, 0);
    pm25CloudGroup.add(lampMarker);
}

function getPM25Color(concentration) {
    if (concentration <= 35) return 0x55ff88;
    if (concentration <= 75) return 0xffcc55;
    if (concentration <= 115) return 0xff9955;
    if (concentration <= 150) return 0xff5555;
    if (concentration <= 250) return 0xcc66ff;
    return 0xff3333;
}

function animateFlame(time) {
    if (!lampGroup.userData.flameGroup) return;

    const { flame, innerFlame, smokeParticles } = lampGroup.userData.flameGroup;
    const flameLight = lampGroup.userData.flameLight;

    const flicker = 0.8 + Math.sin(time * 10) * 0.1 + Math.sin(time * 15) * 0.05;
    const intensity = flameIntensity * flicker;

    flame.scale.set(intensity, intensity * (1 + Math.sin(time * 8) * 0.1), intensity);
    innerFlame.scale.set(intensity * 0.8, intensity * 0.9, intensity * 0.8);

    if (flameLight) {
        flameLight.intensity = intensity * 1.2;
    }

    const positions = smokeParticles.geometry.attributes.position.array;
    const basePositions = lampGroup.userData.flameGroup.userData.baseParticles;

    for (let i = 0; i < positions.length / 3; i++) {
        positions[i * 3] = basePositions[i * 3] + Math.sin(time * 3 + i) * 0.02;
        positions[i * 3 + 1] = (basePositions[i * 3 + 1] + time * 0.3) % 0.8;
        positions[i * 3 + 2] = basePositions[i * 3 + 2] + Math.cos(time * 2 + i) * 0.02;
    }
    smokeParticles.geometry.attributes.position.needsUpdate = true;
    smokeParticles.material.opacity = 0.3 * flameIntensity;
}

function animateFlowParticles(time) {
    if (!particleSystem.visible) return;

    const { flowParticles } = particleSystem.userData;

    flowParticles.forEach(particle => {
        const { trajectory, speed } = particle.userData;
        if (!trajectory || trajectory.length < 2) return;

        particle.userData.progress += speed;
        if (particle.userData.progress > 1) {
            particle.userData.progress = 0;
        }

        const progress = particle.userData.progress;
        const idx = Math.floor(progress * (trajectory.length - 1));
        const nextIdx = Math.min(idx + 1, trajectory.length - 1);
        const t = (progress * (trajectory.length - 1)) % 1;

        const pos = new THREE.Vector3().lerpVectors(
            trajectory[idx],
            trajectory[nextIdx],
            t
        );
        particle.position.copy(pos);
    });
}

function animate() {
    requestAnimationFrame(animate);

    const time = performance.now() * 0.001;

    animateFlame(time);
    animateFlowParticles(time);

    if (pm25CloudGroup.visible) {
        pm25CloudGroup.children.forEach((child, i) => {
            if (child.material) {
                child.material.opacity = Math.min(
                    child.material.opacity,
                    0.3 + Math.sin(time * 2 + i) * 0.1
                );
            }
        });
    }

    controls.update();
    renderer.render(scene, camera);
    updateTimeDisplay();
}

function updateTimeDisplay() {
    const now = new Date();
    document.getElementById('current-time').textContent = now.toLocaleString('zh-CN');
}

function onWindowResize() {
    camera.aspect = (window.innerWidth - 380) / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth - 380, window.innerHeight);
}

function setupEventListeners() {
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            switchView(tab.dataset.view);
        });
    });

    document.getElementById('fuel-select').addEventListener('change', (e) => {
        fuelType = e.target.value;
        if (currentView === 'particles') {
            loadParticles();
        }
    });

    document.getElementById('flame-slider').addEventListener('input', (e) => {
        flameIntensity = parseFloat(e.target.value);
        document.getElementById('flame-val').textContent = flameIntensity.toFixed(2);
    });

    document.getElementById('blockage-slider').addEventListener('input', (e) => {
        blockageDegree = parseFloat(e.target.value);
        document.getElementById('blockage-val').textContent = blockageDegree.toFixed(2);
    });

    document.getElementById('ach-slider').addEventListener('input', (e) => {
        airChangeRate = parseFloat(e.target.value);
        document.getElementById('ach-val').textContent = airChangeRate.toFixed(1);
    });

    document.getElementById('outdoor-pm25-slider').addEventListener('input', (e) => {
        outdoorPm25 = parseFloat(e.target.value);
        document.getElementById('outdoor-pm25-val').textContent = Math.round(outdoorPm25);
    });

    document.getElementById('particles-slider').addEventListener('input', (e) => {
        particleCount = parseInt(e.target.value);
        document.getElementById('particles-val').textContent = particleCount;
        if (currentView === 'particles') {
            loadParticles();
        }
    });

    document.getElementById('btn-simulate').addEventListener('click', () => {
        triggerManualSimulation();
    });

    document.getElementById('btn-auto-toggle').addEventListener('click', (e) => {
        autoUpdate = !autoUpdate;
        e.target.textContent = autoUpdate ? '暂停自动' : '启动自动';
    });
}

function switchView(view) {
    currentView = view;

    lampGroup.visible = view === 'lamp' || view === 'particles';
    particleSystem.visible = view === 'particles';
    pm25CloudGroup.visible = view === 'pm25';

    document.getElementById('pm25-legend').style.display = view === 'pm25' ? 'block' : 'none';

    if (view === 'particles') {
        loadParticles();
        controls.target.set(0, 2.5, 0);
    } else if (view === 'pm25') {
        loadPM25Cloud();
        controls.target.set(0, 1.5, 0);
    } else {
        controls.target.set(0, 1.5, 0);
    }
}

async function loadParticles() {
    const vel = currentSensorData?.flue_velocity || 0.5;
    const temp = currentSensorData?.flue_temperature || 120;

    try {
        const res = await fetch(
            `/api/simulation/particles?flue_velocity=${vel}&flue_temperature=${temp}&num_particles=${particleCount}&fuel_type=${fuelType}`
        );
        const data = await res.json();
        updateParticleTrajectories(data.trajectories, data.flue_length, data.flue_diameter);
        const simInfo = document.getElementById('sim-info');
        if (data.fuel_name && simInfo) {
            const fuelDiv = document.createElement('div');
            fuelDiv.innerHTML = `燃料: <span>${data.fuel_name}</span>`;
            const existingFuel = simInfo.querySelector('.fuel-info');
            if (existingFuel) {
                existingFuel.remove();
            }
            fuelDiv.className = 'fuel-info';
            simInfo.insertBefore(fuelDiv, simInfo.firstChild);
        }
    } catch (e) {
        console.warn('加载粒子数据失败，使用模拟数据');
        const mockTrajectories = generateMockTrajectories(particleCount);
        updateParticleTrajectories(mockTrajectories, 0.8, 0.05);
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
        const res = await fetch('/api/simulation/pm25-grid/latest?lamp_id=1');
        const data = await res.json();
        const gridData = data.grid_data.map(p => {
            const nx = 5, ny = 5, nz = 5;
            return {
                ...p,
                world_x: (p.grid_x / (nx - 1)) * ROOM_SIZE.x - ROOM_SIZE.x / 2,
                world_y: (p.grid_y / (ny - 1)) * ROOM_SIZE.y - ROOM_SIZE.y / 2,
                world_z: (p.grid_z / (nz - 1)) * ROOM_SIZE.z
            };
        });
        updatePM25Cloud(gridData);
    } catch (e) {
        console.warn('加载PM2.5云图失败，使用模拟数据');
        updatePM25Cloud(generateMockPM25Grid());
    }
}

function generateMockPM25Grid() {
    const data = [];
    const nx = 5, ny = 5, nz = 5;
    const basePm25 = currentSensorData?.indoor_pm25 || 50;

    for (let i = 0; i < nx; i++) {
        for (let j = 0; j < ny; j++) {
            for (let k = 0; k < nz; k++) {
                const wx = (i / (nx - 1)) * ROOM_SIZE.x - ROOM_SIZE.x / 2;
                const wy = (j / (ny - 1)) * ROOM_SIZE.y - ROOM_SIZE.y / 2;
                const wz = (k / (nz - 1)) * ROOM_SIZE.z;

                const distToLamp = Math.sqrt(wx * wx + wy * wy + (wz - 1.5) * (wz - 1.5));
                const concentration = basePm25 + 30 * Math.exp(-distToLamp / 2) + (Math.random() - 0.5) * 10;

                data.push({
                    grid_x: i, grid_y: j, grid_z: k,
                    concentration: Math.max(10, concentration),
                    world_x: wx, world_y: wy, world_z: wz
                });
            }
        }
    }
    return data;
}

async function triggerManualSimulation() {
    const oil = 1.5 + flameIntensity * 1.5;
    const blockageFactor = 1 + blockageDegree * 2;
    const temp = 25 + (180 - 25) * flameIntensity * blockageFactor * 0.8;
    const velocity = (0.3 + flameIntensity * 0.4) / blockageFactor;
    const pm25 = 35 + flameIntensity * 20 - velocity * 5 + blockageDegree * 25;

    const payload = {
        lamp_id: 1,
        oil_consumption: oil,
        flue_temperature: temp,
        flue_velocity: velocity,
        indoor_pm25: pm25,
        oil_level: 450,
        ambient_temperature: 24,
        ambient_humidity: 55,
        fuel_type: fuelType,
        air_change_rate: airChangeRate,
        outdoor_pm25: outdoorPm25
    };

    try {
        const res = await fetch('/api/sensor/data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.status === 'success') {
            await fetchLatestData();
        }
    } catch (e) {
        console.error('手动仿真失败', e);
    }
}

async function fetchLatestData() {
    try {
        const res = await fetch('/api/sensor/data/latest?lamp_id=1');
        if (res.ok) {
            const data = await res.json();
            currentSensorData = data.sensor;
            currentFlueSim = data.flue_simulation;
            currentAirQuality = data.air_quality;
            updateDashboard(data);
            updateStatus(data);

            if (currentView === 'particles') loadParticles();
            if (currentView === 'pm25') loadPM25Cloud();
        }
    } catch (e) {
        useMockData();
    }

    try {
        const statRes = await fetch('/api/statistics?lamp_id=1&hours=24');
        if (statRes.ok) {
            const stats = await statRes.json();
            updateStatistics(stats);
        }
    } catch (e) {}
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
        ambient_humidity: 55
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
        flow_regime: 'laminar'
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
        aqi_level: '良',
        health_risk: '空气质量可接受'
    };

    updateDashboard({
        sensor: currentSensorData,
        flue_simulation: currentFlueSim,
        air_quality: currentAirQuality,
        alerts: []
    });
}

function updateDashboard(data) {
    const s = data.sensor;
    if (s) {
        document.getElementById('metric-oil').textContent = s.oil_consumption?.toFixed(2) || '--';
        document.getElementById('metric-oil-level').textContent = s.oil_level?.toFixed(0) || '--';
        document.getElementById('metric-temp').textContent = s.flue_temperature?.toFixed(1) || '--';
        document.getElementById('metric-velocity').textContent = s.flue_velocity?.toFixed(3) || '--';
        document.getElementById('metric-pm25').textContent = s.indoor_pm25?.toFixed(1) || '--';
        document.getElementById('metric-amb-temp').textContent = s.ambient_temperature?.toFixed(1) || '--';

        const pm25Card = document.getElementById('card-pm25');
        pm25Card.classList.remove('good', 'warning', 'danger');
        if (s.indoor_pm25 <= 35) pm25Card.classList.add('good');
        else if (s.indoor_pm25 <= 75) pm25Card.classList.add('warning');
        else pm25Card.classList.add('danger');

        const tempCard = document.getElementById('card-temp');
        tempCard.classList.remove('warning', 'danger');
        if (s.flue_temperature > 200) tempCard.classList.add('danger');
        else if (s.flue_temperature > 150) tempCard.classList.add('warning');

        const velCard = document.getElementById('card-velocity');
        velCard.classList.remove('warning', 'danger');
        if (s.flue_velocity < 0.1) velCard.classList.add('danger');
        else if (s.flue_velocity < 0.2) velCard.classList.add('warning');
    }

    const fs = data.flue_simulation;
    if (fs) {
        const regimeMap = { 'laminar': '层流', 'transitional': '过渡流', 'turbulent': '湍流' };
        document.getElementById('info-regime').textContent = regimeMap[fs.flow_regime] || fs.flow_regime;
        document.getElementById('info-re').textContent = fs.reynolds_number?.toFixed(0) || '-';
        document.getElementById('info-nu').textContent = fs.nusselt_number?.toFixed(2) || '-';
        document.getElementById('info-settle').textContent = fs.settling_efficiency?.toFixed(1) || '-';
    }

    const aq = data.air_quality;
    if (aq) {
        document.getElementById('info-purify').textContent = aq.purification_rate?.toFixed(2) || '-';
        updateAQIBadge(aq.aqi_level, aq.health_risk);
    }

    updateAlerts(data.alerts || []);
}

function updateAQIBadge(level, risk) {
    const container = document.getElementById('aqi-container');
    const classMap = {
        '优': 'aqi-good',
        '良': 'aqi-moderate',
        '轻度污染': 'aqi-unhealthy-sensitive',
        '中度污染': 'aqi-unhealthy',
        '重度污染': 'aqi-very-unhealthy',
        '严重污染': 'aqi-hazardous'
    };
    const cls = classMap[level] || 'aqi-good';
    container.innerHTML = `<div class="aqi-badge ${cls}">AQI: ${level} - ${risk || ''}</div>`;
}

function updateStatus(data) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    const hasDanger = data.alerts?.some(a => a.severity === 'CRITICAL');
    const hasWarning = data.alerts?.some(a => a.severity === 'WARNING');

    dot.classList.remove('warning', 'danger');
    if (hasDanger) {
        dot.classList.add('danger');
        text.textContent = '存在严重告警，请立即处理';
    } else if (hasWarning) {
        dot.classList.add('warning');
        text.textContent = '存在警告信息';
    } else {
        text.textContent = '系统运行正常';
    }
}

function updateAlerts(alerts) {
    const list = document.getElementById('alert-list');
    if (!alerts || alerts.length === 0) {
        list.innerHTML = '<div class="alert-empty">暂无告警</div>';
        return;
    }

    list.innerHTML = alerts.map(alert => {
        const isWarning = alert.severity === 'WARNING';
        const typeMap = {
            'FLUE_BLOCKAGE': '烟道堵塞',
            'PM25_EXCEEDED': 'PM2.5超标',
            'TEMPERATURE_HIGH': '温度过高'
        };
        const timeStr = new Date(alert.time).toLocaleString('zh-CN');
        return `
            <div class="alert-item ${isWarning ? 'warning' : ''}">
                <div class="alert-type">${typeMap[alert.alert_type] || alert.alert_type} [${alert.severity}]</div>
                <div>${alert.message}</div>
                <div class="alert-time">${timeStr}</div>
            </div>
        `;
    }).join('');
}

function updateStatistics(stats) {
    document.getElementById('stat-avg-pm25').textContent = stats.avg_pm25?.toFixed(1) || '--';
    document.getElementById('stat-max-pm25').textContent = stats.max_pm25?.toFixed(1) || '--';
    document.getElementById('stat-avg-temp').textContent = stats.avg_flue_temperature?.toFixed(1) || '--';
    document.getElementById('stat-count').textContent = stats.data_points || '--';
}

function startDataPolling() {
    fetchLatestData();
    setInterval(() => {
        if (autoUpdate) {
            fetchLatestData();
        }
    }, 5000);
}

window.addEventListener('load', init);
