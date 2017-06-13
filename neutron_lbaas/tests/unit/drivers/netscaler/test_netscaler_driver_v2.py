# Copyright 2015 Citrix Systems
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

from neutron_lbaas.drivers.netscaler import ncc_client
from neutron_lbaas.drivers.netscaler import netscaler_driver_v2
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

LBAAS_DRIVER_CLASS = ('neutron_lbaas.drivers.netscaler.netscaler_driver_v2'
                      '.NetScalerLoadBalancerDriverV2')

NCC_CLIENT_CLASS = ('neutron_lbaas.drivers.netscaler.ncc_client.NSClient')

LBAAS_PROVIDER_NAME = 'NetScaler'
LBAAS_PROVIDER = ('LOADBALANCERV2:%s:%s:default' %
                  (LBAAS_PROVIDER_NAME, LBAAS_DRIVER_CLASS))

log_path = ('neutron_lbaas.drivers.logging_noop.driver.LOG')


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
        self.object_path = None
        self.async_obj_track_list = (netscaler_driver_v2.
                                     PROVISIONING_STATUS_TRACKER)
        self.successful_completion_mock = mock.patch.object(
            manager, "successful_completion").start()
        self.failed_completion_mock = mock.patch.object(
            manager, "failed_completion").start()

    def start_tests(self):
        model = self.model
        self.object_path = "%s/%s" % (
            self.resource_path,
            model.id)
        self.create_success(model)
        self.update_success(model, model)
        self.delete_success(model)

        self.create_failure(model)
        self.update_failure(model, model)
        self.delete_failure(model)

    def _check_success_completion(self):
        """Check if success_completion is called"""
        successful_completion_mock = self.successful_completion_mock
        successful_completion_mock.assert_called_once_with(
            mock.ANY, self.model)
        successful_completion_mock.reset_mock()

    def _check_success_completion_with_delete(self):
        """Check if success_completion is called with delete"""
        successful_completion_mock = self.successful_completion_mock
        successful_completion_mock.assert_called_once_with(
            mock.ANY, self.model, delete=True)
        successful_completion_mock.reset_mock()

    def _check_failure_completion(self):
        """Check failed_completion is called"""
        failed_completion_mock = self.failed_completion_mock
        failed_completion_mock.assert_called_once_with(
            mock.ANY, self.model)
        failed_completion_mock.reset_mock()

    def _set_response_error(self, mock_instance):
        errorcode = ncc_client.NCCException.RESPONSE_ERROR
        mock_instance.side_effect = (ncc_client
                                     .NCCException(errorcode))

    def create(self, model):
        self.manager.create(self.parent.context, model)
        create_resource_mock = self.parent.create_resource_mock
        self.parent.assertTrue(create_resource_mock.called)
        resource_path = self.resource_path
        object_name = self.object_name
        create_payload = mock.ANY
        create_resource_mock.assert_called_once_with(
            mock.ANY, resource_path, object_name, create_payload)

    def update(self, old_model, model):
        self.manager.update(self.parent.context, old_model, model)
        update_resource_mock = self.parent.update_resource_mock
        self.parent.assertTrue(update_resource_mock.called)
        object_path = self.object_path
        object_name = self.object_name
        update_payload = mock.ANY
        update_resource_mock.assert_called_once_with(
            mock.ANY, object_path, object_name, update_payload)

    def delete(self, model):
        self.manager.delete(self.parent.context, model)
        remove_resource_mock = self.parent.remove_resource_mock
        self.parent.assertTrue(remove_resource_mock.called)
        object_path = self.object_path
        remove_resource_mock.assert_called_once_with(
            mock.ANY, object_path)

    def check_op_status(self, model, delete=False):
        loadbalancer = model.root_loadbalancer
        if hasattr(self, "async_obj_track_list") and self.async_obj_track_list:
            self.parent.assertIn(
                loadbalancer.id, self.async_obj_track_list)
        else:
            if delete:
                self._check_success_completion_with_delete()
            else:
                self._check_success_completion()

    def create_success(self, model):
        self.create(model)
        self.check_op_status(model)
        self.parent.create_resource_mock.reset()

    def update_success(self, old_model, model):
        self.update(old_model, model)
        self.check_op_status(model)
        self.parent.update_resource_mock.reset_mock()

    def delete_success(self, model):
        self.delete(model)
        self.check_op_status(model, delete=True)
        self.parent.remove_resource_mock.reset_mock()

    def create_failure(self, model):
        create_resource_mock = self.parent.create_resource_mock
        self._set_response_error(create_resource_mock)

        try:
            self.create(model)
        except Exception:
            pass

        self._check_failure_completion()
        create_resource_mock.reset_mock()
        create_resource_mock.side_effect = mock_create_resource_func

    def update_failure(self, old_model, model):
        update_resource_mock = self.parent.update_resource_mock
        self._set_response_error(update_resource_mock)

        try:
            self.update(old_model, model)
        except Exception:
            pass

        self._check_failure_completion()
        update_resource_mock.reset_mock()
        update_resource_mock.side_effect = mock_update_resource_func

    def delete_failure(self, model):
        remove_resource_mock = self.parent.remove_resource_mock
        self._set_response_error(remove_resource_mock)
        try:
            self.delete(model)
        except Exception:
            pass

        self._check_failure_completion()
        remove_resource_mock.reset_mock()
        remove_resource_mock.side_effect = mock_remove_resource_func


