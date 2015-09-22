#!/bin/bash

set -ex

GATE_DEST=$BASE/new

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

export DEVSTACK_LOCAL_CONFIG+="
enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas
enable_plugin barbican https://git.openstack.org/openstack/barbican
enable_plugin octavia https://git.openstack.org/openstack/octavia
IMAGE_URLS+=\",http://g8de985af226d635b09bbb525b05dc4af.cdn.hpcloudsvc.com/amphora/amphora-x64-haproxy.qcow2\"
"

if [ "$testenv" != "apiv1" ]; then
  # Override enabled services, so we can turn on lbaasv2.
  # While we're at it, disable cinder and swift, since we don't need them.
  ENABLED_SERVICES+="q-lbaasv2,-q-lbaas"
  ENABLED_SERVICES+=",-c-api,-c-bak,-c-sch,-c-vol,-cinder"
  ENABLED_SERVICES+=",-s-account,-s-container,-s-object,-s-proxy"
  ENABLED_SERVICES+=",octavia,o-cw,o-hk,o-hm,o-api"
  export ENABLED_SERVICES
  VOLUME_BACKING_FILE_SIZE=24G
  export VOLUME_BACKING_FILE_SIZE
fi

$GATE_DEST/devstack-gate/devstack-vm-gate.sh
