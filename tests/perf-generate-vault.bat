@echo off
setlocal
cd /d "%~dp0.."
python tests\generators\generate_test_vault.py %*
exit /b %ERRORLEVEL%
