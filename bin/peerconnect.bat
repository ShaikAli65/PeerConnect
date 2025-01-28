@echo off
setlocal

:: Check for Python installation
set "runner=py"
where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set "runner=python3"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "runner=python"
    ) else (
        echo Python not found. Please install Python 3.
        exit /b 1
    )
)

:: Function to install dependencies
:install
%runner% -m pip install --upgrade pip >nul
echo Found pip
echo Installing missing dependencies
%runner% -m pip install -r "%base_dir%\bin\requirements.txt" >nul
echo Installed dependencies successfully
goto :eof

:: Get the base directory (parent of the script's directory)
set "script_dir=%~dp0"
set "base_dir=%script_dir:~0,-1%"
for %%A in ("%base_dir%") do set "base_dir=%%~dpA"
set "base_dir=%base_dir:~0,-1%"
set "venv_dir=%base_dir%\venv"

:: Function to set up the virtual environment
:setup_environment
echo Setting up...
%runner% -m venv "%venv_dir%"
call "%venv_dir%\Scripts\activate.bat"
goto :eof

:: Function to re-setup the virtual environment
:re_setup
rmdir /s /q "%venv_dir%"
call :setup_environment
goto :eof

:: Check if the virtual environment is already set up
if not exist "%venv_dir%\Scripts\activate.bat" (
    call :setup_environment
)

:: Activate the virtual environment
if exist "%venv_dir%\Scripts\activate.bat" (
    call "%venv_dir%\Scripts\activate.bat"
    echo Activated Virtual environment...
) else (
    call :re_setup
)

:: Check for dependencies
set "lines=0"
for %%L in (websockets PyQt5 tqdm) do (
    %runner% -m pip show %%L >nul 2>&1
    if errorlevel 1 (
        call :re_setup
        goto :check_dependencies
    )
)
:check_dependencies
for /f "delims=" %%i in ('%runner% -m pip show websockets PyQt5 tqdm 2^>nul ^| find /c /v ""') do set "lines=%%i"

if %lines% neq 32 (
    call :install
)

:: Change to the base directory and run the main Python script
cd /d "%base_dir%"
%runner% main.py

:: Deactivate the virtual environment
deactivate

:: Ask user if they want to clear the screen
set /p CLEAR_SCREEN="Clear screen before setup? (y/n): "
if /i "%CLEAR_SCREEN%"=="y" (
    cls
)

endlocal
