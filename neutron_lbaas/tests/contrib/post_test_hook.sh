#!/bin/bash

set -xe

NEUTRON_LBAAS_DIR="$BASE/new/neutron-lbaas"
TEMPEST_CONFIG_DIR="$BASE/new/tempest/etc"
SCRIPTS_DIR="/usr/os-testr-env/bin"
OCTAVIA_DIR="$BASE/new/octavia"

# Sort out our gate args
. `dirname "$0"`/decode_args.sh

LBAAS_VERSION=$lbaasversion
LBAAS_TEST=$lbaasenv
LBAAS_DRIVER=$lbaasdriver

if [ "$LBAAS_VERSION" = "lbaasv1" ]; then
    testenv="apiv1"
else
    testenv="apiv2"
    case "$LBAAS_TEST" in
        api)
            if [ "$LBAAS_DRIVER" = "namespace" ]; then
                test_subset="load_balancers "
                test_subset+="listeners "
                test_subset+="pools "
                test_subset+="members "
                test_subset+="health_monitor"
            else
                testenv=${LBAAS_TEST:-"apiv2"}
            fi
            ;;
        minimal)
            # Temporarily just do the happy path
            test_subset="neutron_lbaas.tests.tempest.v2.api.test_load_balancers_non_admin.LoadBalancersTestJSON.test_create_load_balancer(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_load_balancers_non_admin.LoadBalancersTestJSON.test_get_load_balancer_stats(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_load_balancers_non_admin.LoadBalancersTestJSON.test_get_load_balancer_status_tree(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_listeners_non_admin.ListenersTestJSON.test_create_listener(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_pools_non_admin.TestPools.test_create_pool(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_members_non_admin.MemberTestJSON.test_add_member(?!_) "
            test_subset+="neutron_lbaas.tests.tempest.v2.api.test_health_monitors_non_admin.TestHealthMonitors.test_create_health_monitor(?!_)"
            ;;
        healthmonitor)
            test_subset="health_monitor"
            ;;
        listener)
            test_subset="listeners"
            ;;
        loadbalancer)
            test_subset="load_balancers"
            ;;
        member)
            test_subset="members"
            ;;
        pool)
            test_subset="pools"
            ;;
        scenario)
            testenv="scenario"
            ;;
        *)
            testenv=${LBAAS_TEST:-"apiv2"}
            ;;
    esac
fi

function generate_testr_results {
    # Give job user rights to access tox logs
    sudo -H -u $owner chmod o+rw .
    sudo -H -u $owner chmod o+rw -R .testrepository
    if [ -f ".testrepository/0" ] ; then
        subunit-1to2 < .testrepository/0 > ./testrepository.subunit
        $SCRIPTS_DIR/subunit2html ./testrepository.subunit testr_results.html
        gzip -9 ./testrepository.subunit
        gzip -9 ./testr_results.html
        sudo mv ./*.gz /opt/stack/logs/
    fi
}

owner=tempest

# Set owner permissions according to job's requirements.
cd $NEUTRON_LBAAS_DIR
sudo chown -R $owner:stack $NEUTRON_LBAAS_DIR
if [ "$lbaasdriver" = "octavia" ]; then
    sudo chown -R $owner:stack $OCTAVIA_DIR
fi

sudo_env=" OS_TESTR_CONCURRENCY=1"

# Configure the api and scenario tests to use the tempest.conf set by devstack
sudo_env+=" TEMPEST_CONFIG_DIR=$TEMPEST_CONFIG_DIR"

if [ "$testenv" = "apiv2" ]; then
    sudo_env+=" OS_TEST_PATH=$NEUTRON_LBAAS_DIR/neutron_lbaas/tests/tempest/v2/api"
elif [ "$testenv" = "apiv1" ]; then
    sudo_env+=" OS_TEST_PATH=$NEUTRON_LBAAS_DIR/neutron_lbaas/tests/tempest/v1/api"
elif [ "$testenv" = "scenario" ]; then
    sudo_env+=" OS_TEST_PATH=$NEUTRON_LBAAS_DIR/neutron_lbaas/tests/tempest/v2/scenario"
else
    echo "ERROR: unsupported testenv: $testenv"
    exit 1
fi

# Run tests
echo "Running neutron lbaas $testenv test suite"
set +e

sudo -H -u $owner $sudo_env tox -e $testenv -- $test_subset
# sudo -H -u $owner $sudo_env testr init
# sudo -H -u $owner $sudo_env testr run

testr_exit_code=$?
set -e

# Collect and parse results
generate_testr_results
exit $testr_exit_code
