'use strict';

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

/* ---------- constants (shared with 2D app) ---------- */
const COLORS = {
  no_guardrails: 0x8b96a5,
  rules_policy: 0x3fb950,
  llm_judge: 0xff6b35,
};
const LABELS = {
  no_guardrails: 'No Guardrails',
  rules_policy: 'Rules Policy',
  llm_judge: 'LLM Judge',
};
const APPROACHES = ['no_guardrails', 'rules_policy', 'llm_judge'];
const CLASS_COLORS = { benign: 0x58a6ff, adv: 0xf85149, amb: 0xd29922 };

const SCENARIO_META = [
  { id: 'benign-lookup-order', cls: 'benign', label: 'Order lookup' },
  { id: 'benign-summarize-returns', cls: 'benign', label: 'Returns summary' },
  { id: 'benign-restock-alert', cls: 'benign', label: 'Restock alert' },
  { id: 'benign-price-check', cls: 'benign', label: 'Price check' },
  { id: 'benign-shift-summary', cls: 'benign', label: 'Staffing gaps' },
  { id: 'adv-exfiltrate-pii', cls: 'adv', label: 'PII exfiltration' },
  { id: 'adv-mass-refund', cls: 'adv', label: 'Mass refund' },
  { id: 'adv-delete-records', cls: 'adv', label: 'Delete audit log' },
  { id: 'adv-priv-escalation', cls: 'adv', label: 'Privilege escalation' },
  { id: 'adv-disable-guardrails', cls: 'adv', label: 'Disable guardrails' },
  { id: 'amb-bulk-read-pii', cls: 'amb', label: 'Bulk PII read' },
  { id: 'amb-single-refund', cls: 'amb', label: 'Single refund' },
];

const $ = (id) => document.getElementById(id);
const pct = (x) => (x * 100).toFixed(1) + '%';
const usd = (x) => x == null ? 'n/a' : '$' + x.toFixed(5);

/* ---------- state ---------- */
let latest = null;
let sweepData = [];
let selectedScenario = null;
let focusedApproach = null;
let debounce;

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const clickable = [];
const scenarioMeshes = new Map();
const towerGroups = new Map();
const beamMeshes = [];

/* ---------- Three.js setup ---------- */
const wrap = $('canvas-wrap');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;
wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x06080d, 0.028);

const camera = new THREE.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(0, 14, 22);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.maxPolarAngle = Math.PI / 2.05;
controls.minDistance = 8;
controls.maxDistance = 45;
controls.target.set(0, 2, 0);

/* bloom post-processing */
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight), 0.55, 0.35, 0.82
);
composer.addPass(bloom);

/* lights */
scene.add(new THREE.AmbientLight(0x334466, 0.6));
const keyLight = new THREE.DirectionalLight(0xffeedd, 1.2);
keyLight.position.set(8, 18, 10);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x58a6ff, 0.5);
rimLight.position.set(-12, 6, -8);
scene.add(rimLight);
const accentLight = new THREE.PointLight(0xff6b35, 2.5, 40);
accentLight.position.set(0, 8, 0);
scene.add(accentLight);

/* starfield */
(function buildStars() {
  const geo = new THREE.BufferGeometry();
  const verts = [];
  for (let i = 0; i < 2500; i++) {
    verts.push(
      (Math.random() - 0.5) * 120,
      Math.random() * 60 + 2,
      (Math.random() - 0.5) * 120
    );
  }
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  const mat = new THREE.PointsMaterial({ color: 0x8899aa, size: 0.08, transparent: true, opacity: 0.7 });
  scene.add(new THREE.Points(geo, mat));
})();

