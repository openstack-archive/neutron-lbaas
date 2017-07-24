Welcome!
========

This contains the Tempest testing code for the Neutron Load Balancer as a
Service (LBaaS) service. The tests currently require Tempest to be installed
with a working devstack instance.   It is assumed that you also have Neutron
with the Neutron LBaaS service installed.

Please see ``/neutron-lbaas/devstack/README.md`` for the required
devstack configuration settings for Neutron-LBaaS.

API and SCENARIO Testing with Tempest:
--------------------------------------

Included in the repo are Tempest tests.  If you are familiar with the Tempest
Testing Framework continue on, otherwise please see the
Tempest README :

https://github.com/openstack/tempest/blob/master/README.rst

1. Using Devstack
^^^^^^^^^^^^^^^^^
If you have a running devstack environment, tempest will be automatically
configured and placed in ``/opt/stack/tempest``. It will have a configuration
file, tempest.conf, already set up to work with your devstack installation.

Tests can be run in the following way but you need to have devstack running

for apiv2 tests ::

    $> tox -e apiv2

for scenario tests ::

    $> tox -e scenario

2. Not using Devstack
^^^^^^^^^^^^^^^^^^^^^
6/19/2015 - As we do not have an external OpenStack environment with
Neutron_LBaaS V2 to test with, this is TBD

3. Packages tempest vs. tempest-lib
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
As of 6/19/2015, tests are being migrated to tempest-lib, and while both
that library and these tests are in-progress, a specific subset of tempest
is also included in this repo at neutron_lbaas/tests/tempest/lib.

External Resources:
===================

For more information on the Tempest testing framework see:
<https://github.com/openstack/tempest>
