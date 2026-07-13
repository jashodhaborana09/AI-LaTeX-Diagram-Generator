#!/bin/sh
set -eu

APP_PORT="${APP_PORT:-5000}"
PORT="${PORT:-8080}"
export APP_PORT PORT

python scripts/validate_env.py

gunicorn --config gunicorn.conf.py --bind "127.0.0.1:${APP_PORT}" backend.app:app &
GUNICORN_PID="$!"

envsubst '${PORT} ${APP_PORT}' < nginx/cloud.conf.template > /tmp/nginx/nginx.conf
nginx -c /tmp/nginx/nginx.conf -g 'daemon off;' &
NGINX_PID="$!"

terminate() {
    kill "$NGINX_PID" "$GUNICORN_PID" 2>/dev/null || true
    wait "$NGINX_PID" "$GUNICORN_PID" 2>/dev/null || true
}

trap terminate INT TERM

while kill -0 "$NGINX_PID" 2>/dev/null && kill -0 "$GUNICORN_PID" 2>/dev/null; do
    sleep 1
done

terminate
exit 1
