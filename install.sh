#!/bin/bash

if [ ! -z "`which dmake`" ] && [ ! -z "${DMAKE_VERSION}" ] && (( $(echo "$DMAKE_VERSION == 0.1" | bc -l) )); then
    echo "Looks like dmake is configured"
    exit 0
fi

pushd `dirname $0` > /dev/null
DMAKE_PATH=`pwd -P`
popd > /dev/null

echo "export DMAKE_VERSION=0.1" > ${DMAKE_PATH}/config.sh
echo "export DMAKE_PATH=${DMAKE_PATH}" >> ${DMAKE_PATH}/config.sh
echo "export DMAKE_SSH_KEY=${DMAKE_SSH_KEY}" >> ${DMAKE_PATH}/config.sh
echo "export DMAKE_CONFIG_DIR=${DMAKE_CONFIG_DIR}" >> ${DMAKE_PATH}/config.sh
echo "export PYTHONPATH=\$PYTHONPATH:${DMAKE_PATH}" >> ${DMAKE_PATH}/config.sh
echo "export PATH=\$PATH:${DMAKE_PATH}/deepomatic/deepomake/:${DMAKE_PATH}/deepomatic/deepomake/utils" >> ${DMAKE_PATH}/config.sh

LINE="source ${DMAKE_PATH}/config.sh"
if [ -z "`which dmake`" ]; then
    # Try to automatically adds the source
    INSTALLED=0
    for CONFIG_FILE in `ls ~/\.*shrc`; do
        if [ -z "`grep \"${LINE}\" ${CONFIG_FILE}`" ]; then
            echo "We detected a shell config file here: ${CONFIG_FILE}"
            read -p "Do you want to append '${LINE}' at the end ? [Y/n] " yn
            if [ -z "$yn" ] || [ "$yn" = "y" ] || [ "$YN" = "Y" ]; then
                echo "${LINE}" >> ${CONFIG_FILE}
                INSTALLED=1
            else
                echo "Skipping"
            fi
        else
            INSTALLED=1
        fi
    done

    if [ "${INSTALLED}" = "0" ]; then
        echo "Please ensure '${DMAKE_PATH}/config.sh' is sourced by adding the following lines to your shell configuration:"
        echo "${LINE}"
    fi
fi

echo "You should be good to go after restarting a shell session !"