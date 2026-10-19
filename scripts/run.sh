#!/bin/sh
# One-command launcher. Refuses anything but paper mode via config.yaml.
set -e
cd "$(dirname "$0")/.."
exec python -m aroonbot
