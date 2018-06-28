=======================================
Neutron-LBaaS to Octavia Migration Tool
=======================================


This tool allows you to migrate existing, running load balancers from
Neutron-LBaaS to Octavia. This is intended as a one-time migration tool used
to move load balancers from being managed by Neutron-LBaaS to be managed by
Octavia.

.. warning::
    We recommend you make a backup of both the neutron and octavia databases
    before running this tool.

.. warning::
    You must have the provider driver loaded and enabled in Octavia for the
    load  balancer(s) you are migrating.

.. note::
    This tool will not convert a load balancer from one provider to a
    different provider. It will only migrate a load balancer using the
    same provider in Neutron-LBaaS and Octavia.

Background
----------

Neutron-LBaaS was deprecated during the Queens release of OpenStack.

Theory of Operation
-------------------

Octavia is an improved superset of the Neutron-LBaaS API extension to Neutron.
Because of this relationship the object model is very similar between the two.
This tool will access the Neutron database (which contains the neutron-lbaas
tables and records) and intelligently migrate the management records from the
Neutron database to the Octavia database. The tool will also update neutron
object ownership to reflect Octavia taking ownership for those objects.

Objects that will change ownership are:
Neutron ports
Neutron security groups

Usage
-----

.. line-block::

    $ nlbaas2octavia --config-file <filename> [--all | --lb_id <id> | --project_id <project_id>]

      '--all' Migrate all neutron-lbaas load balancers
      '--config-file' The path to the configuration file
      '--lb_id <id>' Migrate one load balancer by ID
      '--project_id <project_id>' Migrate all load balancers owned by this project ID
