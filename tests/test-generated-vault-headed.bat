@echo off
setlocal
cd /d "%~dp0.."
npm --prefix frontend run test:generated-vault:headed
exit /b %ERRORLEVEL%
