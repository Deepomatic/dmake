# Script will fail on any error
set -e

apt-get update
apt-get --no-install-recommends -y install \
        make \
        iputils-ping
