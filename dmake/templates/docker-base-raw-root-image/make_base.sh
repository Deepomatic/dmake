#!/bin/bash
set -e

# Copy config to /base (otherwise the docker commit does not save it)
ROOT=$(dirname $0)
rm -rf /base
cp -r $ROOT /base
cd /base

if [ -d user ]; then
    bash run_cmd.sh
fi
