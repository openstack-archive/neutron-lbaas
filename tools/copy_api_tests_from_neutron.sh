#!/usr/bin/env bash

# This script is intended to allow repeatable migration of the neutron
# api tests from tempest.  The intention is to allow development to
# continue in Tempest while the migration strategy evolves.

set -e

if [[ "$#" -ne 1 ]]; then
    >&2 echo "Usage: $0 /path/to/neutron
Migrate lbaas's api tests from a neutron repo."
    exit 1
fi

NEUTRON_PATH=${NEUTRON_PATH:-$1}

if [ ! -d "$NEUTRON_PATH/neutron/tests/tempest" ]; then
  >&2 echo "Unable to find tempest at '$NEUTRON_PATH'.  Please verify that the specified path points to a valid tempest repo."
  exit 1
fi

NEUTRON_LBAAS_PATH=${NEUTRON_LBAAS_PATH:-$(cd "$(dirname "$0")/.." && pwd)}
NEUTRON_LBAAS_TEST_PATH=$NEUTRON_LBAAS_PATH/neutron_lbaas/tests

function copy_files {
    local neutron_dep_paths=(
        ''
        'common'
        'common/generator'
        'common/utils'
        'services'
        'services/identity'
        'services/identity/v2'
        'services/identity/v2/json'
        'services/identity/v3'
        'services/identity/v3/json'
        'services/network'
        'services/network/json'
    )
    for neutron_dep_path in ${neutron_dep_paths[@]}; do
        local target_path=$NEUTRON_LBAAS_TEST_PATH/tempest/lib/$neutron_dep_path
        if [[ ! -d "$target_path" ]]; then
            mkdir -p "$target_path"
        fi
        cp $NEUTRON_PATH/neutron/tests/tempest/$neutron_dep_path/*.py "$target_path"
    done
    # local paths_to_remove=(
    #     "$NEUTRON_LBAAS_TEST_PATH/tempest/clients.py"
    # )
    # for path_to_remove in ${paths_to_remove[@]}; do
    #     if [ -f "$path_to_remove" ]; then
    #         rm "$path_to_remove"
    #     fi
    # done

    # Tests are now maintained in neutron/tests/api
    cp $NEUTRON_PATH/neutron/tests/api/*.py $NEUTRON_LBAAS_TEST_PATH/tempest/v1/api
    cp $NEUTRON_PATH/neutron/tests/api/admin/*.py \
        $NEUTRON_LBAAS_TEST_PATH/tempest/v1/api/admin
}

function rewrite_imports {
    regexes=(
        's/neutron.tests.tempest.common.generator/neutron_lbaas.tests.tempest.lib.common.generator/'
        "s/neutron.tests.api/neutron_lbaas.tests.tempest.v1.api/"
        's/neutron.tests.tempest.test/neutron_lbaas.tests.tempest.lib.test/'
        's/from neutron.tests.api import clients/from neutron_lbaas.tests.tempest.v1.api import clients/'
        's/from neutron.tests.tempest/from neutron_lbaas.tests.tempest.lib/'
        's/CONF.lock_path/CONF.oslo_concurrency.lock_path/'
    )
    files=$(find "$NEUTRON_LBAAS_TEST_PATH/tempest/lib" "$NEUTRON_LBAAS_TEST_PATH/tempest/v1/api" -name '*.py')
    for ((i = 0; i < ${#regexes[@]}; i++)); do
        perl -p -i -e "${regexes[$i]}" $files
    done
}

copy_files
rewrite_imports
