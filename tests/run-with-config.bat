@echo off
setlocal
if "%~1"=="" (
  echo Usage: tests\run-with-config.bat path\to\config.yaml [command...]
  exit /b 2
)
set "LMZ_CONFIG_PATH=%~f1"
shift
if "%~1"=="" (
  echo LMZ_CONFIG_PATH=%LMZ_CONFIG_PATH%
  echo Run your backend/frontend command in this shell with the variable above.
  exit /b 0
)
%*
exit /b %ERRORLEVEL%
