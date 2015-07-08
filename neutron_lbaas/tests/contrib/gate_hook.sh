#!/bin/bash

set -ex

testenv=${2:-"apiv2"}

if [ "$1" = "lbaasv1" ]; then
    testenv="apiv1"
elif [ "$1" = "lbaasv2" ]; then
    if [ "$2" = "api" ]; then
        testenv="apiv2"
    elif [ "$2" = "scenario" ]; then
          testenv="scenario"
    fi
fi

export DEVSTACK_LOCAL_CONFIG="enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas"

if [ "$testenv" != "apiv1" ]; then
  # Override enabled services, so we can turn on lbaasv2.
  # While we're at it, disable cinder and swift, since we don't need them.
  ENABLED_SERVICES="q-lbaasv2,-q-lbaas"
  ENABLED_SERVICES+=",-c-api,-c-bak,-c-sch,-c-vol,-cinder"
  ENABLED_SERVICES+=",-s-account,-s-container,-s-object,-s-proxy"
  export ENABLED_SERVICES
fi

$BASE/new/devstack-gate/devstack-vm-gate.sh
