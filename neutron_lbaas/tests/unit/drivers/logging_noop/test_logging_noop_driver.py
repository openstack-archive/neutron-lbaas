# Copyright 2014, Doug Wiegley (dougwig), A10 Networks
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

import mock
from neutron_lib import context

from neutron_lbaas.drivers.logging_noop import driver
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

log_path = ('neutron_lbaas.drivers.logging_noop.driver.LOG')


class FakeModel(object):
    def __init__(self, id):
        self.id = id

    def attached_to_loadbalancer(self):
        return True


def patch_manager(func):
    @mock.patch(log_path)
    def wrapper(*args):
        log_mock = args[-1]
        manager_test = args[0]
        model = args[1]
        parent = manager_test.parent
        driver = parent.driver
        driver.plugin.reset_mock()

        func(*args[:-1])

        s = str(log_mock.mock_calls[0])
        parent.assertEqual("call.debug(", s[:11])
        parent.assertTrue(s.index(model.id) != -1,
                          msg="Model ID not found in log")

    return wrapper


class ManagerTest(object):
    def __init__(self, parent, manager, model):
        self.parent = parent
        self.manager = manager

        self.create(model)
        self.update(model, model)
        self.delete(model)

    @patch_manager
    def create(self, model):
        self.manager.create(self.parent.context, model)

    @patch_manager
    def update(self, old_model, model):
        self.manager.update(self.parent.context, old_model, model)

    @patch_manager
    def delete(self, model):
        self.manager.delete(self.parent.context, model)


class ManagerTestWithUpdates(ManagerTest):
    def __init__(self, parent, manager, model):
        self.parent = parent
        self.manager = manager

        self.create(model)
        self.update(model, model)
        self.delete(model)

    @patch_manager
    def create(self, model):
        self.manager.create(self.parent.context, model)

    @patch_manager
    def update(self, old_model, model):
        self.manager.update(self.parent.context, old_model, model)

    @patch_manager
    def delete(self, model):
        self.manager.delete(self.parent.context, model)


class LoadBalancerManagerTest(ManagerTestWithUpdates):
    def __init__(self, parent, manager, model):
        super(LoadBalancerManagerTest, self).__init__(parent, manager, model)

        self.create_and_allocate_vip(model)
        self.refresh(model)
        self.stats(model)

    @patch_manager
    def allocates_vip(self):
        self.manager.allocates_vip()

    @patch_manager
    def create_and_allocate_vip(self, model):
        self.manager.create(self.parent.context, model)

    @patch_manager
    def refresh(self, model):
        self.manager.refresh(self.parent.context, model)

    @patch_manager
    def stats(self, model):
        dummy_stats = {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }
        h = self.manager.stats(self.parent.context, model)
        self.parent.assertEqual(dummy_stats, h)


class TestLoggingNoopLoadBalancerDriver(
        test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def _create_fake_models(self):
        id = 'name-001'
        lb = data_models.LoadBalancer(id=id)
        pool = data_models.Pool(id=id, loadbalancer=lb)
        listener = data_models.Listener(id=id, loadbalancer=lb)
        member = data_models.Member(id=id, pool=pool)
        hm = data_models.HealthMonitor(id=id, pool=pool)
        lb.listeners = [listener]
        lb.pools = [pool]
        listener.default_pool = pool
        pool.members = [member]
        pool.healthmonitor = hm
        return lb

    def setUp(self):
        super(TestLoggingNoopLoadBalancerDriver, self).setUp()
        self.context = context.get_admin_context()
        self.plugin = mock.Mock()
        self.driver = driver.LoggingNoopLoadBalancerDriver(self.plugin)
        self.lb = self._create_fake_models()

    def test_load_balancer_ops(self):
        LoadBalancerManagerTest(self, self.driver.load_balancer, self.lb)

    def test_listener_ops(self):
        ManagerTest(self, self.driver.listener, self.lb.listeners[0])

    def test_pool_ops(self):
        ManagerTestWithUpdates(self, self.driver.pool,
                               self.lb.listeners[0].default_pool)

    def test_member_ops(self):
        ManagerTestWithUpdates(self, self.driver.member,
                               self.lb.listeners[0].default_pool.members[0])

    def test_health_monitor_ops(self):
        ManagerTest(self, self.driver.health_monitor,
                    self.lb.listeners[0].default_pool.healthmonitor)
