// client.js — TV Launcher Remote Controller

// ─── ÉTAT GLOBAL ──────────────────────────────────────────────────────────────

const activeModifiers = { ctrl: false, alt: false, super: false };

let isEditMode     = false;
let mouseMode      = 'trackpad';
let mouseSpeed     = 8;
let cachedApps     = [];
let statusInterval = null;

// Hooks gyroscope (assignés dans initGyroscope)
let startGyroscope = () => {};
let stopGyroscope  = () => {};

const CONFIG = {
  apiBase:          '',
  mousePollRateMs:  45,
  gyroPollRateMs:   40,
  joystickDeadzone: 5,
  joystickMaxDist:  60,
};

// ─── INITIALISATION ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initApps();
  initKeyboard();
  initJoystick();
  initMouseButtons();
  initGyroscope();
  initUrlLauncher();
  initAppsCMS();
  initMonitor();
  initPowerModal();
  initUpdateButton();

  checkStatus();
  statusInterval = setInterval(checkStatus, 5000);
});

// ─── NAVIGATION (ONGLETS) ─────────────────────────────────────────────────────

function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const panels   = document.querySelectorAll('.tab-panel');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetId = item.getAttribute('data-target');
      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      panels.forEach(p => p.classList.toggle('active', p.id === targetId));
      vibrate(10);
    });
  });
}

// ─── HELPERS API ET CONNEXION ─────────────────────────────────────────────────

async function apiPost(endpoint, data = {}) {
  try {
    const response = await fetch(`${CONFIG.apiBase}${endpoint}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(data),
    });
    updateConnectionStatus(response.ok);
    if (!response.ok) {
      console.error(`API Error: ${response.statusText}`);
      return null;
    }
    return await response.json();
  } catch (error) {
    console.error('Fetch Error:', error);
    updateConnectionStatus(false);
    return null;
  }
}

function updateConnectionStatus(isConnected) {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  dot.className    = `status-dot ${isConnected ? 'online' : 'offline'}`;
  text.textContent = isConnected ? 'Connecté à tv.local' : 'Déconnecté';
}

async function checkStatus() {
  try {
    const response = await fetch(`${CONFIG.apiBase}/api/status`);
    updateConnectionStatus(response.ok);
  } catch {
    updateConnectionStatus(false);
  }
}

function vibrate(ms) {
  if (navigator.vibrate) navigator.vibrate(ms);
}

// ─── PANEL 1 : LANCEUR D'APPLICATIONS ────────────────────────────────────────

async function initApps() {
  const grid       = document.getElementById('apps-grid');
  const countBadge = document.getElementById('apps-count');

  try {
    const response = await fetch(`${CONFIG.apiBase}/api/apps`);
    if (!response.ok) throw new Error("Impossible de charger la liste des apps");
    const data = await response.json();

    cachedApps = data.apps || [];
    grid.innerHTML   = '';
    countBadge.textContent = cachedApps.length;

    if (cachedApps.length === 0) {
      grid.innerHTML = '<p class="loading-placeholder">Aucune application configurée.</p>';
      return;
    }

    grid.classList.toggle('edit-mode', isEditMode);

    cachedApps.forEach((app, index) => {
      const btn = document.createElement('div');
      btn.className = 'app-item-btn';

      const iconWrap = document.createElement('div');
      iconWrap.className = 'app-icon-wrapper';

      const img = document.createElement('img');
      img.src    = app.icon ? `/${app.icon}` : '/icons/firefox.png';
      img.onerror = () => { img.src = '/icons/firefox.png'; };
      iconWrap.appendChild(img);

      const name = document.createElement('span');
      name.className   = 'app-name';
      name.textContent = app.name;

      btn.appendChild(iconWrap);
      btn.appendChild(name);

      if (isEditMode) {
        // Bouton supprimer
        const delBtn = document.createElement('div');
        delBtn.className = 'btn-delete-app';
        delBtn.innerHTML = '✕';
        delBtn.addEventListener('click', e => { e.stopPropagation(); deleteApp(app.id, app.name); });
        btn.appendChild(delBtn);

        // Bouton éditer
        const editBtn = document.createElement('div');
        editBtn.className = 'btn-edit-app';
        editBtn.innerHTML = '✏️';
        editBtn.addEventListener('click', e => { e.stopPropagation(); openAppEditModal(app); });
        btn.appendChild(editBtn);

        // Boutons de réorganisation
        const reorderWrap = document.createElement('div');
        reorderWrap.className = 'app-reorder-actions';

        const leftArrow = document.createElement('div');
        leftArrow.className = 'btn-reorder';
        leftArrow.innerHTML = '◀';
        leftArrow.addEventListener('click', e => { e.stopPropagation(); moveAppInList(index, -1); });

        const rightArrow = document.createElement('div');
        rightArrow.className = 'btn-reorder';
        rightArrow.innerHTML = '▶';
        rightArrow.addEventListener('click', e => { e.stopPropagation(); moveAppInList(index, 1); });

        reorderWrap.appendChild(leftArrow);
        reorderWrap.appendChild(rightArrow);
        btn.appendChild(reorderWrap);
      } else {
        btn.addEventListener('click', () => { vibrate(25); launchApp(app.id); });
      }

      grid.appendChild(btn);
    });
  } catch (e) {
    console.error(e);
    grid.innerHTML = '<p class="loading-placeholder">Erreur de chargement. Vérifiez la connexion.</p>';
  }
}

function launchApp(appId) {
  apiPost('/api/launch', { id: appId });
}

function initUrlLauncher() {
  const urlInput      = document.getElementById('custom-url-input');
  const browserSelect = document.getElementById('custom-url-browser');
  const openBtn       = document.getElementById('btn-open-url');

  openBtn.addEventListener('click', () => {
    const rawUrl = urlInput.value.trim();
    if (!rawUrl) return;
    vibrate(30);
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `http://${rawUrl}`;
    apiPost('/api/launch-url', { url, browser: browserSelect.value });
  });
}

