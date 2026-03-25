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
echo "Building frontend..."

# Check for Node and npm
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: 'node' is not installed. Node.js is required to build the web UI."
    echo "Install Node.js from https://nodejs.org/ and re-run install.sh."
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: 'npm' is not installed. npm is required to build the web UI."
    echo "Install Node.js (which includes npm) and re-run install.sh."
    exit 1
fi

# Save current directory and switch to ui/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/ui"

npm install
npm run build

# Return to original directory
cd "$SCRIPT_DIR"

echo "Frontend build complete. Static files written to web/static/."

echo ""
echo "Setup complete."
echo "Run tally with: .venv/bin/python3 tally.py"
