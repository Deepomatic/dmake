#!/bin/bash

set -e

# Useful to have a working home (notably for pip commands), otherwise HOME is `/`, which is not writable with DMAKE_UID!=0
export HOME=/tmp/home
mkdir -p $HOME

exec "$@"
