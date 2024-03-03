@echo off

python -m pip install --upgrade pip
pip install websockets
pip install requests
pip install asyncio
pip install PyQt5
pip install tqdm
python3 main.py
exit