This directory contains the neutron-lbaas devstack plugin.  To
configure the neutron load balancer, in the [[local|localrc]] section,
you will need to enable the neutron-lbaas devstack plugin and enable
the LBaaS service by editing the [[local|localrc]] section of your
local.conf file.

Octavia is the LBaaS V2 reference service provider and is used in the
examples below. Enabling another service provider, such as the agent
Haproxy driver, can be done by enabling its driver plugin, if
applicable, and setting the appropriate service provider value for
NEUTRON_LBAAS_SERVICE_PROVIDERV2, like the following:

    NEUTRON_LBAAS_SERVICE_PROVIDERV2="LOADBALANCERV2:Haproxy:neutron_lbaas.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default"

In addition, you can enable multiple
service providers by enabling the applicable driver plugins and
space-delimiting the service provider values in
NEUTRON_LBAAS_SERVICE_PROVIDERV2.

1) Enable the plugins

To enable the plugin, add a line of the form:

    enable_plugin neutron-lbaas <neutron-lbaas GITURL> [GITREF]
    enable_plugin octavia <octavia GITURL> [GITREF]

where

    <neutron-lbaas GITURL> is the URL of a neutron-lbaas repository
    <octavia GITURL> is the URL of a octavia repository
    [GITREF] is an optional git ref (branch/ref/tag).  The default is
             master.

For example

    enable_plugin neutron-lbaas https://git.openstack.org/openstack/neutron-lbaas stable/liberty
    enable_plugin octavia https://git.openstack.org/openstack/octavia stable/liberty

"q-lbaasv2" is the default service enabled with neutron-lbaas plugin.

2) Enable the LBaaS services

To enable the LBaaS services, add lines in the form:


    ENABLED_SERVICES+=<LBAAS-FLAG>
    ENABLED_SERVICES+=<OCTAVIA-FLAGS>

where

    <LBAAS-FLAG> is "q-lbaasv2" for LBaaS Version 2.
    <OCTAVIA-FLAGS> are "octavia" the Octavia driver,
                    "o-cw" the Octavia Controller Worker,
                    "o-hk" the Octavia housekeeping manager,
                    "o-hm" the Octavia Health Manager,
                    and "o-api" the Octavia API service.

to the [[local|localrc]] section of local.conf

For example

    # For LBaaS V2
    ENABLED_SERVICES+=,q-lbaasv2
    ENABLED_SERVICES+=,octavia,o-cw,o-hk,o-hm,o-api


3) Enable the dashboard of LBaaS V2

If using LBaaS V2 and you want to add horizon support, add lines in the form:

    enable_plugin neutron-lbaas-dashboard <neutron-lbaas-dashboard GITURL> [GITREF]

where

    <neutron-lbaas-dashboard GITURL> is the URL of a neutron-lbaas-dashboard repository
    [GITREF] is an optional git ref (branch/ref/tag).  The default is
             master.

For example

    enable_plugin neutron-lbaas-dashboard https://git.openstack.org/openstack/neutron-lbaas-dashboard stable/liberty

Once you enable the neutron-lbaas-dashboard plugin in your local.conf, ensure ``horizon`` and
``q-lbaasv2`` services are enabled. If both of them are enabled,
neutron-lbaas-dashboard will be enabled automatically

For more information, see the "Plugin Interface" section of
https://docs.openstack.org/devstack/latest/plugins.html
