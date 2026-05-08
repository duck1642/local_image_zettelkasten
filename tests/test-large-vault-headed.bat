@echo off
setlocal
cd /d "%~dp0..\frontend"
npm run test:large-vault:headed
exit /b %ERRORLEVEL%
