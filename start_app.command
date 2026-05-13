#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "Starting BadmintonAI..."
echo "Project: $PROJECT_DIR"

if [ ! -d "venv" ]; then
  echo "No venv found. Creating one..."
  python3 -m venv venv
fi

if [ ! -x "venv/bin/python" ]; then
  echo "Cannot find venv/bin/python. Please recreate the virtual environment."
  exit 1
fi

echo "Installing/updating dependencies..."
venv/bin/python -m pip install -r requirements.txt

echo ""
echo "Launching Streamlit..."
echo "If the browser does not open automatically, visit http://localhost:8501"
echo ""

venv/bin/streamlit run front_page.py
