# Script will fail on any error
set -e

apt-get update
apt-get --no-install-recommends -y install \
        ca-certificates \
        curl python python-dev python-pip \
        make \
        iputils-ping

pip install --no-cache-dir -r deploy/requirements.txt
