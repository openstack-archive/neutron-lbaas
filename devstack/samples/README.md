This directory contains sample files for configuring neutron LBaaS using
devstack. By copying these files into the main devstack directory (not the
neutron-lbaas/devstack directory directly above this one), and running
stack.sh, you will create a fully functioning OpenStack installation running
a neutron-lbaas load balancer.

1) Copy the files into place:

    cp local.conf local.sh webserver.sh <DEVSTACK_DIR>

where

    <DEVSTCK_DIR> is the main devstack directory.  Note: this is not
    neutron-lbaas/devstack.

2) Build your devstack:

    cd <DEVSTACK_DIR>
    ./stack.sh

3) Test your loadbalancer:

    a) Determine the loadbalancer IP:

        source openrc admin admin
        neutron lbaas-loadbalancer-show lb1 | grep vip_address
        curl <LB_IP>

    where <LB_IP> is the VIP address for lb1.  The subsequent invocations of
    "curl <LB_IP>" should demonstrate that the load balancer is alternating
    between two member nodes.
