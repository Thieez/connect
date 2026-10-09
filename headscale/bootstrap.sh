#!/bin/sh
set -eu

headscale serve &
server_pid=$!

shutdown() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" || true
}
trap shutdown INT TERM

until headscale health >/dev/null 2>&1; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    wait "$server_pid"
    exit 1
  fi
  sleep 1
done

users=$(headscale users list --name connect --output json)
if ! printf '%s' "$users" | grep -q '"id"'; then
  headscale users create connect
fi

key1=$(headscale preauthkeys create --user 1 --expiration 24h)
key2=$(headscale preauthkeys create --user 1 --expiration 24h)

printf 'CONNECT_DEVICE_1_AUTHKEY=%s\n' "$key1"
printf 'CONNECT_DEVICE_2_AUTHKEY=%s\n' "$key2"

wait "$server_pid"
