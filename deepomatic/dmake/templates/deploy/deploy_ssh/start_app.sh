#!/bin/bash

# Do not add {} around variables without it: it is on purpose so that replace_vars do not replace them.

# Make sure modules are loaded
modprobe nvidia
modprobe nvidia_uvm

# Mount volumes
mount -a

set -e

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

# Launch links if not launched
${LAUNCH_LINK}

# Get ID of current image
CURRENT_IMAGE=`docker images | grep ${APP_NAME} | sed -r 's/ +/ /g' | cut -d ' ' -f 3 | paste -s -d ' ' -`

# Pull the base image and build
BASE_IMAGE=`cat Dockerfile | grep FROM | sed 's/FROM //'`
docker pull $BASE_IMAGE
docker build -t ${APP_NAME} .

RUN_COMMAND="docker run --privileged ${DOCKER_OPTS} -v /var/log:/var/log -e ENV_TYPE=${ENV_TYPE}"
# Options to share docker (if the hooks wants to launch another container)
DOCKER_SHARE_OPTS="-v /var/run/docker.sock:/var/run/docker.sock -v $(which docker):/usr/bin/docker -v /usr/lib/x86_64-linux-gnu/libltdl.so.7:/usr/lib/x86_64-linux-gnu/libltdl.so.7"
RUN_COMMAND_HOOKS="$RUN_COMMAND --rm $DOCKER_SHARE_OPTS -v $PWD:/app -t -i ${APP_NAME}"
# Run pre hooks
if [ ! -z "${PRE_DEPLOY_HOOKS}" ]; then
    echo "Running pre-deploy script ${PRE_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${PRE_DEPLOY_HOOKS}
fi

# Switch images
docker rm -f ${APP_NAME}-tmp || echo 'No such container'
$RUN_COMMAND --restart unless-stopped --name ${APP_NAME}-tmp -d -i ${APP_NAME}

# Run mid hooks
if [ ! -z "${MID_DEPLOY_HOOKS}" ]; then
    echo "Running mid-deploy script ${MID_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${MID_DEPLOY_HOOKS}
fi

docker stop ${APP_NAME} || echo 'No running container'
docker rm -f ${APP_NAME} || echo 'No such container'
docker rmi -f $CURRENT_IMAGE || echo 'No previous image'
docker rename ${APP_NAME}-tmp ${APP_NAME}

# Run post hooks
if [ ! -z "${POST_DEPLOY_HOOKS}" ]; then
    echo "Running post-deploy script ${POST_DEPLOY_HOOKS}"
    $RUN_COMMAND_HOOKS ${POST_DEPLOY_HOOKS}
fi