// ─── PANEL 2 : CLAVIER ────────────────────────────────────────────────────────

function initKeyboard() {
  const textInput      = document.getElementById('keyboard-text-input');
  const sendBtn        = document.getElementById('btn-send-text');
  const modifierBtns   = document.querySelectorAll('.btn-modifier');
  const virtualEnterBtn = document.getElementById('btn-virtual-enter');

  const sendText = () => {
    const text = textInput.value;
    if (!text) return;
    vibrate(20);
    apiPost('/api/keyboard/type', { text });
    textInput.value = '';
    resetModifiers();
  };

  sendBtn.addEventListener('click', sendText);
  textInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendText(); });

  if (virtualEnterBtn) {
    virtualEnterBtn.addEventListener('click', () => {
      sendText();
      sendDirectKey('Return');
    });
  }

  modifierBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const modifier = btn.getAttribute('data-key');
      activeModifiers[modifier] = !activeModifiers[modifier];
      btn.classList.toggle('active', activeModifiers[modifier]);
      vibrate(15);
    });
  });
}

function resetModifiers() {
  Object.keys(activeModifiers).forEach(k => { activeModifiers[k] = false; });
  document.querySelectorAll('.btn-modifier').forEach(btn => btn.classList.remove('active'));
}

function sendKey(keyName) {
  vibrate(15);
  const modifiersList = [];
  if (activeModifiers.ctrl)  modifiersList.push('ctrl');
  if (activeModifiers.alt)   modifiersList.push('alt');
  if (activeModifiers.super) modifiersList.push('super');
  apiPost('/api/keyboard/key', { key: keyName, modifiers: modifiersList });
  resetModifiers();
}

function sendDirectKey(keyName, modifiers = []) {
  vibrate(20);
  apiPost('/api/keyboard/key', { key: keyName, modifiers });
}

// ─── PANEL 2 : JOYSTICK / TRACKPAD / GYROSCOPE ───────────────────────────────

