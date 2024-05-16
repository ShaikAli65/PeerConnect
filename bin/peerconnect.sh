#!/bin/bash

source ./env/bin/activate.fish
source ./env/bin/activate

FLAG_FILE="setup_completed.txt"

if [ ! -f "$FLAG_FILE" ]; then
    echo "Setting up..."
    python3 -m pip install --upgrade pip
    pip install venv
    python3 -m venv env
    pip install websockets
    pip install PyQt5
    pip install tqdm
    echo "Setup completed." > "$FLAG_FILE"
fi

cd ..

if command -v python3 &>/dev/null; then
    python3 main.py
elif command -v python &>/dev/null; then
    python main.py
else
    echo "Python not found. Please install Python 3."
fi
