#!/bin/bash

# Expect:
# - /shared_volume2, shared with worker containers
# - 2 worker variants containters started before us, by dependency

set -e

echo "Check worker shared volume"
cat /shared_volume2/hello-from-worker.*
test $(ls -1 /shared_volume2/hello-from-worker.* | wc -l) -eq 2