function initJoystick() {
  const pad            = document.getElementById('joystick-pad');
  const handle         = document.getElementById('joystick-handle');
  const label          = document.getElementById('mouse-control-label');
  const speedSlider    = document.getElementById('mouse-speed');
  const speedVal       = document.getElementById('mouse-speed-val');
  const modeJoyBtn     = document.getElementById('mode-joystick');
  const modeTrackBtn   = document.getElementById('mode-trackpad');
  const modeGyroBtn    = document.getElementById('mode-gyro');
  const speedContainer = document.getElementById('mouse-speed-container');
  const gyroContainer  = document.getElementById('gyro-settings-container');

  let padBounds    = null;
  let isDragging   = false;
  let joystickX    = 0;
  let joystickY    = 0;
  let movementTimer = null;

  // Trackpad
  let prevX = 0, prevY = 0;

  // Deux doigts (scroll)
  let prevTouchX = 0, prevTouchY = 0, isScrolling = false;

  // Détection de tap
  let touchStartX = 0, touchStartY = 0, touchStartTime = 0;
  let hasMoved = false, lastX = 0, lastY = 0;

  // Slider vitesse
  speedSlider.addEventListener('input', () => {
    mouseSpeed = parseInt(speedSlider.value);
    speedVal.textContent = mouseSpeed;
  });

  // Sélecteur de mode
  const setMouseMode = mode => {
    if (mouseMode === 'gyro' && mode !== 'gyro') stopGyroscope();
    mouseMode = mode;

    modeJoyBtn.classList.toggle('active', mode === 'joystick');
    modeTrackBtn.classList.toggle('active', mode === 'trackpad');
    modeGyroBtn.classList.toggle('active', mode === 'gyro');

    if (mode === 'joystick') {
      pad.classList.remove('trackpad-mode');
      speedContainer.style.display = '';
      gyroContainer.style.display  = 'none';
      label.textContent = "Glissez pour déplacer (Joystick)";
    } else if (mode === 'trackpad') {
      pad.classList.add('trackpad-mode');
      speedContainer.style.display = '';
      gyroContainer.style.display  = 'none';
      label.textContent = "Glissez pour déplacer, Tapez G/D pour cliquer";
    } else if (mode === 'gyro') {
      pad.classList.add('trackpad-mode');
      speedContainer.style.display = 'none';
      gyroContainer.style.display  = 'flex';
      label.textContent = "Inclinez le téléphone, Tapez G/D pour cliquer";
      startGyroscope();
    }

    vibrate(15);
    onDragEnd();
  };

  modeJoyBtn.addEventListener('click',   () => setMouseMode('joystick'));
  modeTrackBtn.addEventListener('click', () => setMouseMode('trackpad'));
  modeGyroBtn.addEventListener('click',  () => setMouseMode('gyro'));

  const updatePadBounds = () => { padBounds = pad.getBoundingClientRect(); };

  const onDragStart = e => {
    isDragging = true;
    pad.classList.add('active');
    vibrate(10);

    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;

    touchStartX = lastX = clientX;
    touchStartY = lastY = clientY;
    touchStartTime = Date.now();
    hasMoved = false;

    if (e.touches && e.touches.length === 2) {
      prevTouchX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      prevTouchY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      isScrolling = true;
    } else {
      isScrolling = false;
    }

    if (mouseMode === 'trackpad') {
      prevX = clientX;
      prevY = clientY;
    } else if (mouseMode === 'joystick') {
      updatePadBounds();
      onDragMove(e);
      if (movementTimer) clearInterval(movementTimer);
      movementTimer = setInterval(moveMouseFromJoystick, CONFIG.mousePollRateMs);
    }

    if (e.cancelable && mouseMode !== 'gyro') e.preventDefault();
  };

  const onDragMove = e => {
    if (!isDragging) return;

    // Défilement à deux doigts
    if (e.touches && e.touches.length === 2) {
      const touchX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      const touchY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      if (!isScrolling) { isScrolling = true; prevTouchX = touchX; prevTouchY = touchY; return; }

      const dy = touchY - prevTouchY;
      if (Math.abs(dy) > 10) {
        const direction = dy > 0 ? "down" : "up";
        const clicks    = Math.min(3, Math.max(1, Math.round(Math.abs(dy) / 10)));
        apiPost('/api/mouse/scroll', { direction, clicks });
        prevTouchX = touchX;
        prevTouchY = touchY;
      }
      return;
    }

    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    lastX = clientX;
    lastY = clientY;

    if (Math.abs(clientX - touchStartX) > 8 || Math.abs(clientY - touchStartY) > 8) hasMoved = true;

    if (mouseMode === 'trackpad') {
      const speedScale = mouseSpeed * 0.45;
      const moveX = Math.round((clientX - prevX) * speedScale);
      const moveY = Math.round((clientY - prevY) * speedScale);
      if (moveX !== 0 || moveY !== 0) {
        apiPost('/api/mouse/move', { dx: moveX, dy: moveY });
        prevX = clientX;
        prevY = clientY;
      }
    } else if (mouseMode === 'joystick') {
      let dx = clientX - (padBounds.left + padBounds.width  / 2);
      let dy = clientY - (padBounds.top  + padBounds.height / 2);
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > CONFIG.joystickMaxDist) {
        dx = (dx / dist) * CONFIG.joystickMaxDist;
        dy = (dy / dist) * CONFIG.joystickMaxDist;
      }
      handle.style.transform = `translate(${dx}px, ${dy}px)`;
      joystickX = dx / CONFIG.joystickMaxDist;
      joystickY = dy / CONFIG.joystickMaxDist;
    }
  };

  const onDragEnd = () => {
    if (!isDragging) return;
    isDragging = false;
    pad.classList.remove('active');

    const duration   = Date.now() - touchStartTime;
    const distX      = Math.abs(lastX - touchStartX);
    const distY      = Math.abs(lastY - touchStartY);
    const totalDist  = Math.sqrt(distX * distX + distY * distY);

    // Clic par tap
    if ((mouseMode === 'trackpad' || mouseMode === 'gyro') &&
        (!hasMoved || (duration < 250 && totalDist < 15))) {
      const rect   = pad.getBoundingClientRect();
      const clickX = lastX - rect.left;
      vibrate(20);
      apiPost('/api/mouse/click', { button: clickX < rect.width / 2 ? 'left' : 'right' });
    }

    if (mouseMode === 'joystick') {
      handle.style.transition = 'transform 0.15s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
      handle.style.transform  = 'translate(0px, 0px)';
      joystickX = 0;
      joystickY = 0;
      if (movementTimer) { clearInterval(movementTimer); movementTimer = null; }
      setTimeout(() => { handle.style.transition = ''; }, 150);
    }
  };

  pad.addEventListener('touchstart',     onDragStart, { passive: false });
  window.addEventListener('touchmove',   onDragMove,  { passive: false });
  window.addEventListener('touchend',    onDragEnd);
  pad.addEventListener('mousedown',      onDragStart);
  window.addEventListener('mousemove',   onDragMove);
  window.addEventListener('mouseup',     onDragEnd);

  function moveMouseFromJoystick() {
    if (!isDragging || mouseMode !== 'joystick') return;
    const dist = Math.sqrt(joystickX * joystickX + joystickY * joystickY) * CONFIG.joystickMaxDist;
    if (dist < CONFIG.joystickDeadzone) return;
    const speedMultiplier = 25 * (mouseSpeed / 5);
    const moveX = Math.round(Math.sign(joystickX) * Math.pow(Math.abs(joystickX), 1.5) * speedMultiplier);
    const moveY = Math.round(Math.sign(joystickY) * Math.pow(Math.abs(joystickY), 1.5) * speedMultiplier);
    if (moveX !== 0 || moveY !== 0) apiPost('/api/mouse/move', { dx: moveX, dy: moveY });
  }

  speedSlider.value    = mouseSpeed;
  speedVal.textContent = mouseSpeed;
  setMouseMode(mouseMode);
}

