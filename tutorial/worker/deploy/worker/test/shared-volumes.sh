#!/bin/bash

# Expect:
# - /var/lib/rabbitmq shared with rabbitmq container
# - rabbitmq container started before us, by dependency

set -e

echo "Check rabbitmq shared volume"
# mnesia directory is created at rabbitmq startup
test -d /var/lib/rabbitmq/mnesia
