#!/bin/bash
clear
# git stash
# git pull

runner="py"
if command -v python3 &>/dev/null; then
    runner="python3"
elif command -v python &>/dev/null; then
    runner="python"
else
    echo "Python not found. Please install Python 3."
    exit 1
fi

install() {
    $runner -m pip install --upgrade pip
    $runner -m pip install -r requirements.txt
}

setup_environment() {
    echo "Setting up..."
    $runner -m venv ../venv
    source ../venv/bin/activate

}

re_setup() {
  rm -rf venv/
  setup_environment
}

if [ ! -f "../venv/bin/activate" ]; then
  setup_environment
fi


if source ./venv/bin/activate 2>/dev/null; then
    echo "Activated Virtual environment..."
else
  re_setup
fi

if lines=$($runner -m pip show websockets PyQt5 tqdm 2>/dev/null | wc -l); then
    echo "Checking for dependencies..."
else
    re_setup
fi


if [ "$lines" -ne 32 ]; then
  echo "installing libs"
  install
fi

$runner ../main.py

deactivate

read -p -r "Clear screen before setup? (y/n): " CLEAR_SCREEN

if [[ "$CLEAR_SCREEN" == [Yy] ]]; then
    clear
fi
 # --force-reinstall
