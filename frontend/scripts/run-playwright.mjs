import { spawn } from 'node:child_process';

const host = '127.0.0.1';
const port = '5173';
const baseUrl = `http://${host}:${port}`;

function run(command, args, options = {}) {
  return spawn(command, args, {
    stdio: 'inherit',
    windowsHide: true,
    shell: false,
    ...options
  });
}

async function isReady() {
  try {
    const response = await fetch(baseUrl);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer() {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 120_000) {
    if (await isReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Vite did not become ready at ${baseUrl}`);
}

async function stop(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill();
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
      resolve();
    }, 5000);
    child.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

let server = null;
let serverStarted = false;

try {
  if (!(await isReady())) {
    server = run(process.execPath, ['./node_modules/vite/bin/vite.js', '--host', host, '--port', port]);
    serverStarted = true;
    await waitForServer();
  }

  const playwright = run(
    process.execPath,
    ['./node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.config.ts', ...process.argv.slice(2)],
    {
      env: {
        ...process.env,
        NODE_PATH: './node_modules',
        PW_SKIP_WEBSERVER: '1'
      }
    }
  );

  const exitCode = await new Promise((resolve) => {
    playwright.once('exit', (code, signal) => {
      if (signal) resolve(1);
      else resolve(code ?? 1);
    });
  });
  process.exitCode = exitCode;
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  if (serverStarted) await stop(server);
}
