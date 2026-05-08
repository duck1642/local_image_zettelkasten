@echo off
setlocal
cd /d "%~dp0..\frontend"
npm run test:playwright:ui
exit /b %ERRORLEVEL%
