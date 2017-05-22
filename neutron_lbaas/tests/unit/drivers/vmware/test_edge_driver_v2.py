# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

from neutron_lib import context as ncontext

from neutron_lbaas.drivers.vmware import edge_driver_v2
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

DUMMY_CERT = {'id': 'fake_id'}


class FakeModel(object):
    def __init__(self, id):
        self.id = id


class ManagerTest(object):
    def __init__(self, context, manager, model, mocked_nsxv):
        self.context = context
        self.manager = manager
        self.model = model
        self.mocked_nsxv = mocked_nsxv

        self.create(model)
        self.update(model, model)
        self.delete(model)

    def create(self, model):
        self.manager.create(self.context, model)
        if model.id == 'listener':
            model.default_tls_container_id = 'fake_id'
            self.mocked_nsxv.create.assert_called_with(
                self.context, model, certificate=DUMMY_CERT)
        else:
            self.mocked_nsxv.create.assert_called_with(self.context, model)

    def update(self, old_model, model):
        self.manager.update(self.context, old_model, model)
        if model.id == 'listener':
            self.mocked_nsxv.update.assert_called_with(
                self.context, old_model, model, certificate=DUMMY_CERT)
        else:
            self.mocked_nsxv.update.assert_called_with(self.context,
                                                       old_model, model)

    def delete(self, model):
        self.manager.delete(self.context, model)
        self.mocked_nsxv.delete.assert_called_with(self.context, model)

    def refresh(self):
        self.manager.refresh(self.context, self.model)
        self.mocked_nsxv.refresh.assert_called_with(self.context, self.model)

    def stats(self):
        self.manager.stats(self.context, self.model)
        self.mocked_nsxv.stats.assert_called_with(self.context, self.model)


class TestVMWareEdgeLoadBalancerDriverV2(
        test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def setUp(self):
        super(TestVMWareEdgeLoadBalancerDriverV2, self).setUp()
        self.context = ncontext.get_admin_context()
        self.driver = edge_driver_v2.EdgeLoadBalancerDriverV2(self.plugin)

    def _patch_manager(self, mgr):
        mgr.driver = mock.Mock()
        mgr.driver.plugin.db = mock.Mock()
        mgr.driver.plugin.db._core_plugin = mock.Mock()
        mgr.driver.plugin.db._core_plugin.nsx_v = mock.Mock()
        return mgr.driver.plugin.db._core_plugin.lbv2_driver

    def test_load_balancer_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.load_balancer)
        m = ManagerTest(self, self.driver.load_balancer,
                        FakeModel("loadbalancer"),
                        mock_nsxv_driver.loadbalancer)
        m.refresh()
        m.stats()

    def test_listener_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.listener)
        self.driver.listener._get_default_cert = mock.Mock()
        self.driver.listener._get_default_cert.return_value = DUMMY_CERT
        listener = FakeModel("listener")
        listener.default_tls_container_id = None
        ManagerTest(self, self.driver.listener, listener,
                    mock_nsxv_driver.listener)

    def test_pool_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.pool)
        ManagerTest(self, self.driver.pool, FakeModel("pool"),
                    mock_nsxv_driver.pool)

    def test_member_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.member)
        ManagerTest(self, self.driver.member, FakeModel("member"),
                    mock_nsxv_driver.member)

    def test_health_monitor_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.health_monitor)
        ManagerTest(self, self.driver.health_monitor, FakeModel("hm"),
                    mock_nsxv_driver.healthmonitor)

    def test_l7policy_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.l7policy)
        ManagerTest(self, self.driver.l7policy, FakeModel("pol"),
                    mock_nsxv_driver.l7policy)

    def test_l7rule_ops(self):
        mock_nsxv_driver = self._patch_manager(self.driver.l7rule)
        ManagerTest(self, self.driver.l7rule, FakeModel("rule"),
                    mock_nsxv_driver.l7rule)
