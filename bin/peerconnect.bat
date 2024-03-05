@echo off
set "FLAG_FILE=setup_completed.txt"

if not exist "%FLAG_FILE%" (
    echo Setting up...
    python -m pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install PyQt5
    echo Setup completed. > "%FLAG_FILE%"
)

cd ..
python3 main.py
exit
