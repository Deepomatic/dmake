#!/bin/bash

set -e

if [ "${TEST_SHARED_VOLUME}" -eq 1 ]; then
  echo "Write file for volume test"
  echo "hello from worker: ${HOSTNAME}" >> /shared_volume/hello-from-worker.${HOSTNAME}
fi

if [ "${TEST_ENV_OVERRIDE}" -eq 1 ]; then
  echo "Test env override"
  test "${ENV_OVERRIDE_TEST1}" = from_root_env
  test "${ENV_OVERRIDE_TEST2}" = from_env_override
  test "${ENV_OVERRIDE_TEST3}" = from_needed_service_env
  test "${ENV_OVERRIDE_TEST4}" = from_env_override
  test "${ENV_OVERRIDE_TEST5}" = from_needed_service_env
fi


exec ./bin/worker
