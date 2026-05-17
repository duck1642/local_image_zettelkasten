@echo off
setlocal
if "%~1"=="" (
  echo Usage: tests\perf-tauri-webview.bat tests\generated\NNN-name\config.yaml
  exit /b 2
)
cd /d "%~dp0.."
python tests\perf\check_tauri_webdriver.py
if errorlevel 1 exit /b %ERRORLEVEL%
set "LMZ_PERF_CONFIG_PATH=%~f1"
set "LMZ_SKIP_SIDECAR=1"
cd /d "%~dp0perf\tauri_webview_perf"
if not exist "node_modules\webdriverio" (
  echo WebdriverIO dependencies are missing. Run: npm install --prefix tests\perf\tauri_webview_perf
  exit /b 1
)
npm test
exit /b %ERRORLEVEL%
