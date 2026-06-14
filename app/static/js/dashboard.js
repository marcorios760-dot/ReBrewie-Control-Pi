/**
 * dashboard.js – live state updates and controls for the main dashboard.
 */
(function () {
  'use strict';

  // ── Load recipe list into select ─────────────────────────────────────────
  async function loadRecipes() {
    try {
      const r = await fetch('/api/recipes');
      const data = await r.json();
      const sel = document.getElementById('recipe-select');
      if (!sel) return;
      (data.recipes || []).forEach(function (rec) {
        const opt = document.createElement('option');
        opt.value = rec.id;
        opt.textContent = rec.name + (rec.style ? ' (' + rec.style + ')' : '');
        sel.appendChild(opt);
      });
    } catch (e) { /* network not ready */ }
  }

  window.setRecipe = function (id) {
    window._selectedRecipeId = id || null;
  };

  // ── Brew control API calls ────────────────────────────────────────────────
  window.brewControl = async function (action) {
    let url = '/api/control/' + action;
    let body = {};
    if (action === 'start') {
      body.recipe_id = window._selectedRecipeId || null;
    }
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        alert('Error: ' + (data.detail || JSON.stringify(data)));
      }
    } catch (e) {
      alert('Request failed: ' + e);
    }
  };

  // ── WebSocket state handler ───────────────────────────────────────────────
  function updateDashboard(msg) {
    const s = (msg && msg.data) ? msg.data : msg;
    if (!s || typeof s !== 'object') return;

    function setText(id, val) {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    }
    function setWidth(id, pct) {
      const el = document.getElementById(id);
      if (el) el.style.width = Math.min(100, Math.max(0, pct)) + '%';
    }

    // Temperatures
    setText('mash-temp-actual', (s.mash_temp_actual || 0).toFixed(1) + '°C');
    setText('mash-temp-target', (s.mash_temp_target || 0).toFixed(1) + '°C');
    setText('boil-temp-actual', (s.boil_temp_actual || 0).toFixed(1) + '°C');
    setText('boil-temp-target', (s.boil_temp_target || 0).toFixed(1) + '°C');
    setWidth('mash-temp-bar', (s.mash_temp_actual || 0));
    setWidth('boil-temp-bar', (s.boil_temp_actual || 0));

    // Weight / pressure
    setText('weight-kg', (s.weight_kg || 0).toFixed(2) + ' kg');
    setText('pressure',  (s.pressure_mbar || 0).toFixed(1) + ' mbar');

    // Step
    setText('step-name', s.step_name || '—');
    setText('step-cur',  (s.current_step || 0) + 1);
    setText('step-tot',  s.total_steps || '—');
    setText('step-time', (s.step_elapsed_s || 0) + 's / ' + (s.step_duration_s || 0) + 's');
    const stepPct = s.step_duration_s > 0
      ? (s.step_elapsed_s / s.step_duration_s * 100) : 0;
    setWidth('step-bar', stepPct);

    // Status badge
    const badge = document.querySelector('.badge');
    if (badge) {
      badge.textContent = (s.status || 'idle').toUpperCase();
      badge.className = 'badge badge-' + (s.status || 'idle');
    }

    // Actuator indicators
    const actuatorMap = {
      'water-inlet':   s.water_inlet,
      'mash-inlet':    s.mash_inlet,
      'boil-inlet':    s.boil_inlet,
      'cool-inlet':    s.cool_inlet,
      'cool-valve':    s.cool_valve,
      'outlet-valve':  s.outlet_valve,
      'mash-return':   s.mash_return,
      'boil-return':   s.boil_return,
      'mash-pump':     s.mash_pump,
      'boil-pump':     s.boil_pump,
      'fan':           s.fan,
      'hop-1':         s.hop1,
      'hop-2':         s.hop2,
      'hop-3':         s.hop3,
      'hop-4':         s.hop4,
    };
    Object.entries(actuatorMap).forEach(function ([key, active]) {
      const el = document.getElementById('act-' + key);
      if (!el) return;
      el.classList.toggle('actuator-on', !!active);
      const dot = el.querySelector('.actuator-dot');
      if (dot) {
        dot.className = 'actuator-dot ' + (active ? 'dot-green' : 'dot-grey');
      }
    });

    // Live log
    appendLog(s);
  }

  let _lastLogLen = 0;
  async function appendLog(state) {
    const box = document.getElementById('log-box');
    if (!box) return;
    try {
      const r = await fetch('/api/log?n=200');
      const data = await r.json();
      const lines = data.log || [];
      if (lines.length === _lastLogLen) return;
      _lastLogLen = lines.length;
      box.innerHTML = '';
      lines.slice().reverse().forEach(function (line) {
        const d = document.createElement('div');
        d.textContent = line;
        box.appendChild(d);
      });
    } catch { /* ignore */ }
  }

  // Register handler
  window._wsHandlers = window._wsHandlers || [];
  window._wsHandlers.push(updateDashboard);

  // Initial data fetch in case WS hasn't fired yet
  fetch('/api/status')
    .then(r => r.json())
    .then(s => updateDashboard({ data: s }))
    .catch(() => {});

  loadRecipes();
})();
