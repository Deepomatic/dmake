#!/bin/bash

set -xe

if [[ ${NVIDIA_VISIBLE_DEVICES} == 'none' ]]; then
  echo "GPU needed for this test but dmake was executed with DMAKE_NO_GPU set."
  echo "Test GPU was really disabled in dmake"
  test "${DMAKE_NO_GPU}" == '1' -o "${DMAKE_NO_GPU}" == 'true'
  exit
fi


echo "Test nvidia-smi execution"
nvidia-smi

echo "Test at least one GPU is available"
test $(nvidia-smi -L | wc -l) -ge 1
