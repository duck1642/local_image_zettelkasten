@echo off
setlocal
cd /d "%~dp0..\frontend"
npm run test:mock-vault:headed
exit /b %ERRORLEVEL%
