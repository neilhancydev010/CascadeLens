@echo off
title GAIA CascadeLens
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python serve.py
    goto done
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 serve.py
    goto done
)
echo.
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and run this file again.
echo.
:done
pause
