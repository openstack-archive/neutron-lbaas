# Copyright 2014 Brocade Communications Systems, Inc.
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
#
# Pattabi Ayyasami (pattabi), Brocade Communication Systems, Inc.
#
import sys

import mock
from neutron_lib import context

from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2
with mock.patch.dict(sys.modules, {'brocade_neutron_lbaas': mock.Mock()}):
    from neutron_lbaas.drivers.brocade import driver_v2 as driver


class FakeModel(object):
    def __init__(self, id):
        self.id = id

    def attached_to_loadbalancer(self):
        return True


class ManagerTest(object):
    def __init__(self, parent, manager, model):
        self.parent = parent
        self.manager = manager
        self.model = model

        self.create(model)
        self.update(model, model)
        self.delete(model)

    def create(self, model):
        self.manager.create(self.parent.context, model)

    def update(self, old_model, model):
        self.manager.update(self.parent.context, old_model, model)

    def delete(self, model):
        self.manager.delete(self.parent.context, model)


class LoadBalancerManagerTest(ManagerTest):
    def __init__(self, parent, manager, model):
        super(LoadBalancerManagerTest, self).__init__(parent, manager, model)

        self.refresh(model)
        self.stats(model)

    def refresh(self, model):
        self.manager.refresh(self.parent.context, model)
        self.parent.driver.device_driver.refresh \
            .assert_called_once_with(model)

    def stats(self, model):
        self.manager.stats(self.parent.context, model)
        self.parent.driver.device_driver.stats.assert_called_once_with(model)


class TestBrocadeLoadBalancerDriver(
        test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def _create_fake_models(self):
        id = 'name-001'
        lb = data_models.LoadBalancer(id=id)
        listener = data_models.Listener(id=id, loadbalancer=lb)
        pool = data_models.Pool(id=id, loadbalancer=lb)
        member = data_models.Member(id=id, pool=pool)
        hm = data_models.HealthMonitor(id=id, pool=pool)
        lb.listeners = [listener]
        lb.pools = [pool]
        listener.default_pool = pool
        pool.members = [member]
        pool.healthmonitor = hm
        return lb

    def setUp(self):
        super(TestBrocadeLoadBalancerDriver, self).setUp()
        self.context = context.get_admin_context()
        self.plugin = mock.Mock()
        self.driver = driver.BrocadeLoadBalancerDriver(self.plugin)
        self.lb = self._create_fake_models()

    def test_load_balancer_ops(self):
        LoadBalancerManagerTest(self, self.driver.load_balancer,
                                self.lb)
        self.driver.device_driver.create_loadbalancer \
            .assert_called_once_with(self.lb)
        self.driver.device_driver.update_loadbalancer \
            .assert_called_once_with(self.lb, self.lb)
        self.driver.device_driver.delete_loadbalancer \
            .assert_called_once_with(self.lb)

    def test_listener_ops(self):
        ManagerTest(self, self.driver.listener, self.lb.listeners[0])
        self.driver.device_driver.create_listener \
            .assert_called_once_with(self.lb.listeners[0])
        self.driver.device_driver.update_listener \
            .assert_called_once_with(self.lb.listeners[0],
                                     self.lb.listeners[0])
        self.driver.device_driver.delete_listener \
            .assert_called_once_with(self.lb.listeners[0])

    def test_pool_ops(self):
        pool_fake_model = self.lb.listeners[0].default_pool
        ManagerTest(self, self.driver.pool,
                    pool_fake_model)
        self.driver.device_driver.update_pool \
            .assert_called_once_with(pool_fake_model, pool_fake_model)
        self.driver.device_driver.delete_pool \
            .assert_called_once_with(pool_fake_model)

    def test_member_ops(self):
        member_fake_model = self.lb.listeners[0].default_pool.members[0]
        ManagerTest(self, self.driver.member,
                    member_fake_model)
        self.driver.device_driver.create_member \
            .assert_called_once_with(member_fake_model)
        self.driver.device_driver.update_member \
            .assert_called_once_with(member_fake_model, member_fake_model)
        self.driver.device_driver.delete_member \
            .assert_called_once_with(member_fake_model)

    def test_health_monitor_ops(self):
        hm_fake_model = self.lb.listeners[0].default_pool.healthmonitor
        ManagerTest(self, self.driver.health_monitor, hm_fake_model)
        self.driver.device_driver.update_healthmonitor \
            .assert_called_once_with(hm_fake_model, hm_fake_model)
        self.driver.device_driver.delete_healthmonitor \
            .assert_called_once_with(hm_fake_model)
