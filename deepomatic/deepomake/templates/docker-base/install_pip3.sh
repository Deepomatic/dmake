#!/bin/bash
#
# Usage:
# install_pip3.sh
#
# Result:
# Install pip3

if [ `which pip3 | wc -l` = "0" ]; then
    echo "N" | apt-get --no-install-recommends -y install openssh-client
    apt-get --no-install-recommends -y install python3-setuptools python3-dev libffi-dev libssl-dev curl g++
    curl https://bootstrap.pypa.io/get-pip.py | python3
    pip3 install --upgrade pip
fi