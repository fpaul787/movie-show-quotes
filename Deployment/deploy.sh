
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/applications/movie-show-quotes"
VENV_PY="$APP_DIR/env/bin/python"

cd "$APP_DIR"

if [ ! -x "$VENV_PY" ]; then
    echo "Virtual environment Python not found at $VENV_PY"
    exit 1
fi

"$VENV_PY" -m pip install -r requirements.txt
"$VENV_PY" manage.py check --deploy
"$VENV_PY" manage.py migrate --noinput
"$VENV_PY" manage.py collectstatic --noinput

sudo apache2ctl configtest
sudo systemctl reload apache2
