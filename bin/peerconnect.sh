source ./env/bin/activate.fish
source ./env/bin/activate

FLAG_FILE="setup_completed.txt"

if [ ! -f "$FLAG_FILE" ]; then
    echo "Setting up..."
    python3 -m pip install --upgrade pip
    python3 -m venv env
    pip install websockets
    pip install requests
    pip install PyQt5
    pip install tqdm
    echo "Setup completed." > "$FLAG_FILE"
fi
cd ..
python main.py

# chmod +x start_app.sh
