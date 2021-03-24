#!/bin/bash
if [ ! -z "${TEST_RABBITMQ_PORT_5672_TCP}" ]; then
    export AMQP_URL=$(echo $TEST_RABBITMQ_PORT_5672_TCP | sed "s|\(.*\)://\(.*\)|amqp://$TEST_RABBITMQ_ENV_RABBITMQ_DEFAULT_USER:$TEST_RABBITMQ_ENV_RABBITMQ_DEFAULT_PASS@\2/$TEST_RABBITMQ_ENV_RABBITMQ_DEFAULT_VHOST|")
fi

exec "$@"
