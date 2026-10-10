#!/bin/zsh
cd -- "$(dirname "$0")" || exit 1
exec python3 scripts/stop_group_session.py
