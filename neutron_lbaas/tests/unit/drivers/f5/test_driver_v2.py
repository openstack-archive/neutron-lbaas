# Copyright 2016 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import sys

import mock
from neutron import context

from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

with mock.patch.dict(
        sys.modules, {'f5lbaasdriver': mock.Mock(__version__="0.1.1")}):
    from neutron_lbaas.drivers.f5 import driver_v2


class FakeModel(object):
    def __init__(self, id):
        self.id = id


class DriverTest(object):
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


class TestF5DriverV2(test_db_loadbalancerv2.LbaasPluginDbTestCase):
    """Unit tests for F5 LBaaSv2 service provider.

    All tests follow the same pattern: call driver method and test
    that driver delegated request to its driver implementation object.

    To test independent of full neutron-lbaas test suite:
        tox -e py27 -- neutron_lbaas.tests.unit.drivers.f5
    """

    def setUp(self):
        super(TestF5DriverV2, self).setUp()
        plugin = mock.Mock()

        self.driver = driver_v2.F5LBaaSV2Driver(plugin)
        self.driver.f5 = mock.Mock()
        self.context = context.get_admin_context()

    def test_load_balancer(self):

        tester = DriverTest(self,
                            self.driver.load_balancer,
                            FakeModel("loadbalancer-01"),
                            self.driver.f5.loadbalancer)

        # additional loadbalancer-only tests
        tester.refresh()
        tester.stats()

    def test_listener(self):
        DriverTest(self,
                   self.driver.listener,
                   FakeModel("listener-01"),
                   self.driver.f5.listener)

    def test_pool(self):
        DriverTest(self,
                   self.driver.pool,
                   FakeModel("pool-01"),
                   self.driver.f5.pool)

    def test_member(self):
        DriverTest(self,
                   self.driver.member,
                   FakeModel("member-01"),
                   self.driver.f5.member)

    def test_health_monitor(self):
        DriverTest(self,
                   self.driver.health_monitor,
                   FakeModel("hm-01"),
                   self.driver.f5.healthmonitor)
