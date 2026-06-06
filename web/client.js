// client.js - TV Launcher Remote Controller Logic

// Active modifiers state
const activeModifiers = {
  ctrl: false,
  alt: false,
  super: false
};

// State variables for CMS and Mouse modes
let isEditMode = false;
let mouseMode = 'joystick'; // 'joystick', 'trackpad', or 'gyro'
let mouseSpeed = 5;         // Sensitivity multiplier (1 to 10)
let cachedApps = [];        // Local copy of apps list

// Global hooks for gyro controls (assigned in initGyroscope)
let startGyroscope = () => {};
let stopGyroscope = () => {};

// Connection status check interval
let statusInterval = null;

// Global settings
const CONFIG = {
  apiBase: '',
  mousePollRateMs: 45, // Rate limit for mouse moves
  gyroPollRateMs: 40,
  joystickDeadzone: 5,
  joystickMaxDist: 60, // Maximum distance the handle can move (px)
};

// Load Apps on Startup
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initApps();
  initKeyboard();
  initJoystick();
  initMouseButtons();
  initGyroscope();
  initUrlLauncher();
  initAppsCMS(); // Initialize Modal & Edit Mode triggers
  
  // Connection status loop
  checkStatus();
  statusInterval = setInterval(checkStatus, 5000);
});

// ---------------------------------------------------------
// Navigation (Tab Switching)
// ---------------------------------------------------------
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const panels = document.querySelectorAll('.tab-panel');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetPanelId = item.getAttribute('data-target');
      
      // Update nav buttons
      navItems.forEach(nav => nav.classList.remove('active'));
      item.classList.add('active');
      
      // Update panels
      panels.forEach(panel => {
        panel.classList.remove('active');
        if (panel.id === targetPanelId) {
          panel.classList.add('active');
        }
      });

      // Vibrate on tap
      vibrate(10);
    });
  });
}

