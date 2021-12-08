#!/bin/bash

set -xe

# Install dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install --yes --no-install-recommends \
        locales make curl wget bash-completion ca-certificates iputils-ping \
        shellcheck \
        python3 python3-distutils python3-dev python3-pip \
        python3-setuptools python3-wheel \

# Generate locale
locale-gen en_US.UTF-8
export LANG=en_US.UTF-8

# Bash completion for developers
cat >> /etc/bash.bashrc <<EOF

# enable bash completion in interactive shells
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi
EOF

# Install pip-tools, outside of requirements-dev.in as it somehow breaks its own hashing constraints
pip3 install --no-cache-dir pip-tools==6.4.0

# Install python dependencies from frozen list
pip3 install --no-cache-dir -r deploy/base/build/requirements.txt

# Cleanup
apt-get clean || :
rm -rf /var/lib/apt/lists/* || :
