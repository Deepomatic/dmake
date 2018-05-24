#!/bin/bash

set -e

DMAKE_VERSION=0.1
DMAKE_CONFIG_DIR=${DMAKE_CONFIG_DIR:-${HOME}/.dmake}
DMAKE_UID=${DMAKE_UID:-}
DMAKE_PULL_CONFIG_DIR=${DMAKE_PULL_CONFIG_DIR:-1}
DMAKE_NO_GPU=${DMAKE_NO_GPU:-1}

# TODO: we should turn all this script into a Python script
NON_INTERACTIVE=0
if [ "$1" == "--non-interactive" ]; then
  NON_INTERACTIVE=1
fi

function prompt {
    QUESTION=$1
    VAR=$2
    declare -a OPTIONS=("${!3}")
    BLANK_OK=$4

    DEFAULT=${!VAR}
    DEFAULT_OPT=""
    if [ ! -z "${OPTIONS}" ] && [ ! -z "${DEFAULT}" ]; then
        N=${#OPTIONS[*]}
        for COUNT in $(seq 1 $N); do
            O=${OPTIONS[$((COUNT-1))]}
            O=`echo $O | sed "s/|.*//"` # remove detail
            if [ "$O" = "${DEFAULT}" ]; then
                DEFAULT=$COUNT
                DEFAULT_OPT=" ($O)"
                break
            fi
        done
    fi

    ANSWER=""
    while [ 1 ]; do
        # Ask question
        echo "${QUESTION}"

	# if non-interactive mode, leaves
        if [ "${NON_INTERACTIVE}" == "1" ]; then
            echo "Non-interactive mode activated, using '${DEFAULT}'"
            break
        fi

        # Print options
        if [ ! -z "${OPTIONS}" ]; then
            N=${#OPTIONS[*]}
            for COUNT in $(seq 1 $N); do
                O=${OPTIONS[$((COUNT-1))]}
                DETAIL=`echo $O | sed "s/[^|]*//"`
                if [ ! -z "$DETAIL" ]; then
                    DETAIL=" ($(echo $DETAIL | sed "s/|//"))"
                fi
                O=`echo $O | sed "s/|.*//"`
                echo "  $COUNT) ${O}${DETAIL}"
            done
        fi
        # Read input
        if [ -z "${DEFAULT}" ]; then
            read -p "  " ANSWER
        else
            read -p "  [default = ${DEFAULT}${DEFAULT_OPT}] " ANSWER
        fi
        # Set default value if necessary
        if [ -z "${ANSWER}" ]; then
            ANSWER=${DEFAULT}
        fi
        # Convert option number into text
        if [ ! -z "${OPTIONS}" ]; then
            N=$((${ANSWER}-1))
            if [ "$N" -lt "0" ]; then
                ANSWER=""
                echo "Please enter a number."
            else
                ANSWER=$(echo ${OPTIONS[$N]} | sed "s/|.*//")
            fi
        fi
        # Repeat if problem
        if [ -z "${BLANK_OK}" ] && [ -z "${ANSWER}" ]; then
            echo "Bad input. Again:"
        else
            break
        fi
    done
    export $VAR=$ANSWER
}

pushd `dirname $0` > /dev/null
DMAKE_PATH=`pwd -P`
popd > /dev/null

# Set DMAKE_CONFIG_DIR
if [ ! -d "${DMAKE_CONFIG_DIR}" ]; then
    mkdir ${DMAKE_CONFIG_DIR}
fi
CONFIG_FILE=${DMAKE_CONFIG_DIR}/config.sh

# Deprecated: move old config file to new location
OLD_CONFIG_FILE=${DMAKE_PATH}/config.sh
if [ -f "${OLD_CONFIG_FILE}" ]; then
    mv ${OLD_CONFIG_FILE} ${CONFIG_FILE}
    echo "Configuration file has moved !"
    for SHRC in `ls ~/\.*shrc`; do
        echo "Patching ${SHRC} (saving backup to ${SHRC}.bak)"
        cp ${SHRC} ${SHRC}.bak
        TMP_CONFIG=/tmp/$(basename ${SHRC})
        sed "s:${OLD_CONFIG_FILE}:${CONFIG_FILE}:" ${SHRC} > ${TMP_CONFIG}
        mv ${TMP_CONFIG} ${SHRC}
        echo "Patching done (removing ${SHRC}.bak)"
        rm ${SHRC}.bak
    done
fi

# Source config file
if [ -f "${DMAKE_CONFIG_DIR}/config.sh" ]; then
    source "${DMAKE_CONFIG_DIR}/config.sh"
fi

if [ -z "${DMAKE_SSH_KEY}" ]; then
    declare -a KEYS=($(ls ${HOME}/.ssh/*.pub 2> /dev/null))
    if [ -z "${KEYS}" ]; then
        DMAKE_SSH_KEY=
    else
        prompt "Which SSH key should we use to clone private repositories ? (enter number)" "DMAKE_SSH_KEY" KEYS[@] "${OPTIONS[0]}"
    fi
    DMAKE_SSH_KEY=$(echo ${DMAKE_SSH_KEY} | sed "s/\.pub//")
fi

echo "export DMAKE_VERSION=${DMAKE_VERSION}" > ${CONFIG_FILE}
echo "export DMAKE_PATH=${DMAKE_PATH}" >> ${CONFIG_FILE}
echo "export DMAKE_CONFIG_DIR=${DMAKE_CONFIG_DIR}" >> ${CONFIG_FILE}
echo "export DMAKE_UID=${DMAKE_UID}" >> ${CONFIG_FILE}
echo "export DMAKE_PULL_CONFIG_DIR=${DMAKE_PULL_CONFIG_DIR}" >> ${CONFIG_FILE}
echo "export DMAKE_NO_GPU=${DMAKE_NO_GPU}" >> ${CONFIG_FILE}
echo "export DMAKE_SSH_KEY=${DMAKE_SSH_KEY}" >> ${CONFIG_FILE}
echo "export PYTHONPATH=\$PYTHONPATH:${DMAKE_PATH}" >> ${CONFIG_FILE}
echo "export PATH=\$PATH:${DMAKE_PATH}/dmake/:${DMAKE_PATH}/dmake/utils" >> ${CONFIG_FILE}

LINE="source ${CONFIG_FILE}"
if [ -z "`which dmake`" ]; then
    # Try to automatically adds the source
    INSTALLED=0
    for SHRC in `ls ~/\.*shrc`; do
        if [ -z "`grep \"${LINE}\" ${SHRC}`" ]; then
            echo "We detected a shell config file here: ${SHRC}, patching to source ${CONFIG_FILE}."
            echo "${LINE}" >> ${SHRC}
            INSTALLED=1
        else
            echo "Patched ${SHRC} to source ${CONFIG_FILE}."
        fi
    done
else
    echo "Patched config to version ${DMAKE_VERSION}"
fi

echo "Installing python dependencies with: pip install --user -r requirements.txt"
pip install --user -r $(dirname $0)/requirements.txt
echo ""
echo "You should be good to go !"
echo "IMPORTANT: restart your shell session before testing the 'dmake' command !"