// ---------------------------------------------------------
// API Call Helper
// ---------------------------------------------------------
async function apiPost(endpoint, data = {}) {
  try {
    const response = await fetch(`${CONFIG.apiBase}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data)
    });
    
    if (!response.ok) {
      console.error(`API Error: ${response.statusText}`);
      updateConnectionStatus(false);
      return null;
    }
    
    updateConnectionStatus(true);
    return await response.json();
  } catch (error) {
    console.error('Fetch Error:', error);
    updateConnectionStatus(false);
    return null;
  }
}

function updateConnectionStatus(isConnected) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  
  if (isConnected) {
    dot.className = 'status-dot online';
    text.textContent = 'Connecté à tv.local';
  } else {
    dot.className = 'status-dot offline';
    text.textContent = 'Déconnecté';
  }
}

async function checkStatus() {
  try {
    const response = await fetch(`${CONFIG.apiBase}/api/status`);
    updateConnectionStatus(response.ok);
  } catch {
    updateConnectionStatus(false);
  }
}

// Simple haptic feedback
function vibrate(ms) {
  if (navigator.vibrate) {
    navigator.vibrate(ms);
  }
}

// ---------------------------------------------------------
// Panel 1: Apps Launcher
// ---------------------------------------------------------
async function initApps() {
  const grid = document.getElementById('apps-grid');
  const countBadge = document.getElementById('apps-count');
  
  try {
    const response = await fetch(`${CONFIG.apiBase}/api/apps`);
    if (!response.ok) throw new Error("Could not fetch apps list");
    const data = await response.json();
    
    grid.innerHTML = '';
    cachedApps = data.apps || [];
    countBadge.textContent = cachedApps.length;
    
    if (cachedApps.length === 0) {
      grid.innerHTML = '<p class="loading-placeholder">Aucune application configurée.</p>';
      return;
    }
    
    // Toggle edit-mode class on the grid container
    if (isEditMode) {
      grid.classList.add('edit-mode');
    } else {
      grid.classList.remove('edit-mode');
    }
    
    cachedApps.forEach((app, index) => {
      const btn = document.createElement('div'); // Use div in edit mode to avoid button issues
      btn.className = 'app-item-btn';
      
      const iconWrap = document.createElement('div');
      iconWrap.className = 'app-icon-wrapper';
      
      const img = document.createElement('img');
      img.src = app.icon ? `/${app.icon}` : '/icons/firefox.png';
      img.onerror = () => { img.src = '/icons/firefox.png'; };
      
      iconWrap.appendChild(img);
      
      const name = document.createElement('span');
      name.className = 'app-name';
      name.textContent = app.name;
      
      btn.appendChild(iconWrap);
      btn.appendChild(name);
      
      if (isEditMode) {
        // 1. Delete Button
        const delBtn = document.createElement('div');
        delBtn.className = 'btn-delete-app';
        delBtn.innerHTML = '✕';
        delBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteApp(app.id, app.name);
        });
        btn.appendChild(delBtn);
        
        // 2. Edit Button
        const editBtn = document.createElement('div');
        editBtn.className = 'btn-edit-app';
        editBtn.innerHTML = '✏️';
        editBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          openAppEditModal(app);
        });
        btn.appendChild(editBtn);
        
        // 3. Reorder buttons (arrows)
        const reorderWrap = document.createElement('div');
        reorderWrap.className = 'app-reorder-actions';
        
        const leftArrow = document.createElement('div');
        leftArrow.className = 'btn-reorder';
        leftArrow.innerHTML = '◀';
        leftArrow.addEventListener('click', (e) => {
          e.stopPropagation();
          moveAppInList(index, -1);
        });
        
        const rightArrow = document.createElement('div');
        rightArrow.className = 'btn-reorder';
        rightArrow.innerHTML = '▶';
        rightArrow.addEventListener('click', (e) => {
          e.stopPropagation();
          moveAppInList(index, 1);
        });
        
        reorderWrap.appendChild(leftArrow);
        reorderWrap.appendChild(rightArrow);
        btn.appendChild(reorderWrap);
      } else {
        // Standard launch app click listener
        btn.addEventListener('click', () => {
          vibrate(25);
          launchApp(app.id);
        });
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
  const urlInput = document.getElementById('custom-url-input');
  const browserSelect = document.getElementById('custom-url-browser');
  const openBtn = document.getElementById('btn-open-url');
  
  openBtn.addEventListener('click', () => {
    const rawUrl = urlInput.value.trim();
    if (!rawUrl) return;
    
    vibrate(30);
    // Auto-prepend http:// if not present
    let url = rawUrl;
    if (!/^https?:\/\//i.test(url)) {
      url = 'http://' + url;
    }
    
    apiPost('/api/launch-url', {
      url: url,
      browser: browserSelect.value
    });
  });
}

// ---------------------------------------------------------
// Panel 2: Keyboard simulation
// ---------------------------------------------------------
function initKeyboard() {
  const textInput = document.getElementById('keyboard-text-input');
  const sendBtn = document.getElementById('btn-send-text');
  const modifierBtns = document.querySelectorAll('.btn-modifier');
  
  // Text submission
  sendBtn.addEventListener('click', () => {
    const text = textInput.value;
    if (text) {
      vibrate(20);
      apiPost('/api/keyboard/type', { text: text });
      textInput.value = '';
      
      // Reset modifier keys after text submission
      resetModifiers();
    }
  });
  
  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      sendBtn.click();
    }
  });
  
  // Modifier key buttons (Ctrl, Alt, Win toggles)
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
  const modifierBtns = document.querySelectorAll('.btn-modifier');
  Object.keys(activeModifiers).forEach(k => {
    activeModifiers[k] = false;
  });
  modifierBtns.forEach(btn => btn.classList.remove('active'));
}

// Send keyboard shortcut
function sendKey(keyName) {
  vibrate(15);
  
  // Gather active modifiers
  const modifiersList = [];
  if (activeModifiers.ctrl) modifiersList.push('ctrl');
  if (activeModifiers.alt) modifiersList.push('alt');
  if (activeModifiers.super) modifiersList.push('super');
  
  apiPost('/api/keyboard/key', {
    key: keyName,
    modifiers: modifiersList
  });
  
  // Reset modifier toggles after sending a standard key press
  resetModifiers();
}

// ---------------------------------------------------------
// Panel 2: Mouse Joystick Pointer Controller
// ---------------------------------------------------------
function initJoystick() {
  const pad = document.getElementById('joystick-pad');
  const handle = document.getElementById('joystick-handle');
  const label = document.getElementById('mouse-control-label');
  const speedSlider = document.getElementById('mouse-speed');
  const speedVal = document.getElementById('mouse-speed-val');
  
  const modeJoyBtn = document.getElementById('mode-joystick');
  const modeTrackBtn = document.getElementById('mode-trackpad');
  const modeGyroBtn = document.getElementById('mode-gyro');

  const speedContainer = document.getElementById('mouse-speed-container');
  const gyroContainer = document.getElementById('gyro-settings-container');
  
  let padBounds = null;
  let isDragging = false;
  let joystickX = 0; // Value from -1 to 1 representing displacement
  let joystickY = 0; 
  let movementTimer = null; // Timer for continuous pointer movement
  
  // Trackpad movement deltas
  let prevX = 0;
  let prevY = 0;

  // Tap detection variables
  let touchStartX = 0;
  let touchStartY = 0;
  let touchStartTime = 0;
  let hasMoved = false;
  let lastX = 0;
  let lastY = 0;

  // 1. Mouse speed / sensitivity slider setup
  speedSlider.addEventListener('input', () => {
    mouseSpeed = parseInt(speedSlider.value);
    speedVal.textContent = mouseSpeed;
  });

  // 2. Mouse Mode selector setup (Joystick vs Trackpad vs Gyro)
  const setMouseMode = (mode) => {
    if (mouseMode === 'gyro' && mode !== 'gyro') {
      stopGyroscope();
    }
    
    mouseMode = mode;
    
    // Toggle active state on buttons
    modeJoyBtn.classList.toggle('active', mode === 'joystick');
    modeTrackBtn.classList.toggle('active', mode === 'trackpad');
    modeGyroBtn.classList.toggle('active', mode === 'gyro');
    
    // Toggle class and display containers
    if (mode === 'joystick') {
      pad.classList.remove('trackpad-mode');
      speedContainer.style.display = '';
      gyroContainer.style.display = 'none';
      label.textContent = "Glissez pour déplacer (Joystick)";
    } else if (mode === 'trackpad') {
      pad.classList.add('trackpad-mode');
      speedContainer.style.display = '';
      gyroContainer.style.display = 'none';
      label.textContent = "Glissez pour déplacer, Tapez G/D pour cliquer";
    } else if (mode === 'gyro') {
      pad.classList.add('trackpad-mode'); // Gyro also uses rectangular pad for clicks
      speedContainer.style.display = 'none';
      gyroContainer.style.display = 'flex';
      label.textContent = "Inclinez le téléphone, Tapez G/D pour cliquer";
      
      // Auto-start gyroscope
      startGyroscope();
    }
    
    vibrate(15);
    onDragEnd(); // Reset dragging state
  };

  modeJoyBtn.addEventListener('click', () => setMouseMode('joystick'));
  modeTrackBtn.addEventListener('click', () => setMouseMode('trackpad'));
  modeGyroBtn.addEventListener('click', () => setMouseMode('gyro'));

  // Initialize bounds on touch start to support scrolling/rotations
  const updatePadBounds = () => {
    padBounds = pad.getBoundingClientRect();
  };

  const onDragStart = (e) => {
    isDragging = true;
    pad.classList.add('active');
    vibrate(10);
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    // Tap detection setup
    touchStartX = clientX;
    touchStartY = clientY;
    lastX = clientX;
    lastY = clientY;
    touchStartTime = Date.now();
    hasMoved = false;
    
    if (mouseMode === 'trackpad') {
      prevX = clientX;
      prevY = clientY;
    } else if (mouseMode === 'joystick') {
      updatePadBounds();
      onDragMove(e);
      // Start interval to continuously move pointer based on joystick tilt
      if (movementTimer) clearInterval(movementTimer);
      movementTimer = setInterval(moveMouseFromJoystick, CONFIG.mousePollRateMs);
    }
    
    if (e.cancelable && mouseMode !== 'gyro') {
      e.preventDefault();
    }
  };

  const onDragMove = (e) => {
    if (!isDragging) return;
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    lastX = clientX;
    lastY = clientY;
    
    const displacementX = Math.abs(clientX - touchStartX);
    const displacementY = Math.abs(clientY - touchStartY);
    if (displacementX > 8 || displacementY > 8) {
      hasMoved = true;
    }
    
    if (mouseMode === 'trackpad') {
      const dx = clientX - prevX;
      const dy = clientY - prevY;
      
      // Scale displacement based on speed slider
      const speedScale = mouseSpeed * 0.45;
      const moveX = Math.round(dx * speedScale);
      const moveY = Math.round(dy * speedScale);
      
      if (moveX !== 0 || moveY !== 0) {
        apiPost('/api/mouse/move', { dx: moveX, dy: moveY });
        prevX = clientX;
        prevY = clientY;
      }
    } else if (mouseMode === 'joystick') {
      const padCenterX = padBounds.left + padBounds.width / 2;
      const padCenterY = padBounds.top + padBounds.height / 2;
      
      // Relative displacement vector
      let dx = clientX - padCenterX;
      let dy = clientY - padCenterY;
      
      // Calculate distance
      const dist = Math.sqrt(dx * dx + dy * dy);
      
      // Constraint displacement to circle perimeter
      if (dist > CONFIG.joystickMaxDist) {
        dx = (dx / dist) * CONFIG.joystickMaxDist;
        dy = (dy / dist) * CONFIG.joystickMaxDist;
      }
      
      // Set handle style offset
      handle.style.transform = `translate(${dx}px, ${dy}px)`;
      
      // Normalize values between -1.0 and 1.0
      joystickX = dx / CONFIG.joystickMaxDist;
      joystickY = dy / CONFIG.joystickMaxDist;
    }
  };

  const onDragEnd = () => {
    if (!isDragging) return;
    isDragging = false;
    pad.classList.remove('active');
    
    const duration = Date.now() - touchStartTime;
    const displacementX = Math.abs(lastX - touchStartX);
    const displacementY = Math.abs(lastY - touchStartY);
    const totalDist = Math.sqrt(displacementX * displacementX + displacementY * displacementY);
    
    // Tap-to-click detection
    if ((mouseMode === 'trackpad' || mouseMode === 'gyro') && 
        (!hasMoved || (duration < 250 && totalDist < 15))) {
      // It's a tap! Click Left or Right based on position
      const rect = pad.getBoundingClientRect();
      const clickX = lastX - rect.left;
      
      vibrate(20);
      if (clickX < rect.width / 2) {
        apiPost('/api/mouse/click', { button: 'left' });
      } else {
        apiPost('/api/mouse/click', { button: 'right' });
      }
    }
    
    if (mouseMode === 'joystick') {
      // Animate stick snap-back to center
      handle.style.transition = 'transform 0.15s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
      handle.style.transform = 'translate(0px, 0px)';
      
      joystickX = 0;
      joystickY = 0;
      
      if (movementTimer) {
        clearInterval(movementTimer);
        movementTimer = null;
      }
      
      setTimeout(() => {
        handle.style.transition = '';
      }, 150);
    }
  };

  // Joystick/Trackpad Events (Mouse + Touch)
  pad.addEventListener('touchstart', onDragStart, { passive: false });
  window.addEventListener('touchmove', onDragMove, { passive: false });
  window.addEventListener('touchend', onDragEnd);
  
  pad.addEventListener('mousedown', onDragStart);
  window.addEventListener('mousemove', onDragMove);
  window.addEventListener('mouseup', onDragEnd);

  // Send relative mouse movement to server (Joystick continuous poll)
  function moveMouseFromJoystick() {
    if (!isDragging || mouseMode !== 'joystick') return;
    
    // Check deadzone
    const dist = Math.sqrt(joystickX * joystickX + joystickY * joystickY) * CONFIG.joystickMaxDist;
    if (dist < CONFIG.joystickDeadzone) return;
    
    // Speed curves based on displacement and mouseSpeed slider settings
    const speedMultiplier = 25 * (mouseSpeed / 5);
    const moveX = Math.round(Math.sign(joystickX) * Math.pow(Math.abs(joystickX), 1.5) * speedMultiplier);
    const moveY = Math.round(Math.sign(joystickY) * Math.pow(Math.abs(joystickY), 1.5) * speedMultiplier);
    
    if (moveX !== 0 || moveY !== 0) {
      apiPost('/api/mouse/move', { dx: moveX, dy: moveY });
    }
  }
}

function initMouseButtons() {
  const leftClick = document.getElementById('btn-click-left');
  const rightClick = document.getElementById('btn-click-right');
  
  leftClick.addEventListener('click', () => {
    vibrate(20);
    apiPost('/api/mouse/click', { button: 'left' });
  });
  
  rightClick.addEventListener('click', () => {
    vibrate(20);
    apiPost('/api/mouse/click', { button: 'right' });
  });
}

// ---------------------------------------------------------
// Panel 3: Gyroscope Mouse Controller
// ---------------------------------------------------------
function initGyroscope() {
  const status = document.getElementById('gyro-status');
  const sensSlider = document.getElementById('gyro-sens');
  const sensValue = document.getElementById('gyro-sens-val');
  const calibBtn = document.getElementById('btn-gyro-calibrate');
  
  let isGyroActive = false;
  let gyroSensitivity = parseInt(sensSlider.value);
  
  // Baselines for orientation (neutral phone posture)
  let baseBeta = null;
  let baseGamma = null;
  
  // Accumulators for throttling orientation inputs
  let accumulatedDx = 0;
  let accumulatedDy = 0;
  let lastSendTime = 0;

  sensSlider.addEventListener('input', () => {
    gyroSensitivity = parseInt(sensSlider.value);
    sensValue.textContent = gyroSensitivity;
  });

  calibBtn.addEventListener('click', () => {
    baseBeta = null; // Forces re-calibration on next frame
    vibrate(40);
    status.textContent = 'Calibré ! Nouveau neutre enregistré.';
    setTimeout(() => {
      if (isGyroActive) status.textContent = 'Actif. Inclinez le téléphone.';
    }, 1500);
  });

  async function startGyro() {
    // Check if device orientation API is available
    if (!window.DeviceOrientationEvent) {
      status.textContent = 'Erreur : Capteur non supporté par ce navigateur.';
      return;
    }

    // iOS requires permission dialog
    if (typeof DeviceOrientationEvent.requestPermission === 'function') {
      try {
        const permission = await DeviceOrientationEvent.requestPermission();
        if (permission !== 'granted') {
          status.textContent = 'Accès au capteur refusé.';
          return;
        }
      } catch (err) {
        status.textContent = 'Erreur autorisation gyroscope : ' + err.message;
        return;
      }
    }

    isGyroActive = true;
    baseBeta = null; // Re-calibrate on startup
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

  // Expose methods to global scope
  startGyroscope = startGyro;
  stopGyroscope = stopGyro;

  function handleOrientation(e) {
    if (!isGyroActive) return;

    let beta = e.beta;   // front-back tilt [-180, 180]
    let gamma = e.gamma; // left-right tilt [-90, 90]

    if (beta === null || gamma === null) return;

    // First frame calibration
    if (baseBeta === null || baseGamma === null) {
      baseBeta = beta;
      baseGamma = gamma;
      status.textContent = 'Actif. Inclinez le téléphone.';
      return;
    }

    // Calculate angular offset from baseline
    let dGamma = gamma - baseGamma;
    let dBeta = beta - baseBeta;

    // Handle wrapping issues if any (less common for remote usage)
    if (dGamma > 180) dGamma -= 360;
    if (dGamma < -180) dGamma += 360;
    if (dBeta > 180) dBeta -= 360;
    if (dBeta < -180) dBeta += 360;

    // Simple deadzone to prevent shaking hands from jittering the cursor
    const deadzone = 0.6;
    let dx = 0;
    let dy = 0;

    if (Math.abs(dGamma) > deadzone) {
      // Map Left/Right tilt to Mouse X movement
      dx = dGamma * gyroSensitivity;
    }
    
    if (Math.abs(dBeta) > deadzone) {
      // Map Up/Down tilt to Mouse Y movement (inverted Y-axis)
      dy = -dBeta * gyroSensitivity;
    }

    // Accumulate movement delta
    accumulatedDx += dx;
    accumulatedDy += dy;

    // Throttle networking requests
    const now = Date.now();
    if (now - lastSendTime >= CONFIG.gyroPollRateMs) {
      sendGyroMove();
      lastSendTime = now;
    }
  }

  function sendGyroMove() {
    const rx = Math.round(accumulatedDx);
    const ry = Math.round(accumulatedDy);

    // Clear accumulator
    accumulatedDx = 0;
    accumulatedDy = 0;

    if (rx !== 0 || ry !== 0) {
      apiPost('/api/mouse/move', { dx: rx, dy: ry });
    }
  }
}

// ---------------------------------------------------------
// Panel 3: Other Remote API calls
// ---------------------------------------------------------
function sendVolume(action) {
  vibrate(15);
  apiPost('/api/volume', { action: action });
}

function sendHyperion(action) {
  vibrate(30);
  
  // Set active buttons style for Hyperion toggle
  const onBtn = document.querySelector('.btn-hyp.btn-on');
  const offBtn = document.querySelector('.btn-hyp.btn-off');
  
  if (action === 'on') {
    onBtn.classList.add('active');
    offBtn.classList.remove('active');
  } else {
    onBtn.classList.remove('active');
    offBtn.classList.add('active');
  }
  
  apiPost('/api/hyperion', { action: action });
}

function sendFullscreen() {
  vibrate(25);
  apiPost('/api/fullscreen');
}

function sendZoom(level) {
  vibrate(15);
  apiPost('/api/zoom', { action: level });
}

function sendMedia(action) {
  vibrate(20);
  apiPost('/api/media', { action: action });
}

// ---------------------------------------------------------
// Panel 1: Apps CMS (Add, Edit, Delete, Reorder)
// ---------------------------------------------------------
function initAppsCMS() {
  const editModeBtn = document.getElementById('btn-edit-mode');
  const favUrlBtn = document.getElementById('btn-fav-url');
  
  const cancelBtn = document.getElementById('btn-modal-cancel');
  const saveBtn = document.getElementById('btn-modal-save');
  
  // Toggle Edit Mode
  editModeBtn.addEventListener('click', () => {
    isEditMode = !isEditMode;
    editModeBtn.classList.toggle('active', isEditMode);
    vibrate(20);
    // Reload apps layout in edit mode
    initApps();
  });
  
  // Custom URL Star -> Open Add Favorite Modal
  favUrlBtn.addEventListener('click', () => {
    vibrate(15);
    openAddFavModal();
  });
  
  // Modal buttons
  cancelBtn.addEventListener('click', hideModal);
  saveBtn.addEventListener('click', saveModal);
  
  // Close modal when tapping outside card
  document.getElementById('app-modal').addEventListener('click', (e) => {
    if (e.target.id === 'app-modal') {
      hideModal();
    }
  });
}

function openAddFavModal() {
  const customUrlInput = document.getElementById('custom-url-input');
  
  document.getElementById('modal-title').textContent = "Épingler aux Favoris";
  document.getElementById('modal-app-id').value = "";
  document.getElementById('modal-app-name').value = "";
  document.getElementById('modal-app-browser').value = document.getElementById('custom-url-browser').value;
  
  // Auto-prefill URL
  let url = customUrlInput.value.trim();
  if (url && !/^https?:\/\//i.test(url)) {
    url = 'http://' + url;
  }
  document.getElementById('modal-app-url').value = url;
  
  document.getElementById('app-modal').classList.add('active');
}

function openAppEditModal(app) {
  document.getElementById('modal-title').textContent = "Modifier l'Application";
  document.getElementById('modal-app-id').value = app.id;
  document.getElementById('modal-app-name').value = app.name;
  document.getElementById('modal-app-url').value = app.url || "";
  document.getElementById('modal-app-browser').value = app.browser || "firefox";
  
  document.getElementById('app-modal').classList.add('active');
}

function hideModal() {
  vibrate(10);
  document.getElementById('app-modal').classList.remove('active');
}

async function saveModal() {
  vibrate(25);
  const appId = document.getElementById('modal-app-id').value;
  const name = document.getElementById('modal-app-name').value.trim();
  const url = document.getElementById('modal-app-url').value.trim();
  const browser = document.getElementById('modal-app-browser').value;
  
  if (!name || !url) {
    alert("Veuillez remplir le nom et l'adresse URL.");
    return;
  }
  
  let endpoint = '/api/apps/add';
  const payload = { name, url, browser };
  
  if (appId) {
    endpoint = '/api/apps/edit';
    payload.id = appId;
  }
  
  const result = await apiPost(endpoint, payload);
  if (result && result.success) {
    hideModal();
    initApps(); // Refresh apps grid
  } else {
    alert("Une erreur s'est produite lors de l'enregistrement.");
  }
}

async function deleteApp(appId, appName) {
  vibrate([20, 50, 20]);
  const confirmDel = confirm(`Voulez-vous vraiment supprimer "${appName}" des favoris ?`);
  if (!confirmDel) return;
  
  const result = await apiPost('/api/apps/delete', { id: appId });
  if (result && result.success) {
    initApps();
  } else {
    alert("Impossible de supprimer l'application.");
  }
}

async function moveAppInList(currentIndex, direction) {
  vibrate(15);
  const targetIndex = currentIndex + direction;
  
  // Boundary check
  if (targetIndex < 0 || targetIndex >= cachedApps.length) return;
  
  // Swap items in local array
  const temp = cachedApps[currentIndex];
  cachedApps[currentIndex] = cachedApps[targetIndex];
  cachedApps[targetIndex] = temp;
  
  // Compile list of IDs in the new order
  const orderList = cachedApps.map(app => app.id);
  
  // Send order to server
  const result = await apiPost('/api/apps/reorder', { order: orderList });
  if (result && result.success) {
    // Redraw grid immediately
    initApps();
  }
}
