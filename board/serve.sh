#!/usr/bin/env bash
set -euo pipefail
export PATH=/opt/orangepi-rpg-aichat/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONPATH PYTHONHOME
export OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1
exec python -m uvicorn app:app --app-dir /opt/orangepi-rpg-aichat/app --host 127.0.0.1 --port 8000 --workers 1
