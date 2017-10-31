#!/bin/bash

set -ex

GATE_DEST=$BASE/new

_DEVSTACK_LOCAL_CONFIG_TAIL=

# Inject config from hook
function load_conf_hook {
    local hook="$1"
    local GATE_HOOKS=$GATE_DEST/neutron-lbaas/neutron_lbaas/tests/contrib/hooks

    _DEVSTACK_LOCAL_CONFIG_TAIL+=$'\n'"$(cat $GATE_HOOKS/$hook)"
}

# Work around a devstack issue:https://review.openstack.org/#/c/435106
export DEVSTACK_LOCAL_CONFIG+="
DEFAULT_IMAGE_NAME=cirros-0.3.5-x86_64-disk
"

export DEVSTACK_LOCAL_CONFIG+="
enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas
enable_plugin barbican https://git.openstack.org/openstack/barbican
"

# Sort out our gate args
. $(dirname "$0")/decode_args.sh

# Note: The check for OVH instances is temporary until they resolve the
# KVM failures as logged here:
# https://bugzilla.kernel.org/show_bug.cgi?id=192521
# However, this may be resolved at OVH before the kernel bug is resolved.
if $(egrep --quiet '(vmx|svm)' /proc/cpuinfo) && [[ ! $(hostname) =~ "ovh" ]]; then
    export DEVSTACK_GATE_LIBVIRT_TYPE=kvm
fi

function _setup_octavia {
    export DEVSTACK_LOCAL_CONFIG+="
        enable_plugin octavia https://git.openstack.org/openstack/octavia
        "
    # Use infra's cached version of the file
    if [ -f /opt/stack/new/devstack/files/get-pip.py ]; then
            export DEVSTACK_LOCAL_CONFIG+="
        DIB_REPOLOCATION_pip_and_virtualenv=file:///opt/stack/new/devstack/files/get-pip.py
        "
    fi

    ENABLED_SERVICES+="octavia,o-cw,o-hk,o-hm,o-api,"
    if [ "$testenv" = "apiv2" ]; then
        load_conf_hook apiv2
    fi

    if [ "$testenv" = "scenario" ]; then
        load_conf_hook scenario
    fi
}


case "$testtype" in

    "dsvm-functional")
        PROJECT_NAME=neutron-lbaas
        NEUTRON_LBAAS_PATH=$GATE_DEST/$PROJECT_NAME
        IS_GATE=True
        USE_CONSTRAINT_ENV=False
        export LOG_COLOR=False
        source "$NEUTRON_LBAAS_PATH"/tools/configure_for_lbaas_func_testing.sh

        # Make the workspace owned by the stack user
        sudo chown -R "$STACK_USER":"$STACK_USER" "$BASE"

        configure_host_for_lbaas_func_testing
        ;;

    "tempest")
        # Make sure lbaasv2 is listed as enabled for tempest
        load_conf_hook api_extensions

        # These are not needed
        ENABLED_SERVICES+="-c-api,-c-bak,-c-sch,-c-vol,-cinder,"
        ENABLED_SERVICES+="-s-account,-s-container,-s-object,-s-proxy,"

        if [ "$testenv" != "scenario" ]; then
            export DEVSTACK_LOCAL_CONFIG+="
        DISABLE_AMP_IMAGE_BUILD=True
        "
            # Not needed for API tests
            ENABLED_SERVICES+="-horizon,-ceilometer-acentral,-ceilometer-acompute,"
            ENABLED_SERVICES+="-ceilometer-alarm-evaluator,-ceilometer-alarm-notifier,"
            ENABLED_SERVICES+="-ceilometer-anotification,-ceilometer-api,"
            ENABLED_SERVICES+="-ceilometer-collector,"
        fi

        # Override enabled services, so we can turn on lbaasv2.
        # While we're at it, disable cinder and swift, since we don't need them.
        ENABLED_SERVICES+="q-lbaasv2,"

        if [ "$lbaasdriver" = "namespace" ]; then
            export DEVSTACK_LOCAL_CONFIG+="
        NEUTRON_LBAAS_SERVICE_PROVIDERV2=LOADBALANCERV2:Haproxy:neutron_lbaas.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default
        "
        fi

        if [ "$lbaasdriver" = "octavia" ]; then
            _setup_octavia
        fi

        export ENABLED_SERVICES
        export DEVSTACK_LOCAL_CONFIG+=$'\n'"$_DEVSTACK_LOCAL_CONFIG_TAIL"
        "$GATE_DEST"/devstack-gate/devstack-vm-gate.sh
        ;;

    *)
        echo "Unrecognized test type $testtype".
        exit 1
        ;;
esac
