#!/bin/sh
# Starts GAIA CascadeLens on macOS or Linux. Needs only Python 3.
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
        exec "$py" serve.py "$@"
    fi
done
echo "Python 3 was not found on this computer."
echo "Install it from https://www.python.org/downloads/ and run this file again."
exit 1