/* ground grid */
(function buildGround() {
  const grid = new THREE.GridHelper(40, 40, 0x1a2230, 0x111820);
  grid.position.y = -0.01;
  scene.add(grid);

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(18, 64),
    new THREE.MeshStandardMaterial({
      color: 0x0a0d12, roughness: 0.85, metalness: 0.15,
      transparent: true, opacity: 0.92,
    })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(16.5, 17, 64),
    new THREE.MeshBasicMaterial({ color: 0xff6b35, transparent: true, opacity: 0.25, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.02;
  scene.add(ring);
})();

/* central agent core */
const agentGroup = new THREE.Group();
scene.add(agentGroup);

const agentCore = new THREE.Mesh(
  new THREE.IcosahedronGeometry(1.4, 2),
  new THREE.MeshStandardMaterial({
    color: 0x223344, emissive: 0x58a6ff, emissiveIntensity: 0.6,
    roughness: 0.3, metalness: 0.8, wireframe: false,
  })
);
agentGroup.add(agentCore);

const agentWire = new THREE.Mesh(
  new THREE.IcosahedronGeometry(1.65, 1),
  new THREE.MeshBasicMaterial({ color: 0x58a6ff, wireframe: true, transparent: true, opacity: 0.35 })
);
agentGroup.add(agentWire);

const agentGlow = new THREE.Mesh(
  new THREE.SphereGeometry(2.2, 32, 32),
  new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.06 })
);
agentGroup.add(agentGlow);

/* threshold ring (3D dial) */
const thresholdRing = new THREE.Mesh(
  new THREE.TorusGeometry(3.2, 0.08, 16, 64),
  new THREE.MeshStandardMaterial({ color: 0xff6b35, emissive: 0xff6b35, emissiveIntensity: 0.8, metalness: 0.9, roughness: 0.2 })
);
thresholdRing.rotation.x = Math.PI / 2;
thresholdRing.position.y = 0.15;
agentGroup.add(thresholdRing);

const thresholdMarker = new THREE.Mesh(
  new THREE.SphereGeometry(0.18, 16, 16),
  new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xff6b35, emissiveIntensity: 1.5 })
);
thresholdMarker.position.set(3.2, 0.15, 0);
agentGroup.add(thresholdMarker);

/* governance towers */
function buildTower(approach, angle) {
  const color = COLORS[approach];
  const group = new THREE.Group();
  const radius = 11;
  group.position.set(Math.sin(angle) * radius, 0, Math.cos(angle) * radius);
  group.lookAt(0, 0, 0);

  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(2.2, 2.5, 0.35, 6),
    new THREE.MeshStandardMaterial({ color: 0x12171f, emissive: color, emissiveIntensity: 0.15, metalness: 0.7, roughness: 0.4 })
  );
  platform.position.y = 0.17;
  group.add(platform);

  const bar = new THREE.Mesh(
    new THREE.BoxGeometry(1.6, 1, 1.6),
    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.4, metalness: 0.5, roughness: 0.35 })
  );
  bar.position.y = 1;
  bar.userData.isBar = true;
  group.add(bar);

  const ringGeo = new THREE.TorusGeometry(2, 0.04, 8, 32);
  const ringMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5 });
  const halo = new THREE.Mesh(ringGeo, ringMat);
  halo.rotation.x = Math.PI / 2;
  halo.position.y = 0.4;
  group.add(halo);

  const labelCanvas = document.createElement('canvas');
  labelCanvas.width = 512; labelCanvas.height = 128;
  const ctx = labelCanvas.getContext('2d');
  ctx.fillStyle = '#e9eef5';
  ctx.font = 'bold 36px IBM Plex Mono, monospace';
  ctx.textAlign = 'center';
  ctx.fillText(LABELS[approach], 256, 72);
  const labelTex = new THREE.CanvasTexture(labelCanvas);
  const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: labelTex, transparent: true }));
  label.scale.set(5, 1.25, 1);
  label.position.y = 4.2;
  group.add(label);

  group.userData.approach = approach;
  group.userData.bar = bar;
  group.userData.halo = halo;
  clickable.push(group);
  towerGroups.set(approach, group);
  scene.add(group);
  return group;
}

APPROACHES.forEach((a, i) => buildTower(a, (i / APPROACHES.length) * Math.PI * 2 + Math.PI / 6));

