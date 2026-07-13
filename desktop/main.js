// Electron main process for the reqmesh desktop app.
//
// Boots the Python/FastAPI backend as a child process (configured to serve the
// pre-built SPA from the same origin), waits for it to become healthy, then
// loads it in a native window. The backend is torn down when the app quits.
//
// The web/server deployment does NOT go through this wrapper — see start.sh.

const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const net = require('node:net');
const http = require('node:http');

const REPO_ROOT = path.resolve(__dirname, '..');
const BACKEND_DIR = path.join(REPO_ROOT, 'backend');
const FRONTEND_DIST = path.join(REPO_ROOT, 'frontend', 'dist');
const HOST = '127.0.0.1';

let backendProc = null;
let mainWindow = null;

/** Absolute path to the backend virtualenv's Python, or a bare fallback. */
function resolvePython() {
  const isWin = process.platform === 'win32';
  const venvPython = isWin
    ? path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
    : path.join(BACKEND_DIR, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) return venvPython;
  // Fall back to whatever `python`/`python3` is on PATH.
  return isWin ? 'python' : 'python3';
}

/** Resolve a free TCP port on the loopback interface. */
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on('error', reject);
    srv.listen(0, HOST, () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/** Poll the backend's /health endpoint until it responds or we time out. */
function waitForBackend(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://${HOST}:${port}/health`;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2000, () => req.destroy());
    };
    const retry = () => {
      if (backendProc && backendProc.exitCode !== null) {
        return reject(new Error(`backend exited early (code ${backendProc.exitCode})`));
      }
      if (Date.now() > deadline) return reject(new Error('backend did not become healthy in time'));
      setTimeout(attempt, 400);
    };
    attempt();
  });
}

function startBackend(port) {
  const python = resolvePython();
  const env = {
    ...process.env,
    // Serve the built SPA from the same origin as the API so the renderer's
    // relative `/api` calls resolve without CORS.
    RT_STATIC_DIR: process.env.RT_STATIC_DIR || FRONTEND_DIST,
  };
  const args = ['-m', 'uvicorn', 'app.main:app', '--host', HOST, '--port', String(port)];
  backendProc = spawn(python, args, { cwd: BACKEND_DIR, env, stdio: ['ignore', 'pipe', 'pipe'] });

  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code, signal) => {
    backendProc = null;
    // If the backend dies while the app is up, there's nothing to show — quit.
    if (!app.isQuiting && code !== 0 && signal !== 'SIGTERM') {
      if (mainWindow) {
        dialog.showErrorBox('reqmesh', `Backend process exited unexpectedly (code ${code}).`);
      }
      app.quit();
    }
  });
}

function stopBackend() {
  if (!backendProc) return;
  const proc = backendProc;
  backendProc = null;
  try {
    proc.kill('SIGTERM');
    // Escalate if it hasn't gone after a grace period.
    setTimeout(() => { try { proc.kill('SIGKILL'); } catch { /* already gone */ } }, 4000);
  } catch { /* already gone */ }
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0a0a0a',
    title: 'reqmesh',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });

  // Open target=_blank / external links in the user's browser, not a new
  // Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.loadURL(`http://${HOST}:${port}/`);
}

async function boot() {
  if (!fs.existsSync(path.join(FRONTEND_DIST, 'index.html'))) {
    dialog.showErrorBox(
      'reqmesh',
      `Frontend build not found at:\n${FRONTEND_DIST}\n\nBuild it first: cd frontend && npm run build`
    );
    app.quit();
    return;
  }
  try {
    const port = process.env.RT_PORT ? Number(process.env.RT_PORT) : await findFreePort();
    startBackend(port);
    await waitForBackend(port);
    createWindow(port);
  } catch (err) {
    dialog.showErrorBox('reqmesh', `Failed to start:\n${err.message}`);
    stopBackend();
    app.quit();
  }
}

// Single-instance: focus the existing window instead of spawning a second app.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(boot);

  app.on('activate', () => {
    // macOS: re-create a window when the dock icon is clicked and none are open.
    if (BrowserWindow.getAllWindows().length === 0 && backendProc) {
      const port = backendProc.spawnargs.includes('--port')
        ? Number(backendProc.spawnargs[backendProc.spawnargs.indexOf('--port') + 1])
        : Number(process.env.RT_PORT);
      if (port) createWindow(port);
    }
  });

  app.on('window-all-closed', () => {
    // Standard desktop behaviour: quit on all platforms except macOS.
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('before-quit', () => { app.isQuiting = true; stopBackend(); });
  app.on('quit', stopBackend);
}

// Make sure a crash/interrupt doesn't orphan the backend.
process.on('exit', stopBackend);
process.on('SIGINT', () => { stopBackend(); process.exit(0); });
process.on('SIGTERM', () => { stopBackend(); process.exit(0); });
