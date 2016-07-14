#!/usr/bin/env bash

# Sample ``local.sh`` that configures two simple webserver instances and sets
# up a Neutron LBaaS Version 2 loadbalancer.

# Keep track of the DevStack directory
TOP_DIR=$(cd $(dirname "$0") && pwd)
BOOT_DELAY=60

# Import common functions
source ${TOP_DIR}/functions

# Use openrc + stackrc for settings
source ${TOP_DIR}/stackrc

# Destination path for installation ``DEST``
DEST=${DEST:-/opt/stack}

# Additional Variables
IMAGE_NAME="cirros"
SUBNET_NAME="private-subnet"

if is_service_enabled nova; then

    # Get OpenStack demo user auth
    source ${TOP_DIR}/openrc demo demo

    # Create an SSH key to use for the instances
    HOST=$(echo $HOSTNAME | cut -d"." -f1)
    DEVSTACK_LBAAS_SSH_KEY_NAME=${HOST}_DEVSTACK_LBAAS_SSH_KEY_RSA
    DEVSTACK_LBAAS_SSH_KEY_DIR=${TOP_DIR}
    DEVSTACK_LBAAS_SSH_KEY=${DEVSTACK_LBAAS_SSH_KEY_DIR}/${DEVSTACK_LBAAS_SSH_KEY_NAME}
    rm -f ${DEVSTACK_LBAAS_SSH_KEY}.pub ${DEVSTACK_LBAAS_SSH_KEY}
    ssh-keygen -b 2048 -t rsa -f ${DEVSTACK_LBAAS_SSH_KEY} -N ""
    nova keypair-add --pub-key=${DEVSTACK_LBAAS_SSH_KEY}.pub ${DEVSTACK_LBAAS_SSH_KEY_NAME}

    # Add tcp/22,80 and icmp to default security group
    nova secgroup-add-rule default tcp 22 22 0.0.0.0/0
    nova secgroup-add-rule default tcp 80 80 0.0.0.0/0
    nova secgroup-add-rule default icmp -1 -1 0.0.0.0/0

    # Get Image id
    IMAGE_ID=$(glance image-list | awk -v image=${IMAGE_NAME} '$0 ~ image {print $2}' | head -1)

    # Get Network id
    NET_ID=$(neutron subnet-show ${SUBNET_NAME} | awk '/network_id/ {print $4}')

    # Boot some instances
    NOVA_BOOT_ARGS="--key-name ${DEVSTACK_LBAAS_SSH_KEY_NAME} --image ${IMAGE_ID} --flavor 1 --nic net-id=$NET_ID"

    nova boot ${NOVA_BOOT_ARGS} node1
    nova boot ${NOVA_BOOT_ARGS} node2

    echo "Waiting ${BOOT_DELAY} seconds for instances to boot"
    sleep ${BOOT_DELAY}

    # Get Instances IP Addresses
    SUBNET_ID=$(neutron subnet-show ${SUBNET_NAME} | awk '/ id / {print $4}')
    IP1=$(neutron port-list --device_owner compute:None -c fixed_ips | grep ${SUBNET_ID} | cut -d'"' -f8 | sed -n 1p)
    IP2=$(neutron port-list --device_owner compute:None -c fixed_ips | grep ${SUBNET_ID} | cut -d'"' -f8 | sed -n 2p)

    ssh-keygen -R ${IP1}
    ssh-keygen -R ${IP2}

    # Run a simple web server on the instances
    scp -i ${DEVSTACK_LBAAS_SSH_KEY} -o StrictHostKeyChecking=no ${TOP_DIR}/webserver.sh cirros@${IP1}:webserver.sh
    scp -i ${DEVSTACK_LBAAS_SSH_KEY} -o StrictHostKeyChecking=no ${TOP_DIR}/webserver.sh cirros@${IP2}:webserver.sh

    screen_process node1 "ssh -i ${DEVSTACK_LBAAS_SSH_KEY} -o StrictHostKeyChecking=no cirros@${IP1} ./webserver.sh"
    screen_process node2 "ssh -i ${DEVSTACK_LBAAS_SSH_KEY} -o StrictHostKeyChecking=no cirros@${IP2} ./webserver.sh"

fi

function wait_for_lb_active {
    echo "Waiting for $1 to become ACTIVE..."
    status=$(neutron lbaas-loadbalancer-show $1 | awk '/provisioning_status/ {print $4}')
    while  [ "$status" != "ACTIVE" ]
     do
        sleep 2
        status=$(neutron lbaas-loadbalancer-show $1 | awk '/provisioning_status/ {print $4}')
        if [ $status == "ERROR" ]
         then
            echo "$1 ERRORED. Exiting."
            exit 1;
        fi
     done
}

if is_service_enabled q-lbaasv2; then

    neutron lbaas-loadbalancer-create --name lb1 ${SUBNET_NAME}
    wait_for_lb_active "lb1"
    neutron lbaas-listener-create --loadbalancer lb1 --protocol HTTP --protocol-port 80 --name listener1
    sleep 10
    neutron lbaas-pool-create --lb-algorithm ROUND_ROBIN --listener listener1 --protocol HTTP --name pool1
    sleep 10
    neutron lbaas-member-create  --subnet ${SUBNET_NAME} --address ${IP1} --protocol-port 80 pool1
    sleep 10
    neutron lbaas-member-create  --subnet ${SUBNET_NAME} --address ${IP2} --protocol-port 80 pool1

fi