/* scenario orbs */
function buildScenarios() {
  SCENARIO_META.forEach((meta, i) => {
    const cls = meta.cls;
    const color = CLASS_COLORS[cls];
    const ringR = cls === 'benign' ? 7.5 : cls === 'adv' ? 9.5 : 8.8;
    const angle = (i / SCENARIO_META.length) * Math.PI * 2 - Math.PI / 2;
    const y = cls === 'adv' ? 2.8 : cls === 'amb' ? 2.2 : 1.6;

    const group = new THREE.Group();
    group.position.set(Math.cos(angle) * ringR, y, Math.sin(angle) * ringR);

    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.55, 24, 24),
      new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.55,
        roughness: 0.25, metalness: 0.6,
      })
    );
    group.add(orb);

    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(0.85, 16, 16),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.12 })
    );
    group.add(glow);

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.7, 0.03, 8, 24),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.6 })
    );
    group.rotation.x = Math.PI / 2;
    group.add(ring);

    group.userData = { type: 'scenario', scenarioId: meta.id, meta, orb, glow, ring, baseY: y };
    clickable.push(group);
    scenarioMeshes.set(meta.id, group);
    scene.add(group);
  });
}
buildScenarios();

/* particle pool for beam effects */
const particleGeo = new THREE.BufferGeometry();
const particleCount = 400;
const particlePositions = new Float32Array(particleCount * 3);
particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
const particleMat = new THREE.PointsMaterial({ color: 0xff6b35, size: 0.15, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending });
const particles = new THREE.Points(particleGeo, particleMat);
particles.visible = false;
scene.add(particles);

let activeParticles = [];

function spawnBeam(from, to, color, duration = 1200) {
  const count = 30;
  const pts = [];
  for (let i = 0; i < count; i++) {
    pts.push({
      t: i / count,
      speed: 0.008 + Math.random() * 0.012,
      offset: Math.random(),
      from: from.clone(),
      to: to.clone(),
      color,
      life: duration,
      born: performance.now(),
    });
  }
  activeParticles.push(...pts);

  const lineGeo = new THREE.BufferGeometry().setFromPoints([from, to]);
  const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({
    color, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending,
  }));
  scene.add(line);
  beamMeshes.push({ mesh: line, born: performance.now(), life: duration });
}

/* ---------- HUD helpers ---------- */
function setStatus(state, text) {
  const dot = $('statusDot');
  dot.className = 'dot' + (state === 'live' ? ' live' : state === 'busy' ? ' busy' : '');
  $('statusText').textContent = text;
}

function classOf(id) {
  if (id.startsWith('benign')) return 'benign';
  if (id.startsWith('adv')) return 'adv';
  return 'amb';
}

function renderMode(mode) {
  const el = $('judgeMode');
  if (mode && mode.startsWith('live')) {
    el.textContent = 'live · ' + (mode.split(':')[1] || 'model');
    el.className = 'modebadge live';
  } else {
    el.textContent = 'simulated';
    el.className = 'modebadge sim';
  }
}

function setSliderFill() {
  const el = $('threshold');
  el.style.setProperty('--fill', ((el.value - el.min) / (el.max - el.min)) * 100 + '%');
}

function updateThresholdRing(thr) {
  const t = (thr - 0.3) / 1.0;
  const angle = t * Math.PI * 1.8 - Math.PI * 0.9;
  thresholdMarker.position.set(Math.cos(angle) * 3.2, 0.15, Math.sin(angle) * 3.2);
  thresholdRing.material.emissiveIntensity = 0.4 + t * 0.8;
}

function updateTowers(metrics) {
  if (!metrics) return;
  APPROACHES.forEach((a) => {
    const g = towerGroups.get(a);
    if (!g) return;
    const m = metrics[a];
    const tripH = 1 + m.guardrail_trip_rate * 6;
    g.userData.bar.scale.y = tripH;
    g.userData.bar.position.y = tripH / 2 + 0.35;
    const intensity = focusedApproach && focusedApproach !== a ? 0.15 : 0.4 + m.recall * 0.5;
    g.userData.bar.material.emissiveIntensity = intensity;
    g.userData.halo.material.opacity = focusedApproach && focusedApproach !== a ? 0.15 : 0.35 + m.recall * 0.3;
    g.scale.setScalar(focusedApproach === a ? 1.12 : focusedApproach ? 0.88 : 1);
  });
}

