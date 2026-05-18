@echo off
setlocal
cd /d "%~dp0.."
python tests\perf\cleanup_perf_artifacts.py %*
exit /b %ERRORLEVEL%
