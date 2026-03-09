#!/bin/sh
set -e

# Configure git to trust all directories at runtime, after volumes are mounted
git config --global --add safe.directory '*'

exec "$@"