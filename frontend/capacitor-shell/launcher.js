(function () {
  'use strict';

  var STORAGE_KEY = 'kahani.serverUrl';
  var HEALTH_PATH = '/health';
  var PROBE_TIMEOUT_MS = 10000;

  function $(id) { return document.getElementById(id); }

  // ---------------------------------------------------------------------------
  // Storage: Capacitor Preferences (durable, native-backed) when available,
  // localStorage fallback for desktop testing. Dual-write so a Preferences
  // wipe doesn't lose the URL and vice-versa.
  // ---------------------------------------------------------------------------
  var storage = (function () {
    function prefs() {
      return window.Capacitor
        && window.Capacitor.Plugins
        && window.Capacitor.Plugins.Preferences;
    }

    async function get(key) {
      var p = prefs();
      if (p) {
        try {
          var r = await p.get({ key: key });
          if (r && r.value) return r.value;
        } catch (e) { /* fall through */ }
      }
      try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    async function set(key, value) {
      var p = prefs();
      if (p) {
        try { await p.set({ key: key, value: value }); } catch (e) {}
      }
      try { localStorage.setItem(key, value); } catch (e) {}
    }

    async function remove(key) {
      var p = prefs();
      if (p) {
        try { await p.remove({ key: key }); } catch (e) {}
      }
      try { localStorage.removeItem(key); } catch (e) {}
    }

    // One-time migration: if Preferences has no value but localStorage does,
    // copy it over so existing installs aren't disconnected after plugin add.
    async function migrate(key) {
      var p = prefs();
      if (!p) return;
      try {
        var r = await p.get({ key: key });
        if (r && r.value) return;
        var local = null;
        try { local = localStorage.getItem(key); } catch (e) {}
        if (local) await p.set({ key: key, value: local });
      } catch (e) {}
    }

    return { get: get, set: set, remove: remove, migrate: migrate };
  })();

  // ---------------------------------------------------------------------------
  // UI helpers
  // ---------------------------------------------------------------------------
  function show(screenId, loaderMsg) {
    var screens = document.querySelectorAll('.screen');
    for (var i = 0; i < screens.length; i++) screens[i].classList.add('hidden');
    $(screenId).classList.remove('hidden');
    if (screenId === 'loader' && loaderMsg) $('loader-msg').textContent = loaderMsg;
  }

  function showError(msg) {
    var e = $('error');
    e.textContent = msg;
    e.classList.remove('hidden');
  }

  function clearError() {
    $('error').classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // URL handling
  // ---------------------------------------------------------------------------
  function normalize(input) {
    var s = (input || '').trim();
    if (!s) return null;
    if (!/^https?:\/\//i.test(s)) s = 'https://' + s;
    s = s.replace(/\/+$/, '');
    try {
      var u = new URL(s);
      if (!u.host) return null;
      return s;
    } catch (e) {
      return null;
    }
  }

  function timeout(ms) {
    return new Promise(function (_, reject) {
      setTimeout(function () { reject(new Error('Request timed out')); }, ms);
    });
  }

  async function probe(url) {
    var endpoint = url + HEALTH_PATH;
    var nativeHttp = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.CapacitorHttp;

    try {
      var body;
      if (nativeHttp) {
        var resp = await Promise.race([
          nativeHttp.request({
            url: endpoint,
            method: 'GET',
            connectTimeout: PROBE_TIMEOUT_MS,
            readTimeout: PROBE_TIMEOUT_MS,
            headers: { Accept: 'application/json' },
          }),
          timeout(PROBE_TIMEOUT_MS + 500),
        ]);
        if (!resp || resp.status !== 200) {
          return { ok: false, reason: 'Server returned ' + (resp && resp.status ? resp.status : 'no response') };
        }
        body = typeof resp.data === 'string' ? JSON.parse(resp.data) : resp.data;
      } else {
        var fResp = await Promise.race([
          fetch(endpoint, { method: 'GET', headers: { Accept: 'application/json' } }),
          timeout(PROBE_TIMEOUT_MS),
        ]);
        if (!fResp.ok) return { ok: false, reason: 'Server returned ' + fResp.status };
        body = await fResp.json();
      }

      if (!body || typeof body !== 'object') {
        return { ok: false, reason: 'Unexpected response from server' };
      }
      if (body.status !== 'healthy') {
        return { ok: false, reason: 'Server is not healthy' };
      }
      if (typeof body.app !== 'string' || body.app.toLowerCase().indexOf('kahani') === -1) {
        return { ok: false, reason: "This doesn't look like a Kahani server" };
      }
      return { ok: true };
    } catch (e) {
      var msg = (e && e.message) ? e.message : 'Network error';
      return { ok: false, reason: msg };
    }
  }

  function navigate(url) {
    window.location.replace(url);
  }

  // ---------------------------------------------------------------------------
  // Form handler
  // ---------------------------------------------------------------------------
  $('connect-form').addEventListener('submit', async function (evt) {
    evt.preventDefault();
    clearError();
    var raw = $('url-input').value;
    var url = normalize(raw);
    if (!url) {
      showError('Please enter a valid URL');
      return;
    }
    var btn = $('connect-btn');
    btn.disabled = true;
    btn.textContent = 'Connecting…';

    var result = await probe(url);
    if (result.ok) {
      await storage.set(STORAGE_KEY, url);
      navigate(url);
    } else {
      btn.disabled = false;
      btn.textContent = 'Connect';
      showError("Couldn't connect: " + result.reason);
    }
  });

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------
  (async function boot() {
    // If main app set ?reset=1 before navigating back, clear stored URL and
    // show the form. Used by the Disconnect button in settings.
    var params = new URLSearchParams(window.location.search);
    if (params.get('reset') === '1') {
      await storage.remove(STORAGE_KEY);
      show('form-screen');
      return;
    }

    await storage.migrate(STORAGE_KEY);
    var stored = await storage.get(STORAGE_KEY);

    if (!stored) {
      show('form-screen');
      return;
    }

    show('loader', 'Connecting to ' + stored.replace(/^https?:\/\//, '') + '…');
    var result = await probe(stored);
    if (result.ok) {
      navigate(stored);
    } else {
      $('url-input').value = stored;
      show('form-screen');
      showError("Couldn't reach " + stored + ': ' + result.reason);
    }
  })();
})();
