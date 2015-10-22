#!/bin/bash

set -ex

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack

testenv=${2:-"apiv2"}

if [ "$1" = "lbaasv1" ]; then
    testenv="apiv1"
elif [ "$1" = "lbaasv2" ]; then
    if [ "$2" = "healthmonitor" ] || [ "$2" = "listener" ] || [ "$2" = "loadbalancer" ] || [ "$2" = "member" ] || [ "$2" = "minimal" ] || [ "$2" = "pool" ]; then
        testenv="apiv2"
    elif [ "$2" = "scenario" ]; then
          testenv="scenario"
    fi
fi

export DEVSTACK_LOCAL_CONFIG+="
enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas
enable_plugin barbican https://git.openstack.org/openstack/barbican
enable_plugin octavia https://git.openstack.org/openstack/octavia
"

if [ "$testenv" != "apiv1" ]; then
  # Override enabled services, so we can turn on lbaasv2.
  # While we're at it, disable cinder and swift, since we don't need them.
  ENABLED_SERVICES+="q-lbaasv2,-q-lbaas"
  ENABLED_SERVICES+=",-c-api,-c-bak,-c-sch,-c-vol,-cinder"
  ENABLED_SERVICES+=",-s-account,-s-container,-s-object,-s-proxy"
  ENABLED_SERVICES+=",octavia,o-cw,o-hk,o-hm,o-api"
  export ENABLED_SERVICES
  DISABLE_AMP_IMAGE_BUILD=True
  export DISABLE_AMP_IMAGE_BUILD
fi

if [ "$testenv" = "apiv2" ]; then
   cat > $DEVSTACK_PATH/local.conf <<EOF
[[post-config|/etc/octavia/octavia.conf]]
[DEFAULT]
debug = True

[controller_worker]
amphora_driver = amphora_noop_driver
compute_driver = compute_noop_driver
network_driver = network_noop_driver

EOF

fi

$GATE_DEST/devstack-gate/devstack-vm-gate.sh
