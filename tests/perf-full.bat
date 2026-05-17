@echo off
setlocal
cd /d "%~dp0.."
python tests\perf\full_perf.py %*
exit /b %ERRORLEVEL%
