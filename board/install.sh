#!/usr/bin/env bash
# Install application files only. Weights and llama-server are supplied separately.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/orangepi-rpg-aichat
id orangepi-chat >/dev/null 2>&1 || useradd --system --home-dir "$prefix" --shell /usr/sbin/nologin orangepi-chat
install -d -m 0750 -o root -g orangepi-chat "$prefix" "$prefix"/{app,config,scripts,models,bin,templates}
install -d -m 0750 -o orangepi-chat -g orangepi-chat "$prefix/logs"
if systemctl is-active --quiet orangepi-rpg-aichat.service; then
    echo 'Stop orangepi-rpg-aichat.service before updating application files'; exit 1
fi
for file in app.py engine_gguf.py model_settings.py index.html requirements.txt; do
    install -m 0640 -o root -g orangepi-chat "$source_dir/$file" "$prefix/app/$file"
done
install -m 0750 -o root -g orangepi-chat "$source_dir/serve.sh" "$prefix/scripts/serve.sh"
if [[ ! -f "$prefix/config/active-model.env" ]]; then
    install -m 0640 -o root -g orangepi-chat "$source_dir/active-model.env.example" "$prefix/config/active-model.env"
fi
python3 -m venv "$prefix/venv"
"$prefix/venv/bin/python" -m pip install -r "$prefix/app/requirements.txt"
chmod o+x "$prefix/venv"
install -m 0644 "$source_dir/orangepi-rpg-aichat.service" /etc/systemd/system/orangepi-rpg-aichat.service
systemctl daemon-reload
echo 'Application installed. Supply llama-server and GGUF, then enable the service as documented.'