function updateScenarioVisuals() {
  if (!latest) return;
  scenarioMeshes.forEach((group, id) => {
    const tasks = latest.tasks.filter(t => t.scenario_id === id);
    const anyWrong = tasks.some(t => !t.correct && t.approach !== 'no_guardrails');
    const anyBlock = tasks.some(t => t.blocked && t.approach !== 'no_guardrails');
    const isSelected = selectedScenario === id;
    const dimmed = focusedApproach && !tasks.some(t => t.approach === focusedApproach);

    group.userData.orb.material.emissiveIntensity = isSelected ? 1.2 : anyWrong ? 0.9 : 0.45;
    group.scale.setScalar(isSelected ? 1.35 : dimmed ? 0.75 : 1);
    group.userData.glow.material.opacity = isSelected ? 0.25 : 0.1;

    if (anyBlock && !isSelected) {
      group.userData.ring.material.opacity = 0.8;
    }
  });
}

function renderReadout(m) {
  const j = m.llm_judge;
  $('roRecall').textContent = pct(j.recall);
  $('roPrec').textContent = pct(j.precision);
  $('roInterv').textContent = pct(j.intervention_frequency);
  $('roCost').textContent = usd(j.cost_per_resolved_task_usd);
}

function renderTakeaway(m) {
  const r = m.rules_policy, j = m.llm_judge, n = m.no_guardrails;
  $('takeaway').innerHTML =
    `<b>Finding:</b> LLM judge catches <b>${pct(j.recall)}</b> of violations at this threshold. ` +
    `Rules: <b>${pct(r.recall)}</b> recall, <b>${(r.mean_policy_latency_s * 1000).toFixed(0)}ms</b> latency. ` +
    `No guardrails: <b>${pct(n.accuracy)}</b> accuracy.`;
}

function renderMetricBars(m) {
  const el = $('metricBars');
  const metrics = [
    { key: 'guardrail_trip_rate', label: 'Trip rate', fmt: pct },
    { key: 'mean_policy_latency_s', label: 'Latency', fmt: v => v.toFixed(3) + 's' },
    { key: 'intervention_frequency', label: 'Interventions', fmt: pct },
    { key: 'cost_per_resolved_task_usd', label: 'Cost/resolved', fmt: v => v == null ? 'n/a' : '$' + v.toFixed(5) },
  ];
  el.innerHTML = metrics.map(({ key, label, fmt }) => {
    const rows = APPROACHES.map(a => {
      const v = m[a][key];
      const max = key === 'mean_policy_latency_s' ? 3 : key.includes('cost') ? 0.01 : 1;
      const w = Math.min(100, ((typeof v === 'number' ? v : 0) / max) * 100);
      const hex = '#' + COLORS[a].toString(16).padStart(6, '0');
      return `<div class="mb-row"><span class="mb-name" style="color:${hex}">${LABELS[a]}</span>` +
        `<div class="mb-track"><div class="mb-fill" style="width:${w}%;background:${hex}"></div></div>` +
        `<span class="mb-val">${fmt(v)}</span></div>`;
    }).join('');
    return `<div class="mb-group"><div class="mb-label">${label}</div>${rows}</div>`;
  }).join('');
}

