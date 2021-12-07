#!/bin/bash

set -xe
test "$(cat /run/secrets/test_secret)" == "this_is_a_secret_value"
