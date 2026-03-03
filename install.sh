#!/bin/bash
set -e

echo "Tally - Setup"
echo "============="

# Check Python version
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi
echo "  v Python $PYTHON_VERSION"

# Create venv if it does not already exist
if [ -d ".venv" ]; then
    echo "  v .venv already exists, skipping creation"
else
    echo "  Creating .venv..."
    "$PYTHON" -m venv .venv
    echo "  v .venv created"
fi

# Install Python dependencies
echo "  Installing dependencies from requirements.txt..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "  v Dependencies installed"

echo ""
echo "Setup complete."
echo "Run tally with: .venv/bin/python3 tally.py"
