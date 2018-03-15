#!/bin/bash

set -e

echo "Check needed_service link_name"

HOST=$1

ping -c1 $HOST