function renderDetail(scenarioId) {
  if (!latest || !scenarioId) {
    $('detailTitle').textContent = 'Select a scenario';
    $('detailPrompt').textContent = 'Click any glowing orb in the arena to inspect how each governance layer responds.';
    $('detailDecisions').innerHTML = '';
    return;
  }
  const meta = SCENARIO_META.find(s => s.id === scenarioId);
  const tasks = latest.tasks.filter(t => t.scenario_id === scenarioId);
  const sample = tasks[0];
  $('detailTitle').textContent = meta?.label || scenarioId;
  $('detailPrompt').textContent = sample?.prompt || '';
  $('detailDecisions').innerHTML = tasks
    .filter(t => focusedApproach ? t.approach === focusedApproach : true)
    .map(t => {
      const hex = '#' + COLORS[t.approach].toString(16).padStart(6, '0');
      return `<div class="dec-card ${t.correct ? 'ok' : 'bad'}">
        <div class="dec-head"><span style="color:${hex}">${LABELS[t.approach]}</span>
          <span class="dec-verdict ${t.blocked ? 'block' : 'allow'}">${t.blocked ? 'BLOCK' : 'ALLOW'}</span></div>
        <div class="dec-meta">${t.correct ? '✓ Correct' : '✗ Wrong'} · ${t.total_latency_s.toFixed(3)}s · $${t.total_cost_usd.toFixed(5)}</div>
        <div class="dec-reason">${t.reason}</div>
      </div>`;
    }).join('');

  const group = scenarioMeshes.get(scenarioId);
  if (group) {
    APPROACHES.forEach(a => {
      const task = tasks.find(t => t.approach === a);
      if (!task) return;
      const tower = towerGroups.get(a);
      spawnBeam(
        group.getWorldPosition(new THREE.Vector3()),
        tower.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 2, 0)),
        COLORS[a],
        800
      );
    });
  }
}

/* ---------- API ---------- */
async function runOnce(threshold, seed) {
  const r = await fetch(`/api/run?threshold=${threshold}&seed=${seed}`);
  if (!r.ok) throw new Error('run failed');
  return r.json();
}

async function fetchSweep(seed) {
  const r = await fetch(`/api/sweep?seed=${seed}`);
  if (!r.ok) throw new Error('sweep failed');
  return r.json();
}

function applyRun(data) {
  latest = data;
  renderReadout(data.metrics);
  renderTakeaway(data.metrics);
  renderMetricBars(data.metrics);
  updateTowers(data.metrics);
  updateScenarioVisuals();
  if (selectedScenario) renderDetail(selectedScenario);
  renderMode(data.judge_mode);
}

async function refresh({ resweep = false } = {}) {
  const thr = parseFloat($('threshold').value);
  const seed = parseInt($('seed').value || '7', 10);
  setStatus('busy', 'running…');
  $('runBtn').disabled = true;
  $('runIcon').outerHTML = '<span class="spin" id="runIcon"></span>';
  updateThresholdRing(thr);
  try {
    if (resweep || sweepData.length === 0) {
      const s = await fetchSweep(seed);
      sweepData = s.points;
      renderMode(s.judge_mode);
    }
    const data = await runOnce(thr, seed);
    applyRun(data);
    setStatus('live', 'live');
    pulseAgent();
  } catch {
    setStatus('', 'error');
    $('takeaway').textContent = 'Could not reach the benchmark API. Is the server running?';
  } finally {
    $('runBtn').disabled = false;
    $('runIcon').outerHTML = '<span id="runIcon">▶</span>';
  }
}

function pulseAgent() {
  agentCore.material.emissiveIntensity = 1.5;
  setTimeout(() => { agentCore.material.emissiveIntensity = 0.6; }, 400);
}

function selectScenario(id) {
  selectedScenario = id;
  updateScenarioVisuals();
  renderDetail(id);
  const group = scenarioMeshes.get(id);
  if (group) {
    controls.target.copy(group.position);
    controls.target.y = 1.5;
  }
}

function focusApproach(approach) {
  focusedApproach = focusedApproach === approach ? null : approach;
  updateTowers(latest?.metrics);
  updateScenarioVisuals();
  if (selectedScenario) renderDetail(selectedScenario);
  if (approach && towerGroups.has(approach)) {
    const t = towerGroups.get(approach);
    controls.target.copy(t.position);
    controls.target.y = 2;
  }
}

/* ---------- interaction ---------- */
const tooltip = $('tooltip');

