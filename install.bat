@echo off
setlocal enabledelayedexpansion

:: === Color Setup ===
:: 0 = Black, 7 = White, 2 = Green, 6 = Yellow, 4 = Red, B = Aqua
color 0B

set PACKAGES=pyqt6 psutil gputil
set FAILED=0
set VENV=venv

cls
echo ============================
echo    BytePurge Installer    
echo ============================
echo.

:: Check for Python
where python >nul 2>nul
if errorlevel 1 (
    color 0C
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.7+ and add it to your system PATH.
    pause
    exit /b 1
)

echo [INFO] Python detected, proceeding...
echo.

:: Simulate progress function
set PROGRESS=0
:progress_loop
if %PROGRESS% GEQ 100 goto install_packages
set /a PROGRESS+=5
set /p="Installing packages: %PROGRESS%%% " <nul
ping -n 2 localhost >nul
set /p="[1G[K" <nul
goto progress_loop

:install_packages
echo Installing required Python packages...

for %%P in (%PACKAGES%) do (
    echo Installing %%P ...
    python -m pip install --upgrade %%P
    if errorlevel 1 set FAILED=1
)

:: Handle virtualenv fallback if install failed
if "!FAILED!"=="1" (
    echo.
    color 0E
    echo [WARN] Some packages failed to install using system Python.
    echo Attempting with isolated virtual environment...

    if not exist %VENV% (
        echo Creating virtual environment...
        python -m venv %VENV%
    )

    echo Activating virtual environment...
    call %VENV%\Scripts\activate.bat

    echo Upgrading pip inside venv...
    python -m pip install --upgrade pip

    echo Installing packages inside virtual environment...
    for %%P in (%PACKAGES%) do (
        pip install --upgrade %%P
    )

    echo.
    echo Launching BytePurge (virtual environment)...
    python main.py
    goto :EOF
)

echo.
color 0A
echo All packages installed successfully.
echo Launching BytePurge...
python main.py
