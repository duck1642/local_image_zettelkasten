@echo off
setlocal
cd /d "%~dp0.."
python tests\perf\compare_perf.py %*
exit /b %ERRORLEVEL%
