#!/bin/bash

if [ "${TEST_SHARED_VOLUME}" -eq 1 ]; then
  echo "Write file for volume test"
  echo "hello from worker: ${HOSTNAME}" >> /shared_volume/hello-from-worker."${HOSTNAME}"
fi

exec ./bin/worker
