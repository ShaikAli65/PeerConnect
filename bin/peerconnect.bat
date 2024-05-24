@echo off

set "FLAG_FILE=setup_completed.txt"

if not exist "%FLAG_FILE%" (
    echo Setting up...
    python -m pip install --upgrade pip
    pip install websockets
    pip install PyQt5
    pip install tqdm
    echo Setup completed. > "%FLAG_FILE%"
)
cd ..
python main.py
exit