function initMouseButtons() {
  document.getElementById('btn-click-left').addEventListener('click', () => {
    vibrate(20); apiPost('/api/mouse/click', { button: 'left' });
  });
  document.getElementById('btn-click-right').addEventListener('click', () => {
    vibrate(20); apiPost('/api/mouse/click', { button: 'right' });
  });
}

// ─── PANEL 2 : GYROSCOPE ─────────────────────────────────────────────────────

function initGyroscope() {
  const status    = document.getElementById('gyro-status');
  const sensSlider = document.getElementById('gyro-sens');
  const sensValue  = document.getElementById('gyro-sens-val');
  const calibBtn   = document.getElementById('btn-gyro-calibrate');

  let isGyroActive     = false;
  let gyroSensitivity  = parseInt(sensSlider.value);
  let baseBeta  = null;
  let baseGamma = null;
  let accumulatedDx = 0;
  let accumulatedDy = 0;
  let lastSendTime  = 0;

  sensSlider.addEventListener('input', () => {
    gyroSensitivity   = parseInt(sensSlider.value);
    sensValue.textContent = gyroSensitivity;
  });

  calibBtn.addEventListener('click', () => {
    baseBeta = null;
    vibrate(40);
    status.textContent = 'Calibré ! Nouveau neutre enregistré.';
    setTimeout(() => {
      if (isGyroActive) status.textContent = 'Actif. Inclinez le téléphone.';
    }, 1500);
  });

  async function startGyro() {
    if (!window.DeviceOrientationEvent) {
      status.textContent = 'Erreur : Capteur non supporté par ce navigateur.';
      return;
    }
    if (typeof DeviceOrientationEvent.requestPermission === 'function') {
      try {
        const permission = await DeviceOrientationEvent.requestPermission();
        if (permission !== 'granted') { status.textContent = 'Accès au capteur refusé.'; return; }
      } catch (err) {
        status.textContent = 'Erreur autorisation gyroscope : ' + err.message;
        return;
      }
    }
    isGyroActive = true;
    baseBeta     = null;
    status.textContent = 'Initialisation... Mettez le téléphone à plat.';
    window.addEventListener('deviceorientation', handleOrientation);
    vibrate([30, 50, 30]);
  }

  function stopGyro() {
    isGyroActive = false;
    status.textContent = 'Désactivé. Utilisez les capteurs de votre téléphone pour diriger la souris.';
    window.removeEventListener('deviceorientation', handleOrientation);
    vibrate(30);
  }

  startGyroscope = startGyro;
  stopGyroscope  = stopGyro;

  function handleOrientation(e) {
    if (!isGyroActive) return;
    const beta  = e.beta;
    const gamma = e.gamma;
    if (beta === null || gamma === null) return;

    if (baseBeta === null || baseGamma === null) {
      baseBeta = beta; baseGamma = gamma;
      status.textContent = 'Actif. Inclinez le téléphone.';
      return;
    }

    let dGamma = gamma - baseGamma;
    let dBeta  = beta  - baseBeta;

    // Correction de wrap
    if (dGamma > 180) dGamma -= 360; else if (dGamma < -180) dGamma += 360;
    if (dBeta  > 180) dBeta  -= 360; else if (dBeta  < -180) dBeta  += 360;

    const deadzone = 0.6;
    accumulatedDx += Math.abs(dGamma) > deadzone ? dGamma * gyroSensitivity : 0;
    accumulatedDy += Math.abs(dBeta)  > deadzone ? -dBeta * gyroSensitivity : 0;

    const now = Date.now();
    if (now - lastSendTime >= CONFIG.gyroPollRateMs) {
      const rx = Math.round(accumulatedDx);
      const ry = Math.round(accumulatedDy);
      accumulatedDx = 0;
      accumulatedDy = 0;
      if (rx !== 0 || ry !== 0) apiPost('/api/mouse/move', { dx: rx, dy: ry });
      lastSendTime = now;
    }
  }
}

