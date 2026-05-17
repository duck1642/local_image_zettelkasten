import os from 'os';
import fs from 'fs';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const rootDir = path.resolve(__dirname, '..', '..', '..');
const frontendDir = path.join(rootDir, 'frontend');
const appPath = process.env.LMZ_TAURI_APP_PATH || path.join(frontendDir, 'src-tauri', 'target', 'debug', process.platform === 'win32' ? 'app.exe' : 'app');
const backendUrl = process.env.LMZ_PERF_BACKEND_URL || 'http://127.0.0.1:8000';
let tauriDriver;
let backendProcess;
let exit = false;

export const config = {
  host: '127.0.0.1',
  port: 4444,
  specs: ['./specs/perf.e2e.js'],
  maxInstances: 1,
  capabilities: [
    {
      maxInstances: 1,
      'tauri:options': {
        application: appPath
      }
    }
  ],
  reporters: ['spec'],
  framework: 'mocha',
  mochaOpts: {
    ui: 'bdd',
    timeout: 180000
  },
  onPrepare: () => {
    const result = spawnSync('npm', ['run', 'tauri', 'build', '--', '--debug', '--no-bundle'], {
      cwd: frontendDir,
      stdio: 'inherit',
      shell: true,
      env: {
        ...process.env,
        LMZ_SKIP_SIDECAR: '1'
      }
    });
    if (result.status !== 0) {
      throw new Error(`Tauri debug build failed with exit code ${result.status}`);
    }
  },
  beforeSession: async () => {
    await startBackend();
    const defaultExecutable = path.join(os.homedir(), '.cargo', 'bin', process.platform === 'win32' ? 'tauri-driver.exe' : 'tauri-driver');
    const executable = process.env.TAURI_DRIVER || (fs.existsSync(defaultExecutable) ? defaultExecutable : 'tauri-driver');
    const args = [];
    if (process.env.MSEDGEDRIVER_PATH) {
      args.push('--native-driver', process.env.MSEDGEDRIVER_PATH);
    }
    tauriDriver = spawn(executable, args, {
      stdio: [null, process.stdout, process.stderr],
      env: {
        ...process.env,
        LMZ_SKIP_SIDECAR: '1'
      }
    });
    tauriDriver.on('error', (error) => {
      console.error('tauri-driver error:', error);
      process.exit(1);
    });
    tauriDriver.on('exit', (code) => {
      if (!exit) {
        console.error('tauri-driver exited with code:', code);
        process.exit(1);
      }
    });
    await waitForTauriDriver();
  },
  afterSession: () => {
    closeTauriDriver();
    stopBackend();
  }
};

function closeTauriDriver() {
  exit = true;
  tauriDriver?.kill();
}

async function startBackend() {
  if (!process.env.LMZ_PERF_CONFIG_PATH) {
    throw new Error('LMZ_PERF_CONFIG_PATH is required');
  }
  if (backendProcess && backendProcess.exitCode === null) return;
  const env = {
    ...process.env,
    LMZ_CONFIG_PATH: process.env.LMZ_PERF_CONFIG_PATH,
    PYTHONPATH: path.join(rootDir, 'backend') + path.delimiter + (process.env.PYTHONPATH || '')
  };
  backendProcess = spawn(process.env.PYTHON || 'python', [path.join(rootDir, 'backend', 'web_api.py')], {
    cwd: path.join(rootDir, 'backend'),
    env,
    stdio: 'ignore',
    windowsHide: true
  });
  await waitForBackend();
}

async function waitForBackend() {
  const deadline = Date.now() + 60000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${backendUrl}/api/session-key`);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw lastError || new Error(`Backend did not become ready at ${backendUrl}`);
}

async function waitForTauriDriver() {
  const deadline = Date.now() + 30000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch('http://127.0.0.1:4444/status');
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw lastError || new Error('tauri-driver did not become ready on 127.0.0.1:4444');
}

function stopBackend() {
  if (!backendProcess || backendProcess.exitCode !== null) return;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(backendProcess.pid)], { stdio: 'ignore', windowsHide: true });
  } else {
    backendProcess.kill();
  }
}

function onShutdown(fn) {
  const cleanup = () => {
    try {
      fn();
    } finally {
      process.exit();
    }
  };
  process.on('exit', cleanup);
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
  process.on('SIGHUP', cleanup);
  process.on('SIGBREAK', cleanup);
}

onShutdown(() => {
  closeTauriDriver();
  stopBackend();
});
