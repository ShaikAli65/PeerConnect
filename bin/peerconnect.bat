@echo off
setlocal enabledelayedexpansion

:: Configuration section
set "script_dir=%~dp0"
set "base_dir=%script_dir%.."
for %%A in ("%base_dir%") do set "base_dir=%%~fA"
set "venv_dir=%base_dir%\.venv"
set "req_file=%base_dir%\requirements.txt"
set "flag_file=%script_dir%.setup_completed"
set "app_module=src"

:: Check for existing setup
if exist "%flag_file%" (
    echo Existing setup detected. Launching application...
    call "%venv_dir%\Scripts\activate.bat" && (
        cd /d "%base_dir%"
        python -m "%app_module%"
        deactivate
    )
    exit /b 0
)

:: Validate Python installation
set "py_cmd=python"
where python >nul 2>&1 || (
    where python3 >nul 2>&1 && set "py_cmd=python3" || (
        echo Error: Python not found in PATH
        exit /b 1
    )
)

:: Verify Python version
%py_cmd% -c "import sys; exit(0) if sys.version_info >= (3,6) else exit(1)" || (
    echo Error: Python 3.6+ required
    exit /b 1
)

:: Validate requirements.txt exists
if not exist "%req_file%" (
    echo Error: requirements.txt not found in project root
    exit /b 1
)

:: Setup process
echo Initializing new setup...
echo Creating virtual environment...
%py_cmd% -m venv "%venv_dir%" || (
    echo Failed to create virtual environment
    exit /b 1
)

call "%venv_dir%\Scripts\activate.bat"
echo Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%req_file%" --quiet || (
    echo Failed to install requirements
    exit /b 1
)

:: Create setup completion flag
echo. > "%flag_file%"
echo Setup completed successfully. Created verification flag.

:: Launch application
cd /d "%base_dir%"
python -m "%app_module%" || (
    echo Application failed to start
    exit /b 1
)

:: Cleanup
deactivate
echo.
set /p "clear=Clear screen? [y/N]: "
if /i "!clear!"=="y" cls

endlocal