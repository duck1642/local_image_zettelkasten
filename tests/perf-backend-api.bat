@echo off
setlocal
cd /d "%~dp0.."
python tests\perf\backend_api_perf.py %*
exit /b %ERRORLEVEL%
