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
echo "Checking optional dependencies for endpoint file conversion..."

# OAS2 and Postman collection conversion requires npx and two npm packages.
# OAS3 and HAR files work without Node. Skip this step if you only
# intend to provide OAS3 files.
if ! command -v npx >/dev/null 2>&1; then
    echo ""
    echo "  Note: 'npx' was not found on PATH."
    echo "  OAS2/Swagger and Postman collection conversion requires Node.js"
    echo "  and npx. OAS3 (.json/.yaml) and HAR (.har) files work without"
    echo "  them. If you only intend to provide OAS3 files, you can skip"
    echo "  this step."
    echo ""
    read -r -p "  Install npm packages for OAS2/Postman conversion? [y/N]: " \
        _INSTALL_CONVERTERS
    _INSTALL_CONVERTERS="${_INSTALL_CONVERTERS:-N}"
    if [ "$_INSTALL_CONVERTERS" = "y" ] || [ "$_INSTALL_CONVERTERS" = "Y" ]; then
        echo "  Cannot install without npx. Install Node.js from"
        echo "  https://nodejs.org/ and re-run install.sh."
    else
        echo "  Skipping converter package installation."
    fi
else
    read -r -p \
        "  Install npm packages for OAS2/Postman conversion? [y/N]: " \
        _INSTALL_CONVERTERS
    _INSTALL_CONVERTERS="${_INSTALL_CONVERTERS:-N}"
    if [ "$_INSTALL_CONVERTERS" = "y" ] || [ "$_INSTALL_CONVERTERS" = "Y" ]; then
        echo "  Installing swagger2openapi and postman-to-openapi..."
        npm install -g swagger2openapi postman-to-openapi
        echo "  v Converter packages installed"
    else
        echo "  Skipping converter package installation."
        echo "  To install later: npm install -g swagger2openapi postman-to-openapi"
    fi
fi

echo ""
echo "Generating self-signed TLS certificate for the web UI..."
.venv/bin/python3 -c "
from infrastructure.web_ui.tls import ensure_tls_cert
cert, key = ensure_tls_cert('.', '127.0.0.1')
print(f'  v Certificate: {cert}')
print(f'  v Private key: {key}')
"
echo "  To regenerate for a different host, run: ui ssl regenerate"

echo ""
echo "Setup complete."
echo "Run tally with: .venv/bin/python3 tally.py"
