# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Rackspace Inc.
# All Rights Reserved.
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

from tempest import config
from tempest.lib.common.utils import data_utils
from tempest import test
import testscenarios

from neutron_lbaas.tests.tempest.v2.api import base

CONF = config.CONF


# Use local tempest conf if one is available.
# This usually means we're running tests outside of devstack
if os.path.exists('./tests/tempest/etc/dev_tempest.conf'):
    CONF.set_config_path('./tests/tempest/etc/dev_tempest.conf')


class AdminStateTests(testscenarios.TestWithScenarios,
                      base.BaseTestCase):
    """
      Scenario Tests(admin_state_up tests):

      This class supplies the resource set up methods and the check
      operating status methods for the admin_sate_up tests.

    """

    @classmethod
    def resource_setup(cls):
        super(AdminStateTests, cls).resource_setup()
        if not test.is_extension_enabled("lbaasv2", "network"):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.tenant_id = cls.subnet.get('tenant_id')
        cls.subnet_id = cls.subnet.get('id')
        cls.protocol = 'HTTP'
        cls.port = 8081
        cls.lb_algorithm = 'ROUND_ROBIN'
        cls.address = '127.0.0.1'

    @classmethod
    def resource_setup_load_balancer(cls, admin_state_up_flag):
        cls.create_lb_kwargs = {'tenant_id': cls.tenant_id,
                                'vip_subnet_id': cls.subnet_id,
                                'admin_state_up': admin_state_up_flag}
        cls.load_balancer = cls._create_active_load_balancer(
            **cls.create_lb_kwargs)
        cls.load_balancer_id = cls.load_balancer['id']

    @classmethod
    def resource_setup_listener(cls, admin_state_up_flag):
        cls.create_listener_kwargs = {'loadbalancer_id': cls.load_balancer_id,
                                      'protocol': cls.protocol,
                                      'protocol_port': cls.port,
                                      'admin_state_up': admin_state_up_flag
                                      }
        cls.listener = cls._create_listener(
            **cls.create_listener_kwargs)
        cls.listener_id = cls.listener['id']

    @classmethod
    def resource_setup_pool(cls, admin_state_up_flag):
        cls.create_pool_kwargs = {'protocol': cls.protocol,
                                  'lb_algorithm': cls.lb_algorithm,
                                  'listener_id': cls.listener_id,
                                  'admin_state_up': admin_state_up_flag
                                  }
        cls.pool = cls._create_pool(
            **cls.create_pool_kwargs)
        cls.pool_id = cls.pool['id']

    @classmethod
    def resource_setup_member(cls, admin_state_up_flag):
        cls.create_member_kwargs = {'address': cls.address,
                                    'protocol_port': cls.port,
                                    'subnet_id': cls.subnet_id,
                                    'admin_state_up': admin_state_up_flag}
        cls.member = cls._create_member(
            cls.pool_id, **cls.create_member_kwargs)
        cls.member_id = cls.member['id']

    @classmethod
    def resource_set_health_monitor(cls, admin_state_up_flag, creator):
        cls.create_hm_kwargs = {'type': cls.protocol,
                                'delay': 3,
                                'max_retries': 10,
                                'timeout': 5,
                                'pool_id': cls.pool_id,
                                'admin_state_up': admin_state_up_flag}
        cls.health_monitor = creator(**cls.create_hm_kwargs)
        cls.health_monitor_id = cls.health_monitor['id']

    @classmethod
    def resource_cleanup(cls):
        super(AdminStateTests, cls).resource_cleanup()

    def check_lb_operating_status(self,
                                  load_balancer,
                                  listeners=None,
                                  pools=None,
                                  members=None):
        if bool(load_balancer) and self.load_balancer.get('admin_state_up'):
            self.assertEqual(
                load_balancer.get('operating_status'), 'ONLINE')
            return True

        elif bool(load_balancer):
            self.assertEqual(
                load_balancer.get('operating_status'), 'DISABLED')
            if bool(listeners):
                self.assertEqual(listeners[0].
                                 get('operating_status'), 'DISABLED')
                if bool(pools):
                    self.assertEqual(pools[0].
                                     get('operating_status'), 'DISABLED')
                    if bool(members):
                        self.assertEqual(members[0].
                                         get('operating_status'), 'DISABLED')

            return False

    def check_listener_operating_status(self,
                                        listeners,
                                        pools=None,
                                        members=None):
        if bool(listeners) and self.listener.get('admin_state_up'):
            self.assertEqual(listeners[0].
                             get('operating_status'), 'ONLINE')
            return True

        elif bool(listeners):
            self.assertEqual(listeners[0].
                             get('operating_status'), 'DISABLED')
            if bool(pools):
                self.assertEqual(pools[0].
                                 get('operating_status'), 'DISABLED')
                if bool(members):
                    self.assertEqual(members[0].
                                     get('operating_status'), 'DISABLED')

            return False

    def check_pool_operating_status(self,
                                    pools,
                                    members=None):
        if bool(pools) and self.pool.get('admin_state_up'):
            self.assertEqual(pools[0].
                             get('operating_status'), 'ONLINE')
            return True

        elif bool(pools):
            self.assertEqual(pools[0].
                             get('operating_status'), 'DISABLED')
            if bool(members):
                        self.assertEqual(members[0].
                                         get('operating_status'), 'DISABLED')

            return False

    def check_member_operating_status(self, members):
        if bool(members) and self.member.get('admin_state_up'):
            self.assertEqual(members[0].
                             get('operating_status'), 'ONLINE')
            return True
        elif bool(members):
            self.assertEqual(members[0].
                             get('operating_status'), 'DISABLED')
            return False

    def check_health_monitor_provisioning_status(self, health_monitor):
        if bool(health_monitor) and self.health_monitor.get('admin_state_up'):
            self.assertEqual(health_monitor.get('provisioning_status'),
                             'ACTIVE')
            return True
        elif bool(health_monitor):
            self.assertEqual(health_monitor.get('provisioning_status'),
                             'DISABLED')
            return False

    def check_operating_status(self):
        statuses = (self.load_balancers_client.
                    get_load_balancer_status_tree
                    (self.load_balancer_id))

        load_balancer = statuses['loadbalancer']
        listeners = load_balancer['listeners']
        pools = None
        members = None
        health_monitor = None

        if bool(listeners):
            pools = listeners[0]['pools']
        if bool(pools):
            members = pools[0]['members']
            health_monitor = pools[0]['healthmonitor']

        if self.check_lb_operating_status(load_balancer,
                                          listeners,
                                          pools,
                                          members):
            if self.check_listener_operating_status(listeners,
                                                    pools,
                                                    members):
                if self.check_pool_operating_status(pools,
                                                    members):
                    self.check_member_operating_status(members)
                    self.check_health_monitor_provisioning_status(
                        health_monitor)