// ─── PANEL 3 : TÉLÉCOMMANDE ───────────────────────────────────────────────────

function sendVolume(action)  { vibrate(15); apiPost('/api/volume',     { action }); }
function sendFullscreen()    { vibrate(25); apiPost('/api/fullscreen'); }
function sendQuitApp()       { vibrate(30); apiPost('/api/quit-app');  }
function sendOpenLauncher()  { vibrate(25); apiPost('/api/system/open-launcher'); }
function sendZoom(level)     { vibrate(15); apiPost('/api/zoom',       { action: level }); }
function sendMedia(action)   { vibrate(20); apiPost('/api/media',      { action }); }

function sendHyperion(action) {
  vibrate(30);
  const onBtn  = document.querySelector('.btn-hyp-on');
  const offBtn = document.querySelector('.btn-hyp-off');
  if (onBtn && offBtn) {
    onBtn.classList.toggle('active',  action === 'on');
    offBtn.classList.toggle('active', action === 'off');
  }
  apiPost('/api/hyperion', { action });
}

// ─── MODAL ALIMENTATION (SHUTDOWN / REBOOT) ───────────────────────────────────

function initPowerModal() {
  const powerModal  = document.getElementById('power-modal');
  const btnShutdown = document.getElementById('btn-power-shutdown');
  const btnReboot   = document.getElementById('btn-power-reboot');
  const btnCancel   = document.getElementById('btn-power-cancel');
  if (!powerModal || !btnShutdown || !btnReboot || !btnCancel) return;

  btnShutdown.addEventListener('click', () => {
    vibrate([50, 100, 50]);
    apiPost('/api/system/shutdown');
    hidePowerModal();
  });
  btnReboot.addEventListener('click', () => {
    vibrate([30, 80, 30]);
    apiPost('/api/system/reboot');
    hidePowerModal();
  });
  btnCancel.addEventListener('click', hidePowerModal);
  powerModal.addEventListener('click', e => { if (e.target.id === 'power-modal') hidePowerModal(); });
}

function showPowerModal() {
  vibrate(20);
  document.getElementById('power-modal')?.classList.add('active');
}

function hidePowerModal() {
  vibrate(10);
  document.getElementById('power-modal')?.classList.remove('active');
}

// ─── MISE À JOUR DU SYSTÈME ───────────────────────────────────────────────────

function initUpdateButton() {
  const btn = document.getElementById('btn-system-update');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    vibrate(30);
    hidePowerModal();

    const original  = btn.innerHTML;
    btn.disabled    = true;
    btn.innerHTML   = '⏳ Mise à jour...';
    btn.style.opacity = '0.6';

    try { await apiPost('/api/system/update'); }
    catch (e) { console.error('Update error:', e); }

    btn.innerHTML = '🔄 Redémarrage...';

    let attempts = 0;
    const pollInterval = setInterval(async () => {
      attempts++;
      try {
        const r = await fetch('/api/status', { cache: 'no-store' });
        if (r.ok) {
          clearInterval(pollInterval);
          btn.innerHTML     = '✅ À jour !';
          btn.style.opacity = '1';
          setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 2500);
          setTimeout(() => location.reload(), 3000);
        }
      } catch (_) { /* serveur en cours de redémarrage */ }
      if (attempts >= 30) {
        clearInterval(pollInterval);
        btn.innerHTML     = '⚠️ Timeout';
        btn.style.opacity = '1';
        setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 3000);
      }
    }, 1000);
  });
}

// ─── PANEL 1 : CMS APPLICATIONS (AJOUTER / ÉDITER / SUPPRIMER / RÉORGANISER) ─

