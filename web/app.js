'use strict';

const COLORS = { no_guardrails: '#8b96a5', rules_policy: '#3fb950', llm_judge: '#ff6b35' };
const LABELS = { no_guardrails: 'No Guardrails', rules_policy: 'Rules Policy', llm_judge: 'LLM Judge' };
const APPROACHES = ['no_guardrails', 'rules_policy', 'llm_judge'];

const $ = (id) => document.getElementById(id);
const pct = (x) => (x * 100).toFixed(1) + '%';
const usd = (x) => x == null ? 'n/a' : '$' + x.toFixed(5);

let charts = {};
let latest = null;          // most recent single run
let sweepData = [];         // [{threshold, recall, precision, trip}]
let filterClass = 'all';
let filterApproach = 'all';

/* ---------- status ---------- */
function setStatus(state, text) {
  const dot = $('statusDot');
  dot.className = 'dot' + (state === 'live' ? ' live' : state === 'busy' ? ' busy' : '');
  $('statusText').textContent = text;
}

/* ---------- api ---------- */
async function runOnce(threshold, seed) {
  const r = await fetch(`/api/run?threshold=${threshold}&seed=${seed}`);
  if (!r.ok) throw new Error('run failed');
  return r.json();
}

function classOf(id) {
  if (id.startsWith('benign')) return 'benign';
  if (id.startsWith('adv')) return 'adv';
  return 'amb';
}

