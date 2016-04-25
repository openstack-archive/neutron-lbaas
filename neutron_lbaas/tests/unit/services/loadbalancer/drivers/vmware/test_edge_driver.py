# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
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

from neutron import context
from neutron.plugins.common import constants

from neutron import manager
from neutron_lbaas.db.loadbalancer import loadbalancer_db as lb_db
from neutron_lbaas.services.loadbalancer.drivers.vmware import db
from neutron_lbaas.tests import nested
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancer


EDGE_PROVIDER = ('LOADBALANCER:vmwareedge:neutron_lbaas.services.'
                 'loadbalancer.drivers.vmware.edge_driver.'
                 'EdgeLoadbalancerDriver:default')

HEALTHMON_ID = 'cb297614-66c9-4048-8838-7e87231569ae'
POOL_ID = 'b3dfb476-6fdf-4ddd-b6bd-e86ae78dc30b'
TENANT_ID = 'f9135d3a908842bd8d785816c2c90d36'
SUBNET_ID = 'c8924d77-ff57-406f-a13c-a8c5def01fc9'
VIP_ID = 'f6393b95-34b0-4299-9001-cbc21e32bf03'
VIP_PORT_ID = '49c547e3-6775-42ea-a607-91e8f1a07432'
MEMBER_ID = '90dacafd-9c11-4af7-9d89-234e2d1fedb1'

EDGE_ID = 'edge-x'
EDGE_POOL_ID = '111'
EDGE_VSE_ID = '222'
APP_PROFILE_ID = '333'
EDGE_MON_ID = '444'
EDGE_FW_RULE_ID = '555'


class TestLoadBalancerPluginBase(
    test_db_loadbalancer.LoadBalancerPluginDbTestCase):
    def setUp(self):
        super(TestLoadBalancerPluginBase, self).setUp(
            lbaas_provider=EDGE_PROVIDER)

        loaded_plugins = manager.NeutronManager().get_service_plugins()
        self.service_plugin = loaded_plugins[constants.LOADBALANCER]
        self.edge_driver = self.service_plugin.drivers['vmwareedge']
        self.service_plugin._core_plugin.nsx_v = mock.Mock()