function initAppsCMS() {
  const editModeBtn = document.getElementById('btn-edit-mode');
  const favUrlBtn   = document.getElementById('btn-fav-url');
  const cancelBtn   = document.getElementById('btn-modal-cancel');
  const saveBtn     = document.getElementById('btn-modal-save');

  editModeBtn.addEventListener('click', () => {
    isEditMode = !isEditMode;
    editModeBtn.classList.toggle('active', isEditMode);
    vibrate(20);
    initApps();
  });

  favUrlBtn.addEventListener('click', () => { vibrate(15); openAddFavModal(); });
  cancelBtn.addEventListener('click', hideModal);
  saveBtn.addEventListener('click',   saveModal);

  document.getElementById('app-modal').addEventListener('click', e => {
    if (e.target.id === 'app-modal') hideModal();
  });
}

function openAddFavModal() {
  const customUrlInput = document.getElementById('custom-url-input');
  document.getElementById('modal-title').textContent   = "Épingler aux Favoris";
  document.getElementById('modal-app-id').value        = "";
  document.getElementById('modal-app-name').value      = "";
  document.getElementById('modal-app-browser').value   = document.getElementById('custom-url-browser').value;

  let url = customUrlInput.value.trim();
  if (url && !/^https?:\/\//i.test(url)) url = `http://${url}`;
  document.getElementById('modal-app-url').value = url;

  document.getElementById('app-modal').classList.add('active');
}

function openAppEditModal(app) {
  document.getElementById('modal-title').textContent  = "Modifier l'Application";
  document.getElementById('modal-app-id').value       = app.id;
  document.getElementById('modal-app-name').value     = app.name;
  document.getElementById('modal-app-url').value      = app.url || "";
  document.getElementById('modal-app-browser').value  = app.browser || "firefox";
  document.getElementById('app-modal').classList.add('active');
}

function hideModal() {
  vibrate(10);
  document.getElementById('app-modal').classList.remove('active');
}

async function saveModal() {
  vibrate(25);
  const appId   = document.getElementById('modal-app-id').value;
  const name    = document.getElementById('modal-app-name').value.trim();
  const url     = document.getElementById('modal-app-url').value.trim();
  const browser = document.getElementById('modal-app-browser').value;

  if (!name || !url) { alert("Veuillez remplir le nom et l'adresse URL."); return; }

  const endpoint = appId ? '/api/apps/edit' : '/api/apps/add';
  const payload  = { name, url, browser };
  if (appId) payload.id = appId;

  const result = await apiPost(endpoint, payload);
  if (result?.success) { hideModal(); initApps(); }
  else { alert("Une erreur s'est produite lors de l'enregistrement."); }
}

async function deleteApp(appId, appName) {
  vibrate([20, 50, 20]);
  if (!confirm(`Voulez-vous vraiment supprimer "${appName}" des favoris ?`)) return;
  const result = await apiPost('/api/apps/delete', { id: appId });
  if (result?.success) initApps();
  else alert("Impossible de supprimer l'application.");
}

async function moveAppInList(currentIndex, direction) {
  vibrate(15);
  const targetIndex = currentIndex + direction;
  if (targetIndex < 0 || targetIndex >= cachedApps.length) return;

  [cachedApps[currentIndex], cachedApps[targetIndex]] = [cachedApps[targetIndex], cachedApps[currentIndex]];

  const result = await apiPost('/api/apps/reorder', { order: cachedApps.map(a => a.id) });
  if (result?.success) initApps();
}

// ─── MONITEUR TV EN DIRECT ────────────────────────────────────────────────────

let isMonitorActive  = false;
let isControlActive  = true;
let monitorFps       = 2;
let monitorInterval  = null;
let isPolling        = false;
let lastMoveAbsTime  = 0;
const MOVE_ABS_THROTTLE_MS = 60;

function initMonitor() {
  const chkMonitor   = document.getElementById('chk-monitor-active');
  const chkControl   = document.getElementById('chk-control-active');
  const fpsSlider    = document.getElementById('range-monitor-fps');
  const fpsVal       = document.getElementById('val-monitor-fps');
  const img          = document.getElementById('monitor-screenshot');
  const innerWrapper = document.getElementById('monitor-screen-inner');
  const touchpad     = document.getElementById('monitor-touchpad');
  const modeSelect   = document.getElementById('select-monitor-mode');
  const fpsRow       = document.getElementById('fps-control-row');
  const activeRow    = document.getElementById('monitor-active-row');
  
  if (!chkMonitor || !chkControl || !fpsSlider || !img) return;

  // Plein écran
  const btnFullscreen = document.getElementById('btn-monitor-fullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      const container = document.getElementById('live-monitor-container');
      if (!container) return;
      if (!document.fullscreenElement) {
        container.requestFullscreen().catch(err => console.error(`Plein écran impossible: ${err.message}`));
      } else {
        document.exitFullscreen();
      }
    });
  }

  // Sélecteur de Mode
  if (modeSelect && touchpad && innerWrapper) {
    modeSelect.addEventListener('change', () => {
      const isTrackpad = modeSelect.value === 'trackpad';
      innerWrapper.style.display = isTrackpad ? 'none' : 'flex';
      touchpad.style.display = isTrackpad ? 'flex' : 'none';
      if (fpsRow) fpsRow.style.display = isTrackpad ? 'none' : 'flex';
      
      if (isTrackpad) {
        // En mode trackpad, on désactive le flux d'images
        stopMonitor();
        if (chkMonitor) chkMonitor.checked = false;
      }
    });
  }

  // Détection support tactile (iPad / mobile)
  const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0) || (navigator.msMaxTouchPoints > 0);
  if (isTouchDevice && modeSelect) {
    // Par défaut en trackpad
    modeSelect.value = 'trackpad';
    if (innerWrapper) innerWrapper.style.display = 'none';
    if (touchpad) touchpad.style.display = 'flex';
    if (fpsRow) fpsRow.style.display = 'none';
    if (activeRow) activeRow.style.display = 'none'; // Pas besoin du Flux Actif
  }

  // Initialisation du trackpad
  initTouchpad();

  // État initial
  chkMonitor.checked = false;
  chkControl.checked = true;
  isControlActive    = true;
  innerWrapper.classList.add('control-enabled');

  chkMonitor.addEventListener('change', () => chkMonitor.checked ? startMonitor() : stopMonitor());

  chkControl.addEventListener('change', () => {
    isControlActive = chkControl.checked;
    innerWrapper.classList.toggle('control-enabled', isControlActive);
    if (!isControlActive) document.getElementById('monitor-pointer').style.display = 'none';
    vibrate(20);
  });

  fpsSlider.addEventListener('input', () => {
    monitorFps = parseInt(fpsSlider.value);
    fpsVal.textContent = monitorFps;
  });

  // Déplacement souris sur l'image
  img.addEventListener('mousemove', e => {
    if (!isControlActive) return;
    const rect = img.getBoundingClientRect();
    sendThrottledMoveAbs((e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height);
    updateLocalPointer(e.clientX - rect.left, e.clientY - rect.top);
  });

  // Clic souris sur l'image
  img.addEventListener('mousedown', e => {
    if (!isControlActive) return;
    const rect = img.getBoundingClientRect();
    sendMoveAbsDirect(
      (e.clientX - rect.left) / rect.width,
      (e.clientY - rect.top)  / rect.height,
      () => apiPost('/api/mouse/click', { button: e.button === 2 ? 'right' : 'left' })
    );
    e.preventDefault();
  });

  // Molette → scroll TV
  img.addEventListener('wheel', e => {
    if (!isControlActive) return;
    e.preventDefault();
    const direction = e.deltaY > 0 ? 'down' : 'up';
    const clicks    = Math.max(1, Math.min(2, Math.round(Math.abs(e.deltaY) / 120)));
    apiPost('/api/mouse/scroll', { direction, clicks });
  }, { passive: false });

  // Désactiver menu contextuel sur l'image
  img.addEventListener('contextmenu', e => { if (isControlActive) e.preventDefault(); });
}

