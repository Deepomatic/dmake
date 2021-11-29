#!/bin/bash

set -xe

# This entrypoint is only used in dev mode: `dmake shell {{cookiecutter.backend}}`
export DEBUG=1

# Useful to have a working home (notably for pip commands), otherwise HOME is `/`, which is not writable with DMAKE_UID!=0
export HOME=/tmp/home
mkdir -p $HOME

exec "$@"
