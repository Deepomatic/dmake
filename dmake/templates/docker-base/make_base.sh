#!/bin/bash
# Please do not edit this file but rather use:
# - requirements.txt: for any pip related install
# - dependencies.sh: for other libraries

set -e

# Copy config to /base (otherwise the docker commit does not save it)
ROOT=$(dirname $0)
rm -rf /base
cp -r $ROOT /base
cd /base

# Setup packet manager
dpkg --configure -a
apt-get update || apt-get update --fix-missing

# Make sure SSH Agent socket is here if needed
if [ ! -z "$SSH_AUTH_SOCK" ] || [ -f "/key" ]; then # HACK for mac: Waiting for Issue docker/for-mac#483 to be solved (cf deepobuild.py)
    # Disable SSH strict checking
    apt-get -y install openssh-client
    mkdir -p /etc/ssh
    echo -e "\nHost *\n    ForwardAgent yes\n    StrictHostKeyChecking no\n" >> /etc/ssh/ssh_config
    # HACK: Waiting for Issue docker/for-mac#483
    if [ -f "/key" ]; then
        chmod 400 /key
        echo -e "    IdentityFile /key\n" >> /etc/ssh/ssh_config
    fi
fi

# Setup logrotate
apt-get --no-install-recommends -y install logrotate
cp config.logrotate /etc/logrotate.d/deepomatic

# Configure SSL on the system
# This step is needed to install Pip
apt-get -y install apt-transport-https ca-certificates

# # Configure the server to stay uptodate (TODO: should actually be set on host ?)
# apt-get -y install ntpdate
# echo "Etc/UTC" > /etc/timezone
# dpkg-reconfigure -f noninteractive tzdata
# ntpdate ntp.ubuntu.com

# Run installation
if [ -d user ]; then
    bash run_cmd.sh
fi

## Do some cleaning
if [ -f /etc/ssh/ssh_config ]; then
    head -n 4 /etc/ssh/ssh_config > /tmp/ssh_config
    mv /tmp/ssh_config /etc/ssh/ssh_config
fi
rm -rf /tmp/* || :
rm -rf /var/lib/apt/lists/* || :
