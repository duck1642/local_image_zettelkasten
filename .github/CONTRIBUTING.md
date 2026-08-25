# Contributing

Thanks for your interest in Local Media Zettelkasten (LMZ).

Contributions are welcome for bug fixes, documentation, tests, and focused improvements that fit the current local-first architecture.

## Before You Start

- Check existing issues before opening a new one.
- Open an issue before starting a large feature or architectural change.
- Keep changes focused and explain user-facing behavior clearly.
- Never commit personal media, vault data, credentials, cookies, tokens, sensitive logs, model files, or generated builds.

## Development Setup

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[windows,tauri]"
.\.venv\Scripts\python.exe -m pip install pytest

cd frontend
npm install
npm exec playwright install chromium
cd ..
```

The commands above use Windows PowerShell. On Linux or macOS, use the equivalent virtual-environment commands, replace the Python extras with `.[unix,tauri]`, and install the platform-specific Tauri dependencies.

## Local Checks

Run the readiness report:

```powershell
.\.venv\Scripts\python.exe tools\maintenance\lmz_readiness_check.py --non-interactive
```

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\backend
```

Run frontend checks and tests:

```powershell
.\.venv\Scripts\Activate.ps1

cd frontend
npm run check
npm run build
npm run test:mock-vault
npm run test:playwright
cd ..
```

Activate the project environment before frontend Playwright tests or the sidecar build because those npm scripts call `python` internally.

## Issues and Pull Requests

- For bugs, include reproduction steps, expected behavior, actual behavior, and relevant environment details.
- Remove credentials and personal paths from logs before sharing them.
- Keep pull requests focused and describe what changed, why, and which checks were run.
- Update the documentation when user-facing behavior changes.
- Do not include unrelated formatting changes or generated files.