let touchStartX = 0;
let touchStartY = 0;
let lastTouchX = 0;
let lastTouchY = 0;
let touchStartT = 0;
let isMoving = false;
let touchCount = 0;
let accumDx = 0;
let accumDy = 0;
let lastTouchSendTime = 0;
const TOUCH_SEND_INTERVAL_MS = 25;

function initTouchpad() {
  const surface = document.getElementById('touchpad-surface');
  const btnLeft = document.getElementById('touchpad-btn-left');
  const btnRight = document.getElementById('touchpad-btn-right');
  if (!surface) return;

  btnLeft.addEventListener('click', () => {
    vibrate(15);
    apiPost('/api/mouse/click', { button: 'left' });
  });

  btnRight.addEventListener('click', () => {
    vibrate(15);
    apiPost('/api/mouse/click', { button: 'right' });
  });

  surface.addEventListener('touchstart', e => {
    touchCount = e.touches.length;
    const touch = e.touches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
    lastTouchX = touchStartX;
    lastTouchY = touchStartY;
    touchStartT = Date.now();
    isMoving = false;
    accumDx = 0;
    accumDy = 0;
  }, { passive: true });

  surface.addEventListener('touchmove', e => {
    if (e.touches.length === 1 && touchCount === 1) {
      const touch = e.touches[0];
      const dx = (touch.clientX - lastTouchX) * 1.5;
      const dy = (touch.clientY - lastTouchY) * 1.5;

      lastTouchX = touch.clientX;
      lastTouchY = touch.clientY;

      if (Math.abs(touch.clientX - touchStartX) > 5 || Math.abs(touch.clientY - touchStartY) > 5) {
        isMoving = true;
      }

      accumDx += dx;
      accumDy += dy;

      const now = Date.now();
      if (now - lastTouchSendTime >= TOUCH_SEND_INTERVAL_MS) {
        sendTouchMove();
        lastTouchSendTime = now;
      }
    } else if (e.touches.length === 2 && touchCount === 2) {
      e.preventDefault();
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const avgY = (t1.clientY + t2.clientY) / 2;
      
      if (!surface.lastAvgY) {
        surface.lastAvgY = avgY;
      } else {
        const dy = avgY - surface.lastAvgY;
        if (Math.abs(dy) > 15) {
          const direction = dy > 0 ? 'down' : 'up';
          apiPost('/api/mouse/scroll', { direction, clicks: 1 });
          surface.lastAvgY = avgY;
          vibrate(10);
        }
      }
    }
  }, { passive: false });

  surface.addEventListener('touchend', e => {
    sendTouchMove();

    const duration = Date.now() - touchStartT;
    if (!isMoving && duration < 300) {
      vibrate(15);
      if (touchCount === 1) {
        apiPost('/api/mouse/click', { button: 'left' });
      } else if (touchCount === 2) {
        apiPost('/api/mouse/click', { button: 'right' });
      }
    }
    surface.lastAvgY = null;
  }, { passive: true });

  function sendTouchMove() {
    const rx = Math.round(accumDx);
    const ry = Math.round(accumDy);
    accumDx = 0;
    accumDy = 0;
    if (rx !== 0 || ry !== 0) {
      apiPost('/api/mouse/move', { dx: rx, dy: ry });
    }
  }
}

