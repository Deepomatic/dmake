#!/bin/bash

# Do not add {} around variables without it: it is on purpose so that replace_vars do not replace them.

# Mount volumes
mount -a

set -e

cd `dirname $0`

# Install Docker
docker --version || INSTALL_DOCKER=1
if [ "$INSTALL_DOCKER" = "1" ]; then
    apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
    echo "deb https://apt.dockerproject.org/repo ubuntu-$(lsb_release -cs) main" | tee /etc/apt/sources.list.d/docker.list -
    apt-get update
    apt-get install -y linux-image-extra-$(uname -r) linux-image-extra-virtual
    apt-get install -y docker-engine
    service docker start || echo 'Already running'
fi

# Search for unmounted volume
device_name=/dev/xvdb
mount_point=/mnt
if [ -e $device_name ] && [ `df | grep $device_name | wc -l` == "0" ] && [ ! -e $mount_point ]; then
    mkfs -t ext4 $device_name
    mkdir -p $mount_point
    mount $device_name $mount_point

    if [ `cat /etc/fstab | grep $device_name | wc -l` == "0" ]; then
        echo "$device_name       $mount_point   ext4    defaults,nofail,nobootwait        0       2"  >> /etc/fstab
    fi
fi

# Install NVIDIA drivers
if [ ! -z "${INSTALL_NVIDIA_DRIVERS}" ]; then
    if [ ! `which nvidia-smi` ]; then
        apt-get update
        apt-get install nvidia-375
    fi
    # Make sure modules are loaded
    modprobe nvidia
    modprobe nvidia_uvm
    if [[ "${DOCKER_RUN_CMD}" =~ nvidia-docker.* ]]; then
        apt-get update
        apt-get install nvidia-modprobe
        wget -P /tmp https://github.com/NVIDIA/nvidia-docker/releases/download/v1.0.1/nvidia-docker_1.0.1-1_amd64.deb
        sudo dpkg -i /tmp/nvidia-docker*.deb && rm /tmp/nvidia-docker*.deb
    fi
fi

# Copy docker credentials
cp -r .docker* $HOME/ || :

# Launch links if not launched
${LAUNCH_LINK}

# Pull the base image and build
docker pull ${IMAGE_NAME}

RUN_COMMAND="${DOCKER_RUN_CMD} ${DOCKER_OPTS} -v /var/log:/var/log"
# Options to share docker (if the hooks wants to launch another container)
DOCKER_SHARE_OPTS="-v /var/run/docker.sock:/var/run/docker.sock -v $(which docker):/usr/bin/docker -v /usr/lib/x86_64-linux-gnu/libltdl.so.7:/usr/lib/x86_64-linux-gnu/libltdl.so.7"
RUN_COMMAND_HOOKS="$RUN_COMMAND --rm $DOCKER_SHARE_OPTS -t -i ${IMAGE_NAME}"

# Run pre hooks (deprecated)
if [ ! -z "${PRE_DEPLOY_HOOKS}" ]; then
    echo "Running pre-deploy script ${PRE_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${PRE_DEPLOY_HOOKS}
fi

# Switch images
echo "Deploying new app version"
docker rm -f ${APP_NAME}-tmp || :
$RUN_COMMAND --restart unless-stopped --name ${APP_NAME}-tmp -d -i ${IMAGE_NAME}

# Run ready probe
if [ ! -z '${READYNESS_PROBE}' ]; then # '' are importants here as there might be unescaped " in READYNESS_PROBE
    echo "Running readyness probe"
    docker exec ${APP_NAME}-tmp ${READYNESS_PROBE}
fi

# Run mid hooks (deprecated)
if [ ! -z "${MID_DEPLOY_HOOKS}" ]; then
    echo "Running mid-deploy script ${MID_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${MID_DEPLOY_HOOKS}
fi

docker stop ${APP_NAME} &> /dev/null || :
docker rm -f ${APP_NAME} &> /dev/null || :
docker rename ${APP_NAME}-tmp ${APP_NAME}

# Remove unused images
set +e
IDS=`docker images | sed "s/  */ /g" | cut -d\  -f1,3 | grep "<none>"`
if [ ! -z "$IDS" ]; then
    docker rmi $IDS
fi
set -e

# Run post hooks (deprecated)
if [ ! -z "${POST_DEPLOY_HOOKS}" ]; then
    echo "Running post-deploy script ${POST_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${POST_DEPLOY_HOOKS}
fi
