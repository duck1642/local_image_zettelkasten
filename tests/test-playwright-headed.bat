@echo off
setlocal
cd /d "%~dp0..\frontend"
npm run test:playwright:headed
exit /b %ERRORLEVEL%
