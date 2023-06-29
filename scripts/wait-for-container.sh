#!/usr/bin/env bash

set -e
timeout="${2-60}"
wait_till=$(($(date -d "+${timeout} seconds" +%s) +0))
until [ "$(docker inspect -f "{{.State.Health.Status}}" "${1}")" == "healthy" ]; do
    if [ $(($(date +%s) +0)) -gt $wait_till ]; then
        echo "timeout"
        exit 1
    fi
    echo -n "."
    sleep 2;
done;
echo ""
