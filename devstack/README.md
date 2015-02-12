This directory contains the neutron-lbaas devstack plugin.  To
configure the neutron load balancer, in the [[local|localrc]] section,
you will need to enable the neutron-lbaas devstack plugin and enable
the LBaaS service by editing the [[local|localrc]] section of your
local.conf file.

1) Enable the plugin

To enable the plugin, add a line of the form:

    enable_plugin neutron-lbaas <GITURL> [GITREF]

where

    <GITURL> is the URL of a neutron-lbaas repository
    [GITREF] is an optional git ref (branch/ref/tag).  The default is
             master.

For example

    enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas stable/kilo

2) Enable the LBaaS service

To enable the LBaaS service, add a line of the form:


    ENABLED_SERVICES+=<LBAAS-FLAG>

where

    <LBAAS-FLAG> is "q-lbaasv1" for LBaaS Version 1, or "q-lbaasv2"
                 for LBaaS Version 2.  "q-lbaas" is synonymous with
                 "q-lbaasv1".

to the [[local|localrc]] section of local.conf

For example

    # For LBaaS V2
    ENABLED_SERVICES+=q-lbaasv2

For more information, see the "Externally Hosted Plugins" section of
http://docs.openstack.org/developer/devstack/plugins.html.
