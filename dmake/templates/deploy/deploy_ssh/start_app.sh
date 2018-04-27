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
if [ "${DOCKER_CMD}" = "nvidia-docker" ]; then
    if [ ! `which nvidia-smi` ]; then
        apt-get update
        apt-get install nvidia-384
    fi
    # Make sure modules are loaded
    modprobe nvidia
    modprobe nvidia_uvm
    if [ ! `which nvidia-docker` ]; then
        # install nvidia-docker v2
        curl -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
        tee /etc/apt/sources.list.d/nvidia-docker.list <<< \
"deb https://nvidia.github.io/libnvidia-container/ubuntu16.04/amd64 /
deb https://nvidia.github.io/nvidia-container-runtime/ubuntu16.04/amd64 /
deb https://nvidia.github.io/nvidia-docker/ubuntu16.04/amd64 /"
        apt-get update
        apt-get install nvidia-docker2
        systemctl reload docker
    fi
fi

# Copy docker credentials
cp -r .docker* $HOME/ || :

# Launch links if not launched
${LAUNCH_LINK}

# Pull the base image and build
docker pull ${IMAGE_NAME}

RUN_COMMAND="${DOCKER_CMD} run ${DOCKER_OPTS} -v /var/log:/var/log"
# Options to share docker (if the hooks wants to launch another container)
DOCKER_SHARE_OPTS="-v /var/run/docker.sock:/var/run/docker.sock -v $(which docker):/usr/bin/docker -v /usr/lib/x86_64-linux-gnu/libltdl.so.7:/usr/lib/x86_64-linux-gnu/libltdl.so.7"
RUN_COMMAND_HOOKS="$RUN_COMMAND --rm $DOCKER_SHARE_OPTS -t -i ${IMAGE_NAME}"

# Switch images
echo "Deploying new app version"
docker rm -f ${APP_NAME}-tmp || :
$RUN_COMMAND --restart unless-stopped --name ${APP_NAME}-tmp -d -i ${IMAGE_NAME}

# Run ready probe
if [ ! -z '${READYNESS_PROBE}' ]; then # '' are importants here as there might be unescaped " in READYNESS_PROBE
    echo "Running readyness probe"
    docker exec ${APP_NAME}-tmp ${READYNESS_PROBE}
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
