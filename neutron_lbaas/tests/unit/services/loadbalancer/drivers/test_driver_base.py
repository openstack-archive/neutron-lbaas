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
#

import mock
from neutron.api.v2 import attributes
from neutron import context as ncontext
from neutron.plugins.common import constants

from neutron_lbaas.drivers import driver_mixins
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2


class DummyManager(driver_mixins.BaseManagerMixin):

    def __init__(self, driver):
        super(DummyManager, self).__init__(driver)
        self.driver = driver
        self._db_delete_method = None

    @property
    def db_delete_method(self):
        return self._db_delete_method

    def delete(self, context, obj):
        pass

    def update(self, context, obj_old, obj):
        pass

    def create(self, context, obj):
        pass


class TestBaseManager(test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def _setup_db_data(self, context):
        hm = self.plugin.db.create_healthmonitor(
            context, {'admin_state_up': True,
                      'type': lb_const.HEALTH_MONITOR_HTTP,
                      'delay': 1, 'timeout': 1, 'max_retries': 1})
        lb = self.plugin.db.create_loadbalancer(
            context, {'vip_address': '10.0.0.1',
                      'vip_subnet_id': self.subnet_id,
                      'admin_state_up': True})
        pool = self.plugin.db.create_pool(
            context, {'protocol': lb_const.PROTOCOL_HTTP,
                      'session_persistence': None,
                      'lb_algorithm': lb_const.LB_METHOD_ROUND_ROBIN,
                      'admin_state_up': True, 'healthmonitor_id': hm.id,
                      'loadbalancer_id': lb.id})
        self.plugin.db.create_pool_member(
            context, {'address': '10.0.0.1', 'protocol_port': 80,
                      'admin_state_up': True}, pool.id)
        listener = self.plugin.db.create_listener(
            context, {'protocol_port': 80, 'protocol': lb_const.PROTOCOL_HTTP,
                      'admin_state_up': True, 'loadbalancer_id': lb.id,
                      'default_pool_id': pool.id, 'sni_container_ids': []})
        return listener

    def setUp(self):
        super(TestBaseManager, self).setUp()
        self.context = ncontext.get_admin_context()
        self.driver = mock.Mock()
        self.driver.plugin = self.plugin
        self.manager = DummyManager(self.driver)
        network = self._make_network(self.fmt, 'test-net', True)
        self.subnet = self._make_subnet(
            self.fmt, network, gateway=attributes.ATTR_NOT_SPECIFIED,
            cidr='10.0.0.0/24')
        self.subnet_id = self.subnet['subnet']['id']
        self.listener = self._setup_db_data(self.context)


class TestLBManager(TestBaseManager):

    def setUp(self):
        super(TestLBManager, self).setUp()
        self.manager._db_delete_method = self.plugin.db.delete_loadbalancer

    def test_success_completion(self):
        self.manager.successful_completion(self.context,
                                           self.listener.loadbalancer)
        lb = self.plugin.db.get_loadbalancer(self.context,
                                             self.listener.loadbalancer.id)
        self.assertEqual(constants.ACTIVE, lb.provisioning_status)
        self.assertEqual(lb_const.ONLINE, lb.operating_status)

    def test_success_completion_delete(self):
        self.plugin.db.delete_listener(self.context, self.listener.id)
        self.manager.successful_completion(self.context,
                                           self.listener.loadbalancer,
                                           delete=True)
        self.assertRaises(loadbalancerv2.EntityNotFound,
                          self.plugin.db.get_loadbalancer,
                          self.context,
                          self.listener.loadbalancer.id)

    def test_failed_completion(self):
        self.manager.failed_completion(self.context,
                                       self.listener.loadbalancer)
        lb = self.plugin.db.get_loadbalancer(self.context,
                                             self.listener.loadbalancer.id)
        self.assertEqual(constants.ERROR, lb.provisioning_status)
        self.assertEqual(lb_const.OFFLINE, lb.operating_status)
        listener = self.plugin.db.get_listener(self.context, self.listener.id)
        self.assertEqual(constants.PENDING_CREATE,
                         listener.provisioning_status)
        self.assertEqual(lb_const.OFFLINE, listener.operating_status)


class TestListenerManager(TestBaseManager):
    """This should also cover Pool, Member, and Health Monitor cases."""

    def setUp(self):
        super(TestListenerManager, self).setUp()
        self.manager._db_delete_method = self.plugin.db.delete_listener

    def test_success_completion(self):
        self.manager.successful_completion(self.context, self.listener)
        listener = self.plugin.db.get_listener(self.context, self.listener.id)
        self.assertEqual(constants.ACTIVE, listener.provisioning_status)
        self.assertEqual(lb_const.ONLINE, listener.operating_status)
        self.assertEqual(constants.ACTIVE,
                         listener.loadbalancer.provisioning_status)
        # because the load balancer's original operating status was OFFLINE
        self.assertEqual(lb_const.OFFLINE,
                         listener.loadbalancer.operating_status)

    def test_success_completion_delete(self):
        self.manager.successful_completion(self.context,
                                           self.listener,
                                           delete=True)
        self.assertRaises(loadbalancerv2.EntityNotFound,
                          self.plugin.db.get_listener,
                          self.context,
                          self.listener.loadbalancer.id)

    def test_failed_completion(self):
        self.manager.failed_completion(self.context, self.listener)
        lb = self.plugin.db.get_loadbalancer(self.context,
                                             self.listener.loadbalancer.id)
        self.assertEqual(constants.ACTIVE, lb.provisioning_status)
        self.assertEqual(lb_const.OFFLINE, lb.operating_status)
        listener = self.plugin.db.get_listener(self.context, self.listener.id)
        self.assertEqual(constants.ERROR, listener.provisioning_status)
        self.assertEqual(lb_const.OFFLINE, listener.operating_status)