class TestEdgeLoadBalancerPlugin(TestLoadBalancerPluginBase):
    def setUp(self):
        super(TestEdgeLoadBalancerPlugin, self).setUp()
        self.context = context.get_admin_context()

    def test_create_pool_successful(self):
        pool = {'id': POOL_ID}

        with nested(
            mock.patch.object(db, 'add_nsxv_edge_pool_mapping'),
            mock.patch.object(self.edge_driver, 'pool_successful')
        ) as (mock_add_pool, mock_pool_successful):
            self.edge_driver.create_pool_successful(self.context,
                                                    pool,
                                                    EDGE_ID, EDGE_POOL_ID)
            mock_add_pool.assert_called_with(self.context, POOL_ID, EDGE_ID,
                                             EDGE_POOL_ID)
            mock_pool_successful.assert_called_with(self.context, pool)

    def test_delete_pool_successful(self):
        pool = {'id': POOL_ID}

        with nested(
            mock.patch.object(self.service_plugin, '_delete_db_pool'),
            mock.patch.object(db, 'delete_nsxv_edge_pool_mapping')
        ) as (mock_del_db_pool, mock_del_mapping):
            self.edge_driver.delete_pool_successful(self.context, pool)
            mock_del_db_pool.assert_called_with(self.context, POOL_ID)
            mock_del_mapping.assert_called_with(self.context, POOL_ID)

    def test_pool_successful(self):
        pool = {'id': POOL_ID}

        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.pool_successful(self.context, pool)
            mock_update_status.assert_called_with(self.context, lb_db.Pool,
                                                  pool['id'], constants.ACTIVE)

    def test_pool_failed(self):
        pool = {'id': POOL_ID}

        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.pool_failed(self.context, pool)
            mock_update_status.assert_called_with(self.context, lb_db.Pool,
                                                  pool['id'], constants.ERROR)

    def test_create_pool(self):
        lbaas_pool = {
            'status': 'PENDING_CREATE', 'lb_method': 'ROUND_ROBIN',
            'protocol': 'HTTP', 'description': '', 'health_monitors': [],
            'members': [], 'status_description': None, 'id': POOL_ID,
            'vip_id': None, 'name': 'testpool', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'health_monitors_status': [], 'provider': 'vmwareedge'}

        with mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                               'create_pool') as mock_create_pool:

            self.edge_driver.create_pool(self.context, lbaas_pool)
            mock_create_pool.assert_called_with(self.context, lbaas_pool)

    def test_update_pool(self):
        from_pool = {
            'status': 'ACTIVE', 'lb_method': 'ROUND_ROBIN',
            'protocol': 'HTTP', 'description': '', 'health_monitors': [],
            'members': [], 'status_description': None, 'id': POOL_ID,
            'vip_id': None, 'name': 'testpool2', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'health_monitors_status': [], 'provider': 'vmwareedge'}

        to_pool = {
            'status': 'PENDING_UPDATE', 'lb_method': 'LEAST_CONNECTIONS',
            'protocol': 'HTTP', 'description': '', 'health_monitors': [],
            'members': [], 'status_description': None, 'id': POOL_ID,
            'vip_id': None, 'name': 'testpool2', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'health_monitors_status': [], 'provider': 'vmwareedge'}

        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'update_pool')
        ) as (mock_get_mapping, mock_update_pool):

            mock_get_mapping.return_value = mapping
            self.edge_driver.update_pool(self.context, from_pool, to_pool)
            mock_update_pool.assert_called_with(self.context, from_pool,
                                                to_pool, mapping)

    def test_delete_pool(self):
        lbaas_pool = {
            'status': 'PENDING_CREATE', 'lb_method': 'ROUND_ROBIN',
            'protocol': 'HTTP', 'description': '', 'health_monitors': [],
            'members': [], 'status_description': None, 'id': POOL_ID,
            'vip_id': None, 'name': 'testpool', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'health_monitors_status': [], 'provider': 'vmwareedge'}
        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin, 'get_pool',
                              return_value={}),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'delete_pool')
        ) as (mock_get_mapping, mock_get_pool, mock_delete_pool):

            mock_get_mapping.return_value = mapping
            self.edge_driver.delete_pool(self.context, lbaas_pool)
            mock_delete_pool.assert_called_with(self.context, lbaas_pool,
                                                mapping)

    def test_create_vip_successful(self):
        vip = {'pool_id': POOL_ID}
        with nested(
            mock.patch.object(db, 'add_nsxv_edge_vip_mapping'),
            mock.patch.object(self.edge_driver, 'vip_successful')
        ) as (mock_add_vip_mapping, mock_vip_successful):

            self.edge_driver.create_vip_successful(
                self.context, vip, EDGE_ID, APP_PROFILE_ID, EDGE_VSE_ID,
                EDGE_FW_RULE_ID)

            mock_add_vip_mapping.assert_called_with(
                self.context, POOL_ID, EDGE_ID, APP_PROFILE_ID,
                EDGE_VSE_ID, EDGE_FW_RULE_ID)
            mock_vip_successful.assert_called_with(self.context, vip)

    def test_delete_vip_successful(self):
        vip = {'pool_id': POOL_ID, 'id': VIP_ID}
        with nested(
            mock.patch.object(db, 'delete_nsxv_edge_vip_mapping'),
            mock.patch.object(self.service_plugin, '_delete_db_vip')
        ) as (mock_del_vip_mapping, mock_del_vip):

            self.edge_driver.delete_vip_successful(self.context, vip)
            mock_del_vip_mapping.assert_called_with(self.context, POOL_ID)
            mock_del_vip.assert_called_with(self.context, VIP_ID)

    def test_vip_successful(self):
        vip = {'pool_id': POOL_ID, 'id': VIP_ID}
        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.vip_successful(self.context, vip)
            mock_update_status.assert_called_with(
                self.context, lb_db.Vip, VIP_ID, constants.ACTIVE)

    def test_vip_failed(self):
        vip = {'pool_id': POOL_ID, 'id': VIP_ID}
        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.vip_failed(self.context, vip)
            mock_update_status.assert_called_with(
                self.context, lb_db.Vip, VIP_ID, constants.ERROR)

    def test_create_vip(self):
        lbaas_vip = {
            'status': 'PENDING_CREATE', 'protocol': 'HTTP',
            'description': '', 'address': '10.0.0.8', 'protocol_port': 555,
            'port_id': VIP_PORT_ID, 'id': VIP_ID, 'status_description': None,
            'name': 'testvip1', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'connection_limit': -1, 'pool_id': POOL_ID,
            'session_persistence': {'type': 'SOURCE_IP'}}
        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'create_vip')
        ) as (mock_get_mapping, mock_create_vip):
            mock_get_mapping.return_value = mapping
            self.edge_driver.create_vip(self.context, lbaas_vip)
            mock_create_vip.assert_called_with(self.context, lbaas_vip,
                                               mapping)

    def test_update_vip(self):
        vip_from = {
            'status': 'ACTIVE', 'protocol': 'HTTP', 'description': '',
            'address': '10.0.0.8', 'protocol_port': 555,
            'port_id': VIP_PORT_ID, 'id': VIP_ID, 'status_description': None,
            'name': 'testvip1', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'connection_limit': -1, 'pool_id': POOL_ID,
            'session_persistence': {'type': 'SOURCE_IP'}}
        vip_to = {
            'status': 'PENDING_UPDATE', 'protocol': 'HTTP',
            'description': '', 'address': '10.0.0.8', 'protocol_port': 555,
            'port_id': VIP_PORT_ID, 'id': VIP_ID, 'status_description': None,
            'name': 'testvip1', 'admin_state_up': True,
            'subnet_id': SUBNET_ID, 'tenant_id': TENANT_ID,
            'connection_limit': -1, 'pool_id': POOL_ID,
            'session_persistence': {'type': 'HTTP_COOKIE'}}
        pool_mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}
        vip_mapping = {'edge_id': EDGE_ID, 'edge_vse_id': EDGE_VSE_ID,
                       'edge_app_profile_id': APP_PROFILE_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(db, 'get_nsxv_edge_vip_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'update_vip')
        ) as (mock_get_pool_mapping, mock_get_vip_mapping, mock_upd_vip):

            mock_get_pool_mapping.return_value = pool_mapping
            mock_get_vip_mapping.return_value = vip_mapping
            self.edge_driver.update_vip(self.context, vip_from, vip_to)
            mock_upd_vip.assert_called_with(self.context, vip_from, vip_to,
                                            pool_mapping, vip_mapping)

    def test_delete_vip(self):
        lbaas_vip = {
            'status': 'PENDING_DELETE', 'protocol': 'HTTP',
            'description': '', 'address': '10.0.0.11', 'protocol_port': 555,
            'port_id': VIP_PORT_ID, 'id': VIP_ID, 'status_description': None,
            'name': 'testvip', 'admin_state_up': True, 'subnet_id': SUBNET_ID,
            'tenant_id': TENANT_ID, 'connection_limit': -1,
            'pool_id': POOL_ID, 'session_persistence': None}
        mapping = {'edge_id': EDGE_ID, 'edge_vse_id': EDGE_VSE_ID,
                   'edge_app_profile_id': APP_PROFILE_ID,
                   'edge_fw_rule_id': EDGE_FW_RULE_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_vip_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'delete_vip')
        ) as (mock_get_mapping, mock_del_vip):

            mock_get_mapping.return_value = mapping
            self.edge_driver.delete_vip(self.context, lbaas_vip)
            mock_del_vip.assert_called_with(self.context, lbaas_vip, mapping)

    def test_member_successful(self):
        member = {'id': MEMBER_ID}
        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.member_successful(self.context, member)
            mock_update_status.assert_called_with(
                self.context, lb_db.Member, member['id'], constants.ACTIVE)

    def test_member_failed(self):
        member = {'id': MEMBER_ID}
        with mock.patch.object(self.service_plugin, 'update_status') as (
                mock_update_status):
            self.edge_driver.member_failed(self.context, member)
            mock_update_status.assert_called_with(
                self.context, lb_db.Member, member['id'], constants.ERROR)

    def test_create_member(self):
        lbaas_member = {
            'admin_state_up': True, 'status': 'PENDING_CREATE',
            'status_description': None, 'weight': 5, 'address': '10.0.0.4',
            'tenant_id': TENANT_ID, 'protocol_port': 555, 'id': MEMBER_ID,
            'pool_id': POOL_ID}
        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'create_member')
        ) as (mock_get_mapping, mock_create_member):

            mock_get_mapping.return_value = mapping
            self.edge_driver.create_member(self.context, lbaas_member)
            mock_create_member.assert_called_with(self.context, lbaas_member,
                                                  mapping)

    def test_update_member(self):
        member_from = {
            'admin_state_up': True, 'status': 'PENDING_UPDATE',
            'status_description': None, 'weight': 5, 'address': '10.0.0.4',
            'tenant_id': TENANT_ID, 'protocol_port': 555, 'id': MEMBER_ID,
            'pool_id': POOL_ID}
        member_to = {
            'admin_state_up': True, 'status': 'ACTIVE',
            'status_description': None, 'weight': 10, 'address': '10.0.0.4',
            'tenant_id': TENANT_ID, 'protocol_port': 555, 'id': MEMBER_ID,
            'pool_id': POOL_ID}
        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'update_member')
        ) as (mock_get_mapping, mock_update_member):

            mock_get_mapping.return_value = mapping
            self.edge_driver.update_member(self.context, member_from,
                                           member_to)
            mock_update_member.assert_called_with(self.context, member_from,
                                                  member_to, mapping)

    def test_delete_member(self):
        lbaas_member = {
            'admin_state_up': True, 'status': 'PENDING_DELETE',
            'status_description': None, 'weight': 5, 'address': '10.0.0.4',
            'tenant_id': TENANT_ID, 'protocol_port': 555, 'id': MEMBER_ID,
            'pool_id': POOL_ID}
        mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'delete_member')
        ) as (mock_get_mapping, mock_delete_member):

            mock_get_mapping.return_value = mapping
            self.edge_driver.delete_member(self.context, lbaas_member)
            mock_delete_member.assert_called_with(self.context, lbaas_member,
                                                  mapping)

    def test_create_pool_health_monitor_successful(self):
        hmon = {'id': HEALTHMON_ID}
        with nested(
            mock.patch.object(db, 'add_nsxv_edge_monitor_mapping'),
            mock.patch.object(self.edge_driver,
                              'pool_health_monitor_successful')
        ) as (mock_add_pool_mon_mapping, mock_pool_hmon_successful):
            self.edge_driver.create_pool_health_monitor_successful(
                self.context, hmon, POOL_ID, EDGE_ID, EDGE_MON_ID)
            mock_add_pool_mon_mapping.assert_called_with(
                self.context, HEALTHMON_ID, EDGE_ID, EDGE_MON_ID)
            mock_pool_hmon_successful.assert_called_with(self.context,
                                                         hmon, POOL_ID)

    def test_delete_pool_health_monitor_successful(self):
        hmon = {'id': HEALTHMON_ID, 'pool_id': POOL_ID}
        hmon_mapping = {'edge_id': EDGE_ID}
        with nested(
            mock.patch.object(db, 'delete_nsxv_edge_monitor_mapping'),
            mock.patch.object(self.service_plugin,
                              '_delete_db_pool_health_monitor')
        ) as (mock_del_pool_hmon_mapping, mock_del_db_pool_hmon):

            self.edge_driver.delete_pool_health_monitor_successful(
                self.context, hmon, POOL_ID, hmon_mapping)
            mock_del_pool_hmon_mapping.assert_called_with(
                self.context, HEALTHMON_ID, EDGE_ID)
            mock_del_db_pool_hmon.assert_called_with(
                self.context, HEALTHMON_ID, POOL_ID)

    def test_pool_health_monitor_successful(self):
        hmon = {'id': HEALTHMON_ID}
        with mock.patch.object(self.service_plugin,
                               'update_pool_health_monitor') as (
                mock_update_hmon):
            self.edge_driver.pool_health_monitor_successful(self.context,
                                                            hmon, POOL_ID)
            mock_update_hmon.assert_called_with(
                self.context, HEALTHMON_ID, POOL_ID, constants.ACTIVE, '')

    def test_pool_health_monitor_failed(self):
        hmon = {'id': HEALTHMON_ID}
        with mock.patch.object(self.service_plugin,
                               'update_pool_health_monitor') as (
                mock_update_hmon):
            self.edge_driver.pool_health_monitor_failed(self.context, hmon,
                                                        POOL_ID)
            mock_update_hmon.assert_called_with(
                self.context, HEALTHMON_ID, POOL_ID, constants.ERROR, '')

    def test_create_pool_health_monitor(self):
        hmon = {
            'admin_state_up': True, 'tenant_id': TENANT_ID, 'delay': 5,
            'max_retries': 5, 'timeout': 5, 'pools': [
                {'status': 'PENDING_CREATE', 'status_description': None,
                 'pool_id': POOL_ID}],
            'type': 'PING', 'id': HEALTHMON_ID}
        pool_mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(db, 'get_nsxv_edge_monitor_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'create_pool_health_monitor')
        ) as (mock_get_pool_mapping, mock_get_mon_mapping,
              mock_create_pool_hm):

            mock_get_pool_mapping.return_value = pool_mapping
            mock_get_mon_mapping.return_value = None
            self.edge_driver.create_pool_health_monitor(self.context,
                                                        hmon, POOL_ID)
            mock_create_pool_hm.assert_called_with(self.context, hmon, POOL_ID,
                                                   pool_mapping, None)

    def test_update_pool_health_monitor(self):
        from_hmon = {
            'admin_state_up': True, 'tenant_id': TENANT_ID, 'delay': 5,
            'max_retries': 5, 'timeout': 5, 'pools': [
                {'status': 'PENDING_UPDATE', 'status_description': None,
                 'pool_id': POOL_ID}],
            'type': 'PING', 'id': HEALTHMON_ID}
        to_hmon = {
            'admin_state_up': True, 'tenant_id': TENANT_ID, 'delay': 5,
            'max_retries': 10, 'timeout': 5, 'pools': [
                {'status': 'ACTIVE', 'status_description': None,
                 'pool_id': POOL_ID}],
            'type': 'PING', 'id': HEALTHMON_ID}
        pool_mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}
        mon_mapping = {'edge_id': EDGE_ID, 'edge_monitor_id': EDGE_MON_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(db, 'get_nsxv_edge_monitor_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'update_pool_health_monitor')
        ) as (mock_get_pool_mapping, mock_get_mon_mapping, mock_upd_pool_hm):

            mock_get_pool_mapping.return_value = pool_mapping
            mock_get_mon_mapping.return_value = mon_mapping
            self.edge_driver.update_pool_health_monitor(
                self.context, from_hmon, to_hmon, POOL_ID)

            mock_upd_pool_hm.assert_called_with(
                self.context, from_hmon, to_hmon, POOL_ID, mon_mapping)

    def test_delete_pool_health_monitor(self):
        hmon = {
            'admin_state_up': True, 'tenant_id': TENANT_ID, 'delay': 5,
            'max_retries': 5, 'timeout': 5, 'pools': [
                {'status': 'PENDING_DELETE', 'status_description': None,
                 'pool_id': POOL_ID}],
            'type': 'PING', 'id': HEALTHMON_ID}
        pool_mapping = {'edge_id': EDGE_ID, 'edge_pool_id': EDGE_POOL_ID}
        mon_mapping = {'edge_id': EDGE_ID, 'edge_monitor_id': EDGE_MON_ID}

        with nested(
            mock.patch.object(db, 'get_nsxv_edge_pool_mapping'),
            mock.patch.object(db, 'get_nsxv_edge_monitor_mapping'),
            mock.patch.object(self.service_plugin._core_plugin.nsx_v,
                              'delete_pool_health_monitor')
        ) as (mock_get_pool_mapping, mock_get_mon_mapping, mock_del_pool_hm):

            mock_get_pool_mapping.return_value = pool_mapping
            mock_get_mon_mapping.return_value = mon_mapping
            self.edge_driver.delete_pool_health_monitor(self.context, hmon,
                                                        POOL_ID)
            mock_del_pool_hm.assert_called_with(self.context, hmon, POOL_ID,
                                                pool_mapping, mon_mapping)
