#!/usr/bin/env bash

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

set -e


IS_GATE=${IS_GATE:-False}
USE_CONSTRAINT_ENV=${USE_CONSTRAINT_ENV:-False}
PROJECT_NAME=${PROJECT_NAME:-neutron-lbaas}
REPO_BASE=${GATE_DEST:-$(cd $(dirname "$BASH_SOURCE")/../.. && pwd)}

source $REPO_BASE/neutron/tools/configure_for_func_testing.sh


function configure_host_for_lbaas_func_testing {
    echo_summary "Configuring for LBaaS functional testing"
    if [ "$IS_GATE" == "True" ]; then
        configure_host_for_func_testing
    fi

    source $REPO_BASE/neutron-lbaas/devstack/settings
    source $NEUTRON_LBAAS_DIR/devstack/plugin.sh

    local temp_ini=$(mktemp)

    # Note(pc_m): Need to ensure this is installed so we have
    # oslo-config-generator present (as this script runs before tox.ini).
    sudo pip install --force oslo.config
    neutron_lbaas_generate_config_files
    neutron_agent_lbaas_install_agent_packages
    neutron_lbaas_configure_agent $temp_ini

    sudo install -d -o $STACK_USER $LBAAS_AGENT_CONF_PATH
    sudo install -m 644 -o $STACK_USER $temp_ini $LBAAS_AGENT_CONF_FILENAME
}


if [ "$IS_GATE" != "True" ]; then
    configure_host_for_lbaas_func_testing
fi
