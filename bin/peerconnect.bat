@echo off

set "FLAG_FILE=setup_completed.txt"
set "VENV_DIR=venv"

if not exist "%FLAG_FILE%" (
    echo Setting up...
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate.bat"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    echo Setup completed. > "%FLAG_FILE%"
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

cd ..
python main.py

rem Deactivate and remove the virtual environment
deactivate
cd ..
rmdir /s /q "%VENV_DIR%"

exit
