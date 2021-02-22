#!/bin/bash

set -e

DMAKE_VERSION=0.1

# TODO: we should turn all this script into a Python script
NON_INTERACTIVE=0
if [[ "$1" == "--non-interactive" ]]; then
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
        if [[ "${NON_INTERACTIVE}" == "1" ]]; then
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
if [ -z "${DMAKE_CONFIG_DIR}" ]; then
    DMAKE_CONFIG_DIR=${HOME}/.dmake
fi
if [ ! -d "${DMAKE_CONFIG_DIR}" ]; then
    mkdir ${DMAKE_CONFIG_DIR}
fi
DMAKE_PULL_CONFIG_DIR=${DMAKE_PULL_CONFIG_DIR:-1}
CONFIG_FILE=${DMAKE_CONFIG_DIR}/config.sh

# Source config file
if [ -f "${DMAKE_CONFIG_DIR}/config.sh" ]; then
    source "${DMAKE_CONFIG_DIR}/config.sh"
fi

DMAKE_USE_HOST_PORTS=${DMAKE_USE_HOST_PORTS:-1}
DMAKE_PUSH_BASE_IMAGE=${DMAKE_PUSH_BASE_IMAGE:-0}

cat <<EOF > ${CONFIG_FILE}
# Global config
: \${DMAKE_GLOBAL_CONFIG_DIR:=/etc/dmake}
if [ -f \${DMAKE_GLOBAL_CONFIG_DIR}/config ]; then
  source \${DMAKE_GLOBAL_CONFIG_DIR}/config
fi


# User-specific config
export DMAKE_VERSION=\${DMAKE_VERSION:-${DMAKE_VERSION}}
export DMAKE_UID=\${DMAKE_UID:-\$(id -u)}
export DMAKE_PATH=\${DMAKE_PATH:-${DMAKE_PATH}}
export DMAKE_CONFIG_DIR=\${DMAKE_CONFIG_DIR:-${DMAKE_CONFIG_DIR}}
export DMAKE_NO_GPU=\${DMAKE_NO_GPU:-${DMAKE_NO_GPU}}
export DMAKE_PULL_CONFIG_DIR=\${DMAKE_PULL_CONFIG_DIR:-${DMAKE_PULL_CONFIG_DIR}}
export DMAKE_USE_HOST_PORTS=\${DMAKE_USE_HOST_PORTS:-${DMAKE_USE_HOST_PORTS}}
export DMAKE_PUSH_BASE_IMAGE=\${DMAKE_PUSH_BASE_IMAGE:-${DMAKE_PUSH_BASE_IMAGE}}
export DMAKE_SSH_KEY=\${DMAKE_SSH_KEY:-${DMAKE_SSH_KEY}}
export DMAKE_GITHUB_OWNER=\${DMAKE_GITHUB_OWNER:-${DMAKE_GITHUB_OWNER}}
export DMAKE_GITHUB_TOKEN=\${DMAKE_GITHUB_TOKEN:-${DMAKE_GITHUB_TOKEN}}
export PYTHONPATH=\${PYTHONPATH+\${PYTHONPATH}:}\${DMAKE_PATH}
export PATH=\${PATH+\${PATH}:}\${DMAKE_PATH}/dmake/:\${DMAKE_PATH}/dmake/utils

# Shell completion
if [ -f "${DMAKE_CONFIG_DIR}/completion.bash.inc" ]; then
  # zsh support for bash completion
  if [ -n "\${ZSH_VERSION}" ]; then
    autoload -U bashcompinit && bashcompinit
  fi
  source "${DMAKE_CONFIG_DIR}/completion.bash.inc"
fi
EOF

LINE="source ${CONFIG_FILE}"
# Try to automatically adds the source
for SHRC in `ls ~/\.*shrc`; do
    if [ -z "`grep \"${LINE}\" ${SHRC}`" ]; then
        echo "We detected a shell config file here: ${SHRC}, patching to source ${CONFIG_FILE}"
        echo -e "\n${LINE}" >> ${SHRC}
    else
        echo "Patched ${SHRC} to source ${CONFIG_FILE}"
    fi
done

echo "Installing python dependencies with: pip3 install --user -r requirements.txt"
pip3 install --user -r $(dirname $0)/requirements.txt
echo ""

echo "Installing shell completion"
# eval and generate shell completion
eval "${LINE}"
dmake completion > "${DMAKE_CONFIG_DIR}/completion.bash.inc"

echo "You should be good to go !"
echo "IMPORTANT: restart your shell session before testing the 'dmake' command !"
