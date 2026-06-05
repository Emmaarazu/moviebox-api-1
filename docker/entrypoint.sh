#!/bin/sh
set -e

if [ "$#" -eq 0 ] || [ "$1" = "api" ] || [ "$1" = "serve" ]; then
  if [ "$1" = "api" ] || [ "$1" = "serve" ]; then
    shift
  fi
  exec uvicorn moviebox_service:app --app-dir /app --host 0.0.0.0 --port "${PORT:-8095}" "$@"
fi

exec moviebox "$@"
