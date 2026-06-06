// client.js - TV Launcher Remote Controller Logic

// Active modifiers state
const activeModifiers = {
  ctrl: false,
  alt: false,
  super: false
};

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
    const apps = data.apps || [];
    countBadge.textContent = apps.length;
    
    if (apps.length === 0) {
      grid.innerHTML = '<p class="loading-placeholder">Aucune application configurée.</p>';
      return;
    }
    
    apps.forEach(app => {
      const btn = document.createElement('button');
      btn.className = 'app-item-btn';
      
      const iconWrap = document.createElement('div');
      iconWrap.className = 'app-icon-wrapper';
      
      const img = document.createElement('img');
      // If path starts with icons/, serve via server. Or fallback to standard layout.
      img.src = app.icon ? `/${app.icon}` : '/icons/firefox.png';
      img.onerror = () => { img.src = '/icons/firefox.png'; };
      
      iconWrap.appendChild(img);
      
      const name = document.createElement('span');
      name.className = 'app-name';
      name.textContent = app.name;
      
      btn.appendChild(iconWrap);
      btn.appendChild(name);
      
      btn.addEventListener('click', () => {
        vibrate(25);
        launchApp(app.id);
      });
      
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
  
  let padBounds = null;
  let isDragging = false;
  let joystickX = 0; // Value from -1 to 1 representing displacement
  let joystickY = 0; 
  let movementTimer = null; // Timer for continuous pointer movement

  // Initialize bounds on touch start to support scrolling/rotations
  const updatePadBounds = () => {
    padBounds = pad.getBoundingClientRect();
  };

  const onDragStart = (e) => {
    isDragging = true;
    pad.classList.add('active');
    updatePadBounds();
    onDragMove(e);
    vibrate(10);
    
    // Start interval to continuously move pointer based on joystick tilt
    if (movementTimer) clearInterval(movementTimer);
    movementTimer = setInterval(moveMouseFromJoystick, CONFIG.mousePollRateMs);
  };

  const onDragMove = (e) => {
    if (!isDragging) return;
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
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
  };

  const onDragEnd = () => {
    if (!isDragging) return;
    isDragging = false;
    pad.classList.remove('active');
    
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
  };

  // Joystick Events (Mouse + Touch)
  pad.addEventListener('touchstart', onDragStart, { passive: false });
  window.addEventListener('touchmove', onDragMove, { passive: false });
  window.addEventListener('touchend', onDragEnd);
  
  pad.addEventListener('mousedown', onDragStart);
  window.addEventListener('mousemove', onDragMove);
  window.addEventListener('mouseup', onDragEnd);

  // Send relative mouse movement to server
  function moveMouseFromJoystick() {
    if (!isDragging) return;
    
    // Check deadzone
    const dist = Math.sqrt(joystickX * joystickX + joystickY * joystickY) * CONFIG.joystickMaxDist;
    if (dist < CONFIG.joystickDeadzone) return;
    
    // Speed curves based on displacement (non-linear scaling for fine control vs fast panning)
    const speedMultiplier = 25; // Speed multiplier for mouse
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
  const toggle = document.getElementById('gyro-toggle');
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

  toggle.addEventListener('change', async () => {
    if (toggle.checked) {
      await startGyro();
    } else {
      stopGyro();
    }
  });

  async function startGyro() {
    // Check if device orientation API is available
    if (!window.DeviceOrientationEvent) {
      status.textContent = 'Erreur : Capteur non supporté par ce navigateur.';
      toggle.checked = false;
      return;
    }

    // iOS requires permission dialog
    if (typeof DeviceOrientationEvent.requestPermission === 'function') {
      try {
        const permission = await DeviceOrientationEvent.requestPermission();
        if (permission !== 'granted') {
          status.textContent = 'Accès au capteur refusé.';
          toggle.checked = false;
          return;
        }
      } catch (err) {
        status.textContent = 'Erreur autorisation gyroscope : ' + err.message;
        toggle.checked = false;
        return;
      }
    }

    isGyroActive = true;
    baseBeta = null; // Re-calibrate on startup
    calibBtn.style.display = 'block';
    status.textContent = 'Initialisation... Mettez le téléphone à plat.';
    window.addEventListener('deviceorientation', handleOrientation);
    vibrate([30, 50, 30]);
  }

  function stopGyro() {
    isGyroActive = false;
    calibBtn.style.display = 'none';
    status.textContent = 'Désactivé. Utilisez les capteurs de votre téléphone pour diriger la souris.';
    window.removeEventListener('deviceorientation', handleOrientation);
    vibrate(30);
  }

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
      // Map Up/Down tilt to Mouse Y movement
      dy = dBeta * gyroSensitivity;
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
