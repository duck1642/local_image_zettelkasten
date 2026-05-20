@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

for /f "usebackq delims=" %%P in (`python tools\maintenance\workspace_launcher.py --choose`) do (
  set "LMZ_CONFIG_PATH=%%P"
)

if "%LMZ_CONFIG_PATH%"=="" (
  echo No workspace selected.
  exit /b 2
)

echo LMZ_CONFIG_PATH=%LMZ_CONFIG_PATH%
python backend\web_api.py
exit /b %ERRORLEVEL%
