#!/usr/bin/env bash
set -e

VENV_PY="env/bin/python"

if [ ! -x "$VENV_PY" ]; then
	echo "Virtual environment python not found at $VENV_PY"
	exit 1
fi

"$VENV_PY" -m pip install -r requirements.txt
"$VENV_PY" movie-show-quotes/manage.py migrate
if [ -d "movie-show-quotes/static" ]; then
  rm -rf movie-show-quotes/static
fi
"$VENV_PY" movie-show-quotes/manage.py collectstatic --noinput
sudo systemctl reload apache2