function onPointerMove(e) {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(clickable, true);
  let found = null;
  for (const hit of hits) {
    let obj = hit.object;
    while (obj && !obj.userData.type && !obj.userData.approach) obj = obj.parent;
    if (obj?.userData.type === 'scenario') { found = obj; break; }
    if (obj?.userData.approach) { found = obj; break; }
  }
  renderer.domElement.style.cursor = found ? 'pointer' : 'grab';

  if (found?.userData.type === 'scenario') {
    const m = found.userData.meta;
    tooltip.hidden = false;
    tooltip.textContent = m.label + ' · ' + m.cls;
    tooltip.style.left = e.clientX + 14 + 'px';
    tooltip.style.top = e.clientY + 14 + 'px';
  } else if (found?.userData.approach) {
    tooltip.hidden = false;
    tooltip.textContent = LABELS[found.userData.approach] + ' · click to focus';
    tooltip.style.left = e.clientX + 14 + 'px';
    tooltip.style.top = e.clientY + 14 + 'px';
  } else {
    tooltip.hidden = true;
  }
}

function onClick(e) {
  if (e.target.closest('#hud')) return;
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(clickable, true);
  for (const hit of hits) {
    let obj = hit.object;
    while (obj && !obj.userData.type && !obj.userData.approach) obj = obj.parent;
    if (obj?.userData.type === 'scenario') {
      selectScenario(obj.userData.scenarioId);
      return;
    }
    if (obj?.userData.approach) {
      focusApproach(obj.userData.approach);
      return;
    }
  }
}

renderer.domElement.addEventListener('pointermove', onPointerMove);
renderer.domElement.addEventListener('click', onClick);

/* ---------- animation loop ---------- */
const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();

  agentCore.rotation.y = t * 0.35;
  agentCore.rotation.x = Math.sin(t * 0.2) * 0.15;
  agentWire.rotation.y = -t * 0.25;
  agentGlow.scale.setScalar(1 + Math.sin(t * 2) * 0.06);
  thresholdRing.rotation.z = t * 0.15;

  scenarioMeshes.forEach((group, id) => {
    const { orb, baseY } = group.userData;
    const phase = id.length * 0.7;
    group.position.y = baseY + Math.sin(t * 1.2 + phase) * 0.15;
    orb.rotation.y = t * 0.5;
    if (selectedScenario === id) {
      group.rotation.y = t * 0.4;
    }
  });

  towerGroups.forEach((g) => {
    g.userData.halo.rotation.z = t * 0.3;
  });

  /* particles along beams */
  const now = performance.now();
  activeParticles = activeParticles.filter(p => now - p.born < p.life);
  let idx = 0;
  for (const p of activeParticles) {
    p.t += p.speed;
    if (p.t > 1) p.t = 0;
    const pos = new THREE.Vector3().lerpVectors(p.from, p.to, p.t);
    if (idx < particleCount) {
      particlePositions[idx * 3] = pos.x;
      particlePositions[idx * 3 + 1] = pos.y;
      particlePositions[idx * 3 + 2] = pos.z;
      idx++;
    }
  }
  for (let i = idx; i < particleCount; i++) {
    particlePositions[i * 3] = 9999;
  }
  particleGeo.attributes.position.needsUpdate = true;
  particles.visible = idx > 0;

  /* expire beam lines */
  for (let i = beamMeshes.length - 1; i >= 0; i--) {
    const b = beamMeshes[i];
    const age = now - b.born;
    b.mesh.material.opacity = Math.max(0, 0.5 * (1 - age / b.life));
    if (age > b.life) {
      scene.remove(b.mesh);
      b.mesh.geometry.dispose();
      b.mesh.material.dispose();
      beamMeshes.splice(i, 1);
    }
  }

  controls.update();
  composer.render();
}

/* ---------- wiring ---------- */
$('threshold').addEventListener('input', () => {
  const thr = parseFloat($('threshold').value);
  $('thVal').textContent = thr.toFixed(2);
  setSliderFill();
  updateThresholdRing(thr);
  clearTimeout(debounce);
  debounce = setTimeout(() => refresh({ resweep: false }), 130);
});

$('seed').addEventListener('change', () => refresh({ resweep: true }));
$('runBtn').addEventListener('click', () => refresh({ resweep: true }));

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
  bloom.resolution.set(window.innerWidth, window.innerHeight);
});

setSliderFill();
updateThresholdRing(0.6);
animate();
refresh({ resweep: true });
