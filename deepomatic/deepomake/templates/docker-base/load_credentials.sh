#!/bin/bash
#
# Usage:
# eval $(load_credentials.sh)
#
# Result:
# The private key for github is stored in $ID_RSA

set -e

# Find address to host
IP=`netstat -nr | grep '^0\.0\.0\.0' | awk '{print $2}'`

# We need to allow wget to fail to exit properly
set +e

wget -q -O /tmp/id_rsa http://$IP:2223/key
if [ "$?" != "0" ]; then
    echo "echo 'Could not find credentials' && exit 1"
    rm -f /tmp/id_rsa
    exit 1
fi
ID_RSA=$(sed 's/$/\\n/' /tmp/id_rsa | paste -s -d "")

echo "export ID_RSA=\"$ID_RSA\""