/* ---------- number animation ---------- */
function animateText(el, to, fmt, ms = 600) {
  const start = performance.now();
  const from = el._cur ?? to;
  el._cur = to;
  function step(now) {
    const t = Math.min(1, (now - start) / ms);
    const e = 1 - Math.pow(1 - t, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ---------- render ---------- */
function renderCards(m, animate) {
  const cards = $('cards');
  const order = ['guardrail_trip_rate', 'mean_policy_latency_s', 'intervention_frequency', 'cost_per_resolved_task_usd'];
  const titles = {
    guardrail_trip_rate: 'Guardrail Trip Rate', mean_policy_latency_s: 'Policy Latency',
    intervention_frequency: 'Intervention Freq.', cost_per_resolved_task_usd: 'Cost / Resolved'
  };
  const fmt = {
    guardrail_trip_rate: pct, intervention_frequency: pct,
    mean_policy_latency_s: (v) => v.toFixed(3) + 's',
    cost_per_resolved_task_usd: (v) => v == null ? 'n/a' : '$' + v.toFixed(5)
  };
  cards.innerHTML = '';
  order.forEach(metric => {
    const c = document.createElement('div'); c.className = 'card';
    let html = `<h4>${titles[metric]}</h4>`;
    APPROACHES.forEach(a => {
      html += `<div class="row"><span class="name" style="color:${COLORS[a]}">${LABELS[a]}</span>` +
        `<span class="val" data-a="${a}" data-m="${metric}">—</span></div>`;
    });
    c.innerHTML = html; cards.appendChild(c);
  });
  cards.querySelectorAll('.val').forEach(el => {
    const v = m[el.dataset.a][el.dataset.m];
    const f = fmt[el.dataset.m];
    if (typeof v === 'number' && animate && el.dataset.m !== 'cost_per_resolved_task_usd') {
      animateText(el, v, f);
    } else {
      el.textContent = f(v);
    }
  });
}

function renderTakeaway(m) {
  const r = m.rules_policy, j = m.llm_judge, n = m.no_guardrails;
  $('takeaway').innerHTML =
    `<b>Finding:</b> At this operating point the LLM judge catches <b>${pct(j.recall)}</b> of violations ` +
    `(precision <b>${pct(j.precision)}</b>), adding <b>${j.mean_policy_latency_s.toFixed(2)}s</b> and routing ` +
    `<b>${pct(j.intervention_frequency)}</b> of tasks to a human at <b>${usd(j.cost_per_resolved_task_usd)}</b>/resolved task. ` +
    `The deterministic rules policy matches detection here for <b>${pct(r.recall)}</b> recall at just ` +
    `<b>${(r.mean_policy_latency_s * 1000).toFixed(0)}ms</b> and <b>${usd(r.cost_per_resolved_task_usd)}</b> with zero interventions — ` +
    `the judge only earns its cost where policy is too subtle to encode in rules. Doing nothing resolves just <b>${pct(n.accuracy)}</b> correctly.`;
}

function renderReadout(m) {
  const j = m.llm_judge;
  animateText($('roRecall'), j.recall, pct);
  animateText($('roPrec'), j.precision, pct);
  animateText($('roInterv'), j.intervention_frequency, pct);
  $('roCost').textContent = usd(j.cost_per_resolved_task_usd);
  [$('roRecall'), $('roPrec'), $('roInterv'), $('roCost')].forEach(e => e.classList.remove('skeleton'));

  let v;
  if (j.recall >= 0.99) v = `Tight enough to catch <b>every</b> violation in the suite. Loosen it and watch recall fall.`;
  else if (j.recall >= 0.6) v = `Now <b>${pct(1 - j.recall)}</b> of violations slip through. This is where a too-permissive judge quietly fails.`;
  else v = `Dangerously loose — <b>${pct(1 - j.recall)}</b> of violations are allowed. Detection has collapsed.`;
  if (j.precision < 0.99 && j.precision > 0) v += ` Precision dropped to <b>${pct(j.precision)}</b>: benign work is being over-blocked.`;
  $('verdict').innerHTML = v;
}

function renderTrace() {
  if (!latest) return;
  const tb = document.querySelector('#traceTable tbody');
  tb.innerHTML = '';
  latest.tasks
    .filter(t => filterApproach === 'all' ? t.approach !== 'no_guardrails' : t.approach === filterApproach)
    .filter(t => filterClass === 'all' || classOf(t.scenario_id) === filterClass)
    .forEach(t => {
      const cls = classOf(t.scenario_id);
      const clabel = { benign: 'benign', adv: 'adversarial', amb: 'ambiguous' }[cls];
      const tr = document.createElement('tr');
      tr.innerHTML =
        `<td>${t.scenario_id}</td>` +
        `<td><span class="classtag ${cls}">${clabel}</span></td>` +
        `<td style="color:${COLORS[t.approach]}">${LABELS[t.approach]}</td>` +
        `<td class="${t.blocked ? 'block' : 'allow'}">${t.blocked ? 'BLOCK' : 'allow'}</td>` +
        `<td>${t.correct ? '<span class="tag ok">✓</span>' : '<span class="tag no">✗</span>'}</td>` +
        `<td>${t.total_latency_s.toFixed(3)}s</td>` +
        `<td>$${t.total_cost_usd.toFixed(5)}</td>` +
        `<td style="color:var(--muted)">${t.reason}</td>` +
        `<td><span class="prompt">${t.prompt}</span></td>`;
      tb.appendChild(tr);
    });
}

/* ---------- charts ---------- */
const gridClr = '#1b212b', tickClr = '#8b96a5';
const thresholdMarker = {
  id: 'thresholdMarker',
  afterDraw(chart) {
    const thr = chart.$thr;
    if (thr == null) return;
    const x = chart.scales.x.getPixelForValue(thr);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath(); ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(255,255,255,.55)';
    ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = '#e9eef5'; ctx.font = '11px IBM Plex Mono';
    ctx.textAlign = Math.abs(x - chart.chartArea.right) < 60 ? 'right' : 'left';
    ctx.fillText('  you are here', x, top + 12);
    ctx.restore();
  }
};

function buildSweepChart() {
  charts.sweep = new Chart($('sweep'), {
    type: 'line',
    data: {
      datasets: [
        { label: 'Recall (violations caught)', borderColor: '#ff6b35', backgroundColor: 'rgba(255,107,53,.12)', fill: true, tension: .25, pointRadius: 0, data: [] },
        { label: 'Precision', borderColor: '#58a6ff', tension: .25, pointRadius: 0, data: [] },
        { label: 'Trip rate', borderColor: '#8b96a5', borderDash: [4, 3], tension: .25, pointRadius: 0, data: [] },
      ]
    },
    options: {
      responsive: true, interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#e9eef5', font: { family: 'IBM Plex Mono', size: 11 }, usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { title: (i) => 'threshold ' + i[0].parsed.x.toFixed(2), label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(0)}%` } }
      },
      scales: {
        x: { type: 'linear', min: 0.3, max: 1.3, title: { display: true, text: 'risk block threshold', color: tickClr }, ticks: { color: tickClr, stepSize: 0.1 }, grid: { color: gridClr } },
        y: { min: -3, max: 105, title: { display: true, text: '%', color: tickClr }, ticks: { color: tickClr, callback: (v) => v + '%' }, grid: { color: gridClr } }
      }
    },
    plugins: [thresholdMarker]
  });
}

function updateSweepChart(thr) {
  const c = charts.sweep;
  c.data.datasets[0].data = sweepData.map(d => ({ x: d.threshold, y: d.recall * 100 }));
  c.data.datasets[1].data = sweepData.map(d => ({ x: d.threshold, y: d.precision * 100 }));
  c.data.datasets[2].data = sweepData.map(d => ({ x: d.threshold, y: d.trip * 100 }));
  c.$thr = thr;
  c.update('none');
}

function buildScatter() {
  charts.scatter = new Chart($('scatter'), {
    type: 'scatter',
    data: { datasets: [] },
    options: {
      plugins: { legend: { labels: { color: '#e9eef5', font: { family: 'IBM Plex Mono', size: 11 }, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(0)}% recall, ${c.parsed.x.toFixed(3)}s` } } },
      scales: {
        x: { title: { display: true, text: 'latency overhead (s)', color: tickClr }, ticks: { color: tickClr }, grid: { color: gridClr } },
        y: { min: -5, max: 105, title: { display: true, text: 'recall (%)', color: tickClr }, ticks: { color: tickClr }, grid: { color: gridClr } }
      }
    }
  });
}

function updateScatter(m) {
  charts.scatter.data.datasets = APPROACHES.map(a => ({
    label: LABELS[a], backgroundColor: COLORS[a], pointRadius: 9, pointHoverRadius: 12,
    data: [{ x: m[a].mean_policy_latency_s, y: m[a].recall * 100 }]
  }));
  charts.scatter.update('none');
}

function buildBars() {
  charts.bars = new Chart($('bars'), {
    type: 'bar',
    data: { labels: APPROACHES.map(a => LABELS[a]), datasets: [{ data: [], backgroundColor: APPROACHES.map(a => COLORS[a]), borderRadius: 6 }] },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => '$' + c.parsed.y.toFixed(5) } } },
      scales: { x: { ticks: { color: tickClr }, grid: { display: false } },
        y: { ticks: { color: tickClr, callback: (v) => '$' + v.toFixed(4) }, grid: { color: gridClr } } }
    }
  });
}

function updateBars(m) {
  charts.bars.data.datasets[0].data = APPROACHES.map(a => m[a].cost_per_resolved_task_usd || 0);
  charts.bars.update('none');
}

/* ---------- orchestration ---------- */
function applyRun(data, animate) {
  latest = data;
  renderCards(data.metrics, animate);
  renderTakeaway(data.metrics);
  renderReadout(data.metrics);
  updateScatter(data.metrics);
  updateBars(data.metrics);
  renderTrace();
  $('mScenarios').textContent = data.scenario_count;
  $('mRuns').textContent = data.tasks.length;
  $('footMeta').textContent = `seed ${data.config.judge_seed} · threshold ${data.config.judge_threshold.toFixed(2)} · ${data.tasks.length} runs`;
}

async function sweep(seed) {
  const thresholds = [];
  for (let t = 0.30; t <= 1.301; t += 0.05) thresholds.push(Math.round(t * 100) / 100);
  const runs = await Promise.all(thresholds.map(t => runOnce(t, seed)));
  sweepData = runs.map((r, i) => ({
    threshold: thresholds[i],
    recall: r.metrics.llm_judge.recall,
    precision: r.metrics.llm_judge.precision,
    trip: r.metrics.llm_judge.guardrail_trip_rate,
  }));
}

let debounce;
async function refresh({ resweep = false, animate = false } = {}) {
  const thr = parseFloat($('threshold').value);
  const seed = parseInt($('seed').value || '7', 10);
  setStatus('busy', 'running…');
  $('runBtn').disabled = true;
  $('runIcon').outerHTML = '<span class="spin" id="runIcon"></span>';
  try {
    const tasks = [runOnce(thr, seed)];
    if (resweep || sweepData.length === 0) tasks.push(sweep(seed));
    const [data] = await Promise.all(tasks);
    applyRun(data, animate);
    updateSweepChart(thr);
    setStatus('live', 'live');
  } catch (e) {
    setStatus('', 'error');
    $('takeaway').textContent = 'Could not reach the benchmark API. Is the server running?';
  } finally {
    $('runBtn').disabled = false;
    $('runIcon').outerHTML = '<span id="runIcon">▶</span>';
  }
}

/* ---------- wiring ---------- */
function setSliderFill() {
  const el = $('threshold');
  const f = ((el.value - el.min) / (el.max - el.min)) * 100;
  el.style.setProperty('--fill', f + '%');
}

$('threshold').addEventListener('input', () => {
  $('thVal').textContent = parseFloat($('threshold').value).toFixed(2);
  setSliderFill();
  updateSweepChart(parseFloat($('threshold').value));   // instant marker move
  clearTimeout(debounce);
  debounce = setTimeout(() => refresh({ resweep: false, animate: false }), 130);
});

$('seed').addEventListener('change', () => refresh({ resweep: true, animate: false }));
$('runBtn').addEventListener('click', () => refresh({ resweep: true, animate: true }));

document.querySelectorAll('.chip[data-f]').forEach(c => c.addEventListener('click', () => {
  document.querySelectorAll('.chip[data-f]').forEach(x => x.classList.remove('on'));
  c.classList.add('on'); filterClass = c.dataset.f; renderTrace();
}));
document.querySelectorAll('.chip[data-a]').forEach(c => c.addEventListener('click', () => {
  document.querySelectorAll('.chip[data-a]').forEach(x => x.classList.remove('on'));
  c.classList.add('on'); filterApproach = c.dataset.a; renderTrace();
}));

/* ---------- boot ---------- */
window.addEventListener('DOMContentLoaded', () => {
  buildSweepChart(); buildScatter(); buildBars();
  setSliderFill();
  refresh({ resweep: true, animate: true });
});
