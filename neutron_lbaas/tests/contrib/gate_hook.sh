#!/bin/bash

set -ex

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack

# Sort out our gate args
. `dirname "$0"`/decode_args.sh

testenv=${lbaastest:-"apiv2"}

if [ "$lbaasversion" = "lbaasv1" ]; then
    testenv="apiv1"
elif [ "$lbaasversion" = "lbaasv2" ]; then
    if [ "$lbaasenv" = "healthmonitor" ] || [ "$lbaasenv" = "listener" ] || [ "$lbaasenv" = "loadbalancer" ] || [ "$lbaasenv" = "member" ] || [ "$lbaasenv" = "minimal" ] || [ "$lbaasenv" = "pool" ]; then
        testenv="apiv2"
    elif [ "$lbaasenv" = "scenario" ]; then
          testenv="scenario"
    fi
fi

export DEVSTACK_LOCAL_CONFIG+="
enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas
enable_plugin barbican https://git.openstack.org/openstack/barbican
"
if [ "$lbaasdriver" = "octavia" ]; then
    export DEVSTACK_LOCAL_CONFIG+="
enable_plugin octavia https://git.openstack.org/openstack/octavia
"
fi

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

# These are not needed with either v1 or v2
ENABLED_SERVICES+="-c-api,-c-bak,-c-sch,-c-vol,-cinder"
ENABLED_SERVICES+=",-s-account,-s-container,-s-object,-s-proxy"

if [ "$testenv" != "apiv1" ]; then
  # Override enabled services, so we can turn on lbaasv2.
  # While we're at it, disable cinder and swift, since we don't need them.
  ENABLED_SERVICES+=",q-lbaasv2,-q-lbaas"
  if [ "$lbaasdriver" = "octavia" ]; then
    ENABLED_SERVICES+=",octavia,o-cw,o-hk,o-hm,o-api"
  fi

  if [ "$lbaasdriver" = "namespace" ]; then
    export DEVSTACK_LOCAL_CONFIG+="
NEUTRON_LBAAS_SERVICE_PROVIDERV2=LOADBALANCERV2:Haproxy:neutron_lbaas.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default
"
  fi
fi
export ENABLED_SERVICES

if [ "$lbaasdriver" = "octavia" -a "$testenv" = "apiv2" ]; then
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

if [ "$lbaasdriver" = "octavia" -a "$testenv" = "scenario" ]; then
   cat > $DEVSTACK_PATH/local.conf <<EOF
[[post-config|/etc/octavia/octavia.conf]]
[DEFAULT]
debug = True

EOF

fi

$GATE_DEST/devstack-gate/devstack-vm-gate.sh
