#!/bin/bash
# ------------------------------------------------------------------------------
# StockPulse - Quick Local Runner
# ------------------------------------------------------------------------------
set -e

cd "$(dirname "$0")"

echo "=== Starting StockPulse Cloud Shop Inventory ==="

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

echo "Launching application on http://localhost:5000 ..."
.venv/bin/python3 app.py
