#!/bin/sh
set -eu
exec docker compose --env-file /opt/clashinfobot/shared/.env \
    -f /opt/clashinfobot/current/compose.server.yaml "$@"
