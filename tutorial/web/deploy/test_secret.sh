# Script will fail on any error
set -e

/bin/bash -c 'v=$(cat /run/secrets/secretvalue); if [ "$v" == "this_is_a_secret_path" ]; then exit 0; else exit 1; fi;'
