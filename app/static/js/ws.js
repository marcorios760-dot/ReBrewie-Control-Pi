/**
 * ws.js – WebSocket client shared by all pages.
 *
 * Opens a persistent connection to /ws and dispatches incoming state
 * frames to all handlers registered in window._wsHandlers[].
 * Also updates the navbar connection indicator.
 */
(function () {
  'use strict';

  let ws = null;
  let reconnectDelay = 2000;

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = function () {
      reconnectDelay = 2000;
      setConnected(true);
    };

    ws.onclose = function () {
      setConnected(false);
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
    };

    ws.onerror = function () {
      ws.close();
    };

    ws.onmessage = function (ev) {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }

      // Dispatch to all registered handlers
      const handlers = window._wsHandlers || [];
      handlers.forEach(function (fn) {
        try { fn(msg); } catch (e) { console.error('WS handler error', e); }
      });

      // Update connection dot
      if (msg.data && msg.data.connected !== undefined) {
        setConnected(msg.data.connected);
      }
    };
  }

  function setConnected(yes) {
    const dot   = document.getElementById('conn-dot');
    const label = document.getElementById('conn-label');
    if (dot) {
      dot.className = 'dot ' + (yes ? 'dot-green' : 'dot-red');
    }
    if (label) {
      label.textContent = yes ? 'Connected' : 'Disconnected';
    }
  }

  // Expose send helper for pages that need it
  window._wsSend = function (obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  };

  connect();
})();