function startMonitor() {
  isMonitorActive = true;
  document.querySelector('.monitor-dot').classList.add('active');
  pollScreenshot();
}

function stopMonitor() {
  isMonitorActive = false;
  document.querySelector('.monitor-dot').classList.remove('active');
  if (monitorInterval) { clearTimeout(monitorInterval); monitorInterval = null; }
  document.getElementById('monitor-screenshot').src =
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='9' viewBox='0 0 16 9'>" +
    "<rect width='100%' height='100%' fill='%23181824'/>" +
    "<text x='50%' y='50%' font-family='sans-serif' font-size='0.8' fill='%236e6e8a' " +
    "dominant-baseline='middle' text-anchor='middle'>Flux Inactif</text></svg>";
  document.getElementById('monitor-pointer').style.display = 'none';
}

function pollScreenshot() {
  if (!isMonitorActive || isPolling) return;
  isPolling = true;
  const img     = document.getElementById('monitor-screenshot');
  const tempImg = new Image();
  tempImg.onload  = () => { img.src = tempImg.src; isPolling = false; scheduleNextPoll(); };
  tempImg.onerror = () => { isPolling = false; scheduleNextPoll(); };
  tempImg.src = `/api/system/screenshot?t=${Date.now()}`;
}

function scheduleNextPoll() {
  if (monitorInterval) clearTimeout(monitorInterval);
  monitorInterval = setTimeout(pollScreenshot, 1000 / monitorFps);
}

function sendThrottledMoveAbs(x, y) {
  const now = Date.now();
  if (now - lastMoveAbsTime >= MOVE_ABS_THROTTLE_MS) {
    lastMoveAbsTime = now;
    apiPost('/api/mouse/move_abs', { x, y });
  }
}

async function sendMoveAbsDirect(x, y, callback) {
  const res = await apiPost('/api/mouse/move_abs', { x, y });
  if (res?.success && callback) callback();
}

function updateLocalPointer(px, py) {
  const pointer = document.getElementById('monitor-pointer');
  if (pointer) {
    pointer.style.display = 'block';
    pointer.style.left    = px + 'px';
    pointer.style.top     = py + 'px';
  }
}

// ─── CLAVIER PHYSIQUE GLOBAL (quand le contrôle live est actif) ───────────────

window.addEventListener('keydown', e => {
  if (!isControlActive) return;

  // Ignorer si un champ de texte est actif
  const activeEl = document.activeElement;
  if (activeEl && ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeEl.tagName)) return;

  // Laisser le navigateur gérer les combinaisons avec modificateurs
  if (e.ctrlKey || e.altKey || e.metaKey) return;

  const keyMap = {
    'Backspace': 'BackSpace', 'Tab': 'Tab', 'Enter': 'Return',
    'Escape': 'Escape', ' ': 'space',
    'ArrowLeft': 'Left', 'ArrowUp': 'Up', 'ArrowRight': 'Right', 'ArrowDown': 'Down',
    'Delete': 'Delete', 'F11': 'F11',
  };
  const ignoredKeys = ['Control', 'Shift', 'Alt', 'Meta', 'CapsLock'];
  if (ignoredKeys.includes(e.key)) return;

  const key       = keyMap[e.key] || e.key;
  const modifiers = (e.shiftKey && key.length > 1) ? ['shift'] : [];
  apiPost('/api/keyboard/key', { key, modifiers });
  e.preventDefault();
});
