@echo off
setlocal
cd /d "%~dp0..\frontend"
npm run test:large-vault
exit /b %ERRORLEVEL%
