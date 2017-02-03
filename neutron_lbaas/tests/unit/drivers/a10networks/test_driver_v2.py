# Copyright 2015, Doug Wiegley (dougwig), A10 Networks
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

import sys

import mock
from neutron_lib import context

from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

with mock.patch.dict(sys.modules, {'a10_neutron_lbaas': mock.Mock()}):
    from neutron_lbaas.drivers.a10networks import driver_v2


class FakeModel(object):
    def __init__(self, id):
        self.id = id
        self.address = '1.1.1.1'
        self.tenant_id = "tennant-was-a-great-doctor"


class ManagerTest(object):
    def __init__(self, parent, manager, model, mocked_root):
        self.parent = parent
        self.context = parent.context
        self.driver = parent.driver
        self.manager = manager
        self.model = model
        self.mocked_root = mocked_root

        self.create(model)
        self.update(model, model)
        self.delete(model)

    def create(self, model):
        self.manager.create(self.context, model)
        self.mocked_root.create.assert_called_with(self.context, model)

    def update(self, old_model, model):
        self.manager.update(self.context, old_model, model)
        self.mocked_root.update.assert_called_with(self.context,
                                                   old_model, model)

    def delete(self, model):
        self.manager.delete(self.context, model)
        self.mocked_root.delete.assert_called_with(self.context, model)

    def refresh(self):
        self.manager.refresh(self.context, self.model)
        self.mocked_root.refresh.assert_called_with(self.context, self.model)

    def stats(self):
        self.manager.stats(self.context, self.model)
        self.mocked_root.stats.assert_called_with(self.context, self.model)


class TestA10ThunderDriver(test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def setUp(self):
        super(TestA10ThunderDriver, self).setUp()
        self.context = context.get_admin_context()
        self.plugin = mock.Mock()
        self.driver = driver_v2.ThunderDriver(self.plugin)
        self.driver.a10 = mock.Mock()

    def test_load_balancer_ops(self):
        m = ManagerTest(self, self.driver.load_balancer,
                        FakeModel("loadbalancer-a10"), self.driver.a10.lb)
        m.refresh()
        m.stats()

    def test_listener_ops(self):
        ManagerTest(self, self.driver.listener, FakeModel("listener-a10"),
                    self.driver.a10.listener)

    def test_pool_ops(self):
        ManagerTest(self, self.driver.pool, FakeModel("pool-10"),
                    self.driver.a10.pool)

    def test_member_ops(self):
        ManagerTest(self, self.driver.member, FakeModel("member-a10"),
                    self.driver.a10.member)

    def test_health_monitor_ops(self):
        ManagerTest(self, self.driver.health_monitor, FakeModel("hm-a10"),
                    self.driver.a10.hm)
