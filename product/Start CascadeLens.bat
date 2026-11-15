@echo off
title GAIA CascadeLens
cd /d "%~dp0"

rem Python is used when it really runs. Windows ships a "python" that only opens the Store, so it is tested, not just looked for.
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if not errorlevel 1 (
    python serve.py
    goto done
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if not errorlevel 1 (
    py -3 serve.py
    goto done
)

rem No Python: the PowerShell that comes with Windows runs the same small server, so nothing has to be installed.
where powershell >nul 2>nul
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File serve.ps1
    goto done
)

echo.
echo Neither Python 3 nor PowerShell was found on this computer.
echo Install Python from https://www.python.org/downloads/ and run this file again.
echo.
:done
pause
