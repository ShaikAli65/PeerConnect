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
set "VENV_DIR=../venv"
if not exist "%FLAG_FILE%" (

    for /d %%D in (../*venv*) do (
        set "VENV_DIR=..\%%D"
        echo Found existing virtual environment: %VENV_DIR%
        goto :venv_found
    )

    echo Setting up virtual environment ...
    set "VENV_DIR=..\.venv"
    %runner% -m venv "%VENV_DIR%"
    echo "Created venv at: %VENV_DIR%"

    :venv_found
    call "%VENV_DIR%\Scripts\activate.bat"
    %runner% -m pip install --upgrade pip
    pip install -r requirements.txt
    echo Setup completed. > "%FLAG_FILE%"
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

REM rmdir /s /q "%VENV_DIR%"
%runner% ../main.py

deactivate

rem set /p CLEAR_SCREEN="Clear screen before setup? (y/n): "
rem if /i "%CLEAR_SCREEN%"=="y" (
rem     cls
rem )

goto :eof