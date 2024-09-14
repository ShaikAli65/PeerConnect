@echo off
@REM git stash
git pull

set "runner=py"

rem Check if python3 is available
where python3 >nul 2>&1
if %errorlevel%==0 (
    set "runner=python3"
) else (
    rem Check if python is available
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "runner=python"
    ) else (
        echo Python not found. Please install Python 3.
        exit /b 1
    )
)

echo Using %runner% as the Python interpreter.

set "FLAG_FILE=setup_completed.txt"
set "VENV_DIR=..\venv"
if not exist "%FLAG_FILE%" (
    if not exist "%VENV_DIR%" (
        echo Setting up virtual environment ...
        %runner% -m venv "%VENV_DIR%"
        if errorlevel 1 (
            echo Failed to create virtual environment.
            exit /b 1
        )
        echo Created venv at: %VENV_DIR%
    ) else (
        echo Found existing virtual environment: %VENV_DIR%
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

%runner% -m pip install --upgrade pip
%runner% -m pip install -r requirements.txt

echo Setup completed. > "%FLAG_FILE%"

echo "using runner=%runner%"

%runner% ../main.py

call "%VENV_DIR%\Scripts\deactivate.bat"
goto :eof
