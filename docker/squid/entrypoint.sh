#!/usr/bin/env bash

set -e

# Prepare the cache using Squid.
echo "Initializing cache..."
squid -z

# Give the Squid cache some time to rebuild.
sleep 5

# Launch squid
echo "Starting Squid..."

exec squid -NYCd 1
