#!/bin/bash

# Expect:
# - /var/lib/rabbitmq shared with rabbitmq container
# - /shared_volume2, shared with web container
# - rabbitmq container started before us, by dependency
# - web containter started after us, by dependency

set -e

echo "Check rabbitmq shared volume"
# mnesia directory is created at rabbitmq startup
test -d /var/lib/rabbitmq/mnesia

echo "Write file for web"
echo "hello from worker: ${HOSTNAME}" >> /shared_volume2/hello-from-worker.${HOSTNAME}
