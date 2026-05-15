@echo off
cd /d "%~dp0.."

:: Intentar con uv en la ruta comun de Windows
set UV_PATH=%USERPROFILE%\.local\bin\uv.exe
if not exist "%UV_PATH%" set UV_PATH=%LOCALAPPDATA%\uv\bin\uv.exe
if not exist "%UV_PATH%" set UV_PATH=uv

"%UV_PATH%" run python scripts\launcher.pyw
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR al iniciar el panel ^(codigo %ERRORLEVEL%^).
    echo Asegurate de haber ejecutado: uv sync
    pause
)
