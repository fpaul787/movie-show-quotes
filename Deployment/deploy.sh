
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

npm --prefix frontend install
npm --prefix frontend run build

APP_ENV=prod "$VENV_PY" manage.py check --deploy
APP_ENV=prod "$VENV_PY" manage.py migrate --noinput
APP_ENV=prod "$VENV_PY" manage.py seed_quotes
APP_ENV=prod "$VENV_PY" manage.py collectstatic --noinput

sudo apache2ctl configtest
sudo systemctl reload apache2
