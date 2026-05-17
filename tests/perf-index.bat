@echo off
setlocal
cd /d "%~dp0.."
python tests\perf\index_perf.py %*
exit /b %ERRORLEVEL%