class LoadBalancerManagerTest(ManagerTest):

    def __init__(self, parent, manager, model):
        super(LoadBalancerManagerTest, self).__init__(parent, manager, model)
        self.object_name = netscaler_driver_v2.LB_RESOURCE
        self.resource_path = "%s/%s" % (
            netscaler_driver_v2.RESOURCE_PREFIX,
            netscaler_driver_v2.LBS_RESOURCE)
        self.start_tests()


class ListenerManagerTest(ManagerTest):

    def __init__(self, parent, manager, model):
        super(ListenerManagerTest, self).__init__(parent, manager, model)
        self.object_name = netscaler_driver_v2.LISTENER_RESOURCE
        self.resource_path = "%s/%s" % (
            netscaler_driver_v2.RESOURCE_PREFIX,
            netscaler_driver_v2.LISTENERS_RESOURCE)
        self.start_tests()


class PoolManagerTest(ManagerTest):

    def __init__(self, parent, manager, model):
        super(PoolManagerTest, self).__init__(parent, manager, model)
        self.object_name = netscaler_driver_v2.POOL_RESOURCE
        self.resource_path = "%s/%s" % (
            netscaler_driver_v2.RESOURCE_PREFIX,
            netscaler_driver_v2.POOLS_RESOURCE)
        self.start_tests()


class MemberManagerTest(ManagerTest):

    def __init__(self, parent, manager, model):
        super(MemberManagerTest, self).__init__(parent, manager, model)
        self.object_name = netscaler_driver_v2.MEMBER_RESOURCE
        self.resource_path = "%s/%s/%s/%s" % (
            netscaler_driver_v2.RESOURCE_PREFIX,
            netscaler_driver_v2.POOLS_RESOURCE,
            model.pool.id,
            netscaler_driver_v2.MEMBERS_RESOURCE)
        self.start_tests()


class MonitorManagerTest(ManagerTest):

    def __init__(self, parent, manager, model):
        super(MonitorManagerTest, self).__init__(parent, manager, model)
        self.object_name = netscaler_driver_v2.MONITOR_RESOURCE
        self.resource_path = "%s/%s" % (
            netscaler_driver_v2.RESOURCE_PREFIX,
            netscaler_driver_v2.MONITORS_RESOURCE)
        self.start_tests()


class TestNetScalerLoadBalancerDriverV2(
        test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def _create_fake_models(self):
        id = 'name-001'
        lb = data_models.LoadBalancer(id=id)
        listener = data_models.Listener(id=id, loadbalancer=lb)
        pool = data_models.Pool(id=id, listener=listener)
        member = data_models.Member(id=id, pool=pool)
        hm = data_models.HealthMonitor(id=id, pool=pool)
        lb.listeners = [listener]
        listener.default_pool = pool
        pool.members = [member]
        pool.healthmonitor = hm
        return lb

    def _get_fake_network_info(self):
        network_info = {}
        network_info["network_id"] = "network_id_1"
        network_info["subnet_id"] = "subnet_id_1"
        return network_info

    def setUp(self):
        super(TestNetScalerLoadBalancerDriverV2, self).setUp()
        self.context = mock.Mock()

        self.plugin = mock.Mock()
        self.lb = self._create_fake_models()
        mock.patch.object(netscaler_driver_v2, 'LOG').start()

        network_info_mock = mock.patch.object(
            netscaler_driver_v2.PayloadPreparer, "get_network_info").start()
        network_info_mock.return_value = self._get_fake_network_info()

        mock.patch.object(
            netscaler_driver_v2.NetScalerLoadBalancerDriverV2,
            "_init_status_collection").start()

        """mock the NSClient class (REST client)"""
        client_mock_cls = mock.patch(NCC_CLIENT_CLASS).start()

        """mock the REST methods of the NSClient class"""

        self.client_mock_instance = client_mock_cls.return_value
        self.create_resource_mock = self.client_mock_instance.create_resource
        self.create_resource_mock.side_effect = mock_create_resource_func
        self.update_resource_mock = self.client_mock_instance.update_resource
        self.update_resource_mock.side_effect = mock_update_resource_func
        self.retrieve_resource_mock = (self.client_mock_instance
                                           .retrieve_resource)
        self.retrieve_resource_mock.side_effect = mock_retrieve_resource_func
        self.remove_resource_mock = self.client_mock_instance.remove_resource
        self.remove_resource_mock.side_effect = mock_remove_resource_func

        self.driver = netscaler_driver_v2.NetScalerLoadBalancerDriverV2(
            self.plugin)
        self.assertTrue(client_mock_cls.called)

    def test_load_balancer_ops(self):
        LoadBalancerManagerTest(self, self.driver.load_balancer, self.lb)

    def test_listener_ops(self):
        ListenerManagerTest(self, self.driver.listener, self.lb.listeners[0])

    def test_pool_ops(self):
        PoolManagerTest(self, self.driver.pool,
                        self.lb.listeners[0].default_pool)

    def test_member_ops(self):
        MemberManagerTest(self, self.driver.member,
                          self.lb.listeners[0].default_pool.members[0])

    def test_health_monitor_ops(self):
        MonitorManagerTest(self, self.driver.health_monitor,
                           self.lb.listeners[0].default_pool.healthmonitor)


def mock_create_resource_func(*args, **kwargs):
    return 201, {}


def mock_update_resource_func(*args, **kwargs):
    return 202, {}


def mock_retrieve_resource_func(*args, **kwargs):
    return 200, {}


def mock_remove_resource_func(*args, **kwargs):
    return 200, {}
