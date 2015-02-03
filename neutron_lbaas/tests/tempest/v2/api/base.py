# Copyright 2015 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import time

from neutron.i18n import _, _LI
from neutron_lbaas.tests.tempest.v2.clients import health_monitors_client
from neutron_lbaas.tests.tempest.v2.clients import listeners_client
from neutron_lbaas.tests.tempest.v2.clients import load_balancers_client
from neutron_lbaas.tests.tempest.v2.clients import members_client
from neutron_lbaas.tests.tempest.v2.clients import pools_client
from tempest.api.network import base
from tempest import clients as tempest_clients
from tempest import config
from tempest.openstack.common import log as logging

CONF = config.CONF

# Use local tempest conf if one is available.
# This usually means we're running tests outside of devstack
if os.path.exists('./tests/tempest/etc/dev_tempest.conf'):
    CONF.set_config_path('./tests/tempest/etc/dev_tempest.conf')


class BaseTestCase(base.BaseNetworkTest):

    _lbs_to_delete = []

    @classmethod
    def resource_setup(cls):
        super(BaseTestCase, cls).resource_setup()

        credentials = cls.isolated_creds.get_primary_creds()
        mgr = tempest_clients.Manager(credentials=credentials)
        auth_provider = mgr.get_auth_provider(credentials)
        client_args = [auth_provider, 'network', 'regionOne']

        cls.load_balancers_client = \
            load_balancers_client.LoadBalancersClientJSON(*client_args)
        cls.listeners_client = \
            listeners_client.ListenersClientJSON(*client_args)
        cls.pools_client = pools_client.PoolsClientJSON(*client_args)
        cls.members_client = members_client.MembersClientJSON(*client_args)
        cls.health_monitors_client = \
            health_monitors_client.HealthMonitorsClientJSON(*client_args)

    @classmethod
    def resource_cleanup(cls):
        for lb_id in cls._lbs_to_delete:
            lb = cls.load_balancers_client.get_load_balancer_status_tree(
                lb_id).get('loadbalancer')
            for listener in lb.get('listeners'):
                for pool in listener.get('pools'):
                    cls._try_delete_resource(cls.pools_client.delete_pool,
                                             pool.get('id'))
                    cls._wait_for_load_balancer_status(lb_id)
                    health_monitor = pool.get('healthmonitor')
                    if health_monitor:
                        cls._try_delete_resource(
                            cls.health_monitors_client.delete_health_monitor,
                            health_monitor.get('id'))
                    cls._wait_for_load_balancer_status(lb_id)
                cls._try_delete_resource(cls.listeners_client.delete_listener,
                                         listener.get('id'))
                cls._wait_for_load_balancer_status(lb_id)
            cls._try_delete_resource(
                cls.load_balancers_client.delete_load_balancer, lb_id)
        super(BaseTestCase, cls).resource_cleanup()

    @classmethod
    def setUpClass(cls):
        cls.LOG = logging.getLogger(cls._get_full_case_name())
        super(BaseTestCase, cls).setUpClass()

    def setUp(self):
        self.LOG.info(_LI('Starting: {0}').format(self._testMethodName))
        super(BaseTestCase, self).setUp()

    def tearDown(self):
        super(BaseTestCase, self).tearDown()
        self.LOG.info(_LI('Finished: {0}\n').format(self._testMethodName))

    @classmethod
    def _create_load_balancer(cls, **kwargs):
        try:
            lb = cls.load_balancers_client.create_load_balancer(**kwargs)
        except Exception:
            raise Exception(_("Failed to create load balancer..."))
        cls._lbs_to_delete.append(lb.get('id'))
        return lb

    @classmethod
    def _create_active_load_balancer(cls, **kwargs):
        lb = cls._create_load_balancer(**kwargs)
        lb = cls._wait_for_load_balancer_status(lb.get('id'))
        return lb

    @classmethod
    def _wait_for_load_balancer_status(cls, load_balancer_id,
                                       provisioning_status='ACTIVE',
                                       operating_status='ONLINE'):
        interval_time = 10
        timeout = 300
        end_time = time.time() + timeout
        while time.time() < end_time:
            lb = cls.load_balancers_client.get_load_balancer(load_balancer_id)
            if (lb.get('provisioning_status') == provisioning_status and
                    lb.get('operating_status') == operating_status):
                break
            time.sleep(interval_time)
        else:
            raise Exception(
                _("Wait for load balancer ran for {timeout} seconds and did "
                  "not observe {lb_id} reach {provisioning_status} "
                  "provisioning status and {operating_status} "
                  "operating status.").format(
                      timeout=timeout,
                      lb_id=lb.get('id'),
                      provisioning_status=provisioning_status,
                      operating_status=operating_status))
        return lb

    @classmethod
    def _get_full_case_name(cls):
        name = '{module}:{case_name}'.format(
            module=cls.__module__,
            case_name=cls.__name__
        )
        return name
