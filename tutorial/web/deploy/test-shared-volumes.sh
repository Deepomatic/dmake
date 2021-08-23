#!/bin/bash

# Expect:
# - ${SHARED_VOLUME_PATH}, shared with worker containers
# - 2 worker variants containers started before us, by dependency

set -e

SHARED_VOLUME_PATH=$1

echo "Check worker shared volume"
cat "${SHARED_VOLUME_PATH}"/hello-from-worker.*
test $(ls -1 ${SHARED_VOLUME_PATH}/hello-from-worker.* | wc -l) -eq 2
