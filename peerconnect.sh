source ./env/bin/activate.fish

FLAG_FILE="setup_completed.txt"

if [ ! -f "$FLAG_FILE" ]; then
    echo "Setting up..."
    python3 -m pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install PyQt5
    echo "Setup completed." > "$FLAG_FILE"
fi

python3 main.py


# chmod +x start_app.sh