#!/bin/sh
export STICKARU_DATA="${XDG_DATA_HOME:-$HOME/.local/share}/stickaru"
export PYTHONPATH="$(echo /app/lib/python3*/site-packages)"
exec python3 /app/share/stickaru/bibliotheque.py "$@"
