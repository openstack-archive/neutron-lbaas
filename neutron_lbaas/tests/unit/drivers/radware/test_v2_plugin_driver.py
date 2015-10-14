# Copyright 2015 Radware LTD. All rights reserved
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

import contextlib
import copy
import mock
import re

from neutron import context
from neutron import manager
from neutron.plugins.common import constants
from oslo_config import cfg
from oslo_serialization import jsonutils
from six.moves import queue as Queue

from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.drivers.radware import exceptions as r_exc
from neutron_lbaas.drivers.radware import v2_driver
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2

GET_200 = ('/api/workflow/', '/api/workflowTemplate')
SERVER_DOWN_CODES = (-1, 301, 307)


class QueueMock(Queue.Queue):
    def __init__(self, completion_handler):
        self.completion_handler = completion_handler
        super(QueueMock, self).__init__()

    def put_nowait(self, oper):
        self.completion_handler(oper)


def _recover_function_mock(action, resource, data, headers, binary=False):
    pass


def rest_call_function_mock(action, resource, data, headers, binary=False):
    if rest_call_function_mock.RESPOND_WITH_ERROR:
        return 400, 'error_status', 'error_description', None
    if rest_call_function_mock.RESPOND_WITH_SERVER_DOWN in SERVER_DOWN_CODES:
        val = rest_call_function_mock.RESPOND_WITH_SERVER_DOWN
        return val, 'error_status', 'error_description', None
    if action == 'GET':
        return _get_handler(resource)
    elif action == 'DELETE':
        return _delete_handler(resource)
    elif action == 'POST':
        return _post_handler(resource, binary)
    else:
        return 0, None, None, None


def _get_handler(resource):
    if resource.startswith(GET_200[1]):
        return 200, '', '', rest_call_function_mock.WF_TEMPLATES_TO_RETURN

    if resource.startswith(GET_200[0]):
        if rest_call_function_mock.WORKFLOW_MISSING:
            data = jsonutils.loads('{"complete":"True", "success": "True"}')
            return 404, '', '', data
        elif resource.endswith('parameters'):
            return 200, '', '', {'stats': {'bytes_in': 100,
                'total_connections': 2, 'active_connections': 1,
                'bytes_out': 200}}
        else:
            return 200, '', '', ''

    if resource.startswith(GET_200):
        return 200, '', '', ''
    else:
        data = jsonutils.loads('{"complete":"True", "success": "True"}')
        return 202, '', '', data


def _delete_handler(resource):
    return 404, '', '', {'message': 'Not Found'}


def _post_handler(resource, binary):
    if re.search(r'/api/workflow/.+/action/.+', resource):
        data = jsonutils.loads('{"uri":"some_uri"}')
        return 202, '', '', data
    elif re.search(r'/api/service\?name=.+', resource):
        data = jsonutils.loads('{"links":{"actions":{"provision":"someuri"}}}')
        return 201, '', '', data
    elif binary:
        return 201, '', '', ''
    else:
        return 202, '', '', ''

RADWARE_PROVIDER = ('LOADBALANCERV2:radwarev2:neutron_lbaas.'
                    'drivers.radware.v2_driver.'
                    'RadwareLBaaSV2Driver:default')

WF_SRV_PARAMS = {
    "name": "_REPLACE_", "tenantId": "_REPLACE_", "haPair": False,
    "sessionMirroringEnabled": False, "islVlan": -1,
    "primary": {
        "capacity": {
            "throughput": 1000, "sslThroughput": 100,
            "compressionThroughput": 100, "cache": 20},
        "network": {
            "type": "portgroup", "portgroups": "_REPLACE_"},
        "adcType": "VA", "acceptableAdc": "Exact"},
    "resourcePoolIds": []}

WF_CREATE_PARAMS = {'parameters':
    {"provision_service": True, "configure_l3": True, "configure_l4": True,
     "twoleg_enabled": False, "ha_network_name": "HA-Network",
     "ha_ip_pool_name": "default", "allocate_ha_vrrp": True,
     "allocate_ha_ips": True, "data_port": 1,
     "data_ip_address": "192.168.200.99", "data_ip_mask": "255.255.255.0",
     "gateway": "192.168.200.1", "ha_port": 2}}
WF_APPLY_EMPTY_LB_PARAMS = {'parameters': {
    'loadbalancer': {'listeners': [], 'admin_state_up': True,
    'pip_address': u'10.0.0.2', 'vip_address': u'10.0.0.2'}}}


class TestLBaaSDriverBase(
    test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def setUp(self):
        super(TestLBaaSDriverBase, self).setUp(
            lbaas_provider=RADWARE_PROVIDER)

        loaded_plugins = manager.NeutronManager().get_service_plugins()
        self.plugin_instance = loaded_plugins[constants.LOADBALANCERV2]
        self.driver = self.plugin_instance.drivers['radwarev2']


class TestLBaaSDriverRestClient(TestLBaaSDriverBase):
    def setUp(self):

        cfg.CONF.set_override('vdirect_address', '1.1.1.1',
                              group='radwarev2')
        cfg.CONF.set_override('ha_secondary_address', '1.1.1.2',
                              group='radwarev2')
        super(TestLBaaSDriverRestClient, self).setUp()

        self.flip_servers_mock = mock.Mock(
            return_value=None)
        self.recover_mock = mock.Mock(
            side_effect=_recover_function_mock)

        self.orig_recover = self.driver.rest_client._recover
        self.orig_flip_servers = self.driver.rest_client._flip_servers
        self.driver.rest_client._flip_servers = self.flip_servers_mock
        self.driver.rest_client._recover = self.recover_mock

    def test_recover_was_called(self):
        """Call REST client which fails and verify _recover is called."""
        self.driver.rest_client.call('GET', '/api/workflowTemplate',
                                     None, None)
        self.recover_mock.assert_called_once_with('GET',
                                                  '/api/workflowTemplate',
                                                  None, None, False)

    def test_flip_servers(self):
        server = self.driver.rest_client.server
        sec_server = self.driver.rest_client.secondary_server

        self.driver.rest_client._recover = self.orig_recover
        self.driver.rest_client._flip_servers = self.orig_flip_servers
        self.driver.rest_client.call('GET', '/api/workflowTemplate',
                                     None, None)
        self.assertEqual(server, self.driver.rest_client.secondary_server)
        self.assertEqual(sec_server, self.driver.rest_client.server)


class CertMock(cert_manager.Cert):
    def __init__(self, cert_container):
        pass

    def get_certificate(self):
        return "certificate"

    def get_intermediates(self):
        return "intermediates"

    def get_private_key(self):
        return "private_key"

    def get_private_key_passphrase(self):
        return "private_key_passphrase"


class TestLBaaSDriver(TestLBaaSDriverBase):
    def setUp(self):
        super(TestLBaaSDriver, self).setUp()

        templates_to_return = [{'name': self.driver.workflow_template_name}]
        for t in self.driver.child_workflow_template_names:
            templates_to_return.append({'name': t})
        rest_call_function_mock.__dict__.update(
            {'RESPOND_WITH_ERROR': False, 'WORKFLOW_MISSING': True,
             'WORKFLOW_TEMPLATE_MISSING': True,
             'RESPOND_WITH_SERVER_DOWN': 200,
             'WF_TEMPLATES_TO_RETURN': templates_to_return})

        self.operation_completer_start_mock = mock.Mock(
            return_value=None)
        self.operation_completer_join_mock = mock.Mock(
            return_value=None)
        self.driver_rest_call_mock = mock.Mock(
            side_effect=rest_call_function_mock)
        self.flip_servers_mock = mock.Mock(
            return_value=None)
        self.recover_mock = mock.Mock(
            side_effect=_recover_function_mock)

        self.driver.completion_handler.start = (
            self.operation_completer_start_mock)
        self.driver.completion_handler.join = (
            self.operation_completer_join_mock)
        self.driver.rest_client.call = self.driver_rest_call_mock
        self.driver.rest_client._call = self.driver_rest_call_mock
        self.driver.completion_handler.rest_client.call = (
            self.driver_rest_call_mock)

        self.driver.queue = QueueMock(
            self.driver.completion_handler.handle_operation_completion)

        self.addCleanup(self.driver.completion_handler.join)

    def test_verify_workflow_templates(self):
        templates_to_return = []
        for t in self.driver.child_workflow_template_names:
            templates_to_return.append({'name': t})
        rest_call_function_mock.__dict__.update(
            {'WF_TEMPLATES_TO_RETURN': templates_to_return})
        message = r_exc.WorkflowTemplateMissing.message % \
            {'workflow_template': self.driver.workflow_template_name}
        try:
            self.driver._verify_workflow_templates()
        except r_exc.WorkflowTemplateMissing as e:
            self.assertEqual(message, e.msg)

        templates_to_return.append(
            {'name': self.driver.workflow_template_name})
        rest_call_function_mock.__dict__.update(
            {'WF_TEMPLATES_TO_RETURN': templates_to_return})
        try:
            self.driver._verify_workflow_templates()
            self.assertTrue(True)
        except r_exc.WorkflowTemplateMissing as e:
            self.assertTrue(False)

    def test_wf_created_on_first_member_creation(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(
                    loadbalancer_id=lb_id) as listener:
                    with self.pool(
                        protocol=lb_const.PROTOCOL_HTTP,
                        listener_id=listener['listener']['id']) as pool:
                        self.driver_rest_call_mock.assert_has_calls([])
                        with self.member(pool_id=pool['pool']['id'],
                                         subnet=vip_sub, address='10.0.1.10'):
                            calls = [
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    mock.ANY,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.driver_rest_call_mock.assert_has_calls(calls)

    def test_wf_deleted_on_lb_deletion(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                get_calls = [
                    mock.call('GET', u'/api/workflow/LB_' +
                        lb['loadbalancer']['id'], None, None)]
                with self.listener(
                    loadbalancer_id=lb['loadbalancer']['id']) as listener:
                    with self.pool(
                        protocol=lb_const.PROTOCOL_HTTP,
                        listener_id=listener['listener']['id']) as pool:
                        with self.member(pool_id=pool['pool']['id'],
                                         subnet=vip_sub, address='10.0.1.10'):
                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                        self.driver_rest_call_mock.assert_has_calls(get_calls)
                        self.driver_rest_call_mock.reset_mock()
                    self.driver_rest_call_mock.assert_has_calls(get_calls)
                    self.driver_rest_call_mock.reset_mock()
                self.driver_rest_call_mock.assert_has_calls(get_calls)
                self.driver_rest_call_mock.reset_mock()
            self.driver_rest_call_mock.assert_any_call(
                'DELETE', u'/api/workflow/LB_' + lb['loadbalancer']['id'],
                None, None)

    def test_lb_crud(self):
        with self.subnet(cidr='10.0.0.0/24') as s:
            with self.loadbalancer(subnet=s, no_delete=True) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as l:
                    with self.pool(
                        protocol=lb_const.PROTOCOL_HTTP,
                        listener_id=l['listener']['id']) as p:
                        self.driver_rest_call_mock.assert_has_calls([])

                        self.plugin_instance.update_loadbalancer(
                            context.get_admin_context(),
                            lb_id, {'loadbalancer': lb})
                        self.driver_rest_call_mock.assert_has_calls([])

                        lb_db = self.plugin_instance.db.get_loadbalancer(
                            context.get_admin_context(),
                            lb_id)
                        self.driver.load_balancer.refresh(
                            context.get_admin_context(), lb_db)
                        self.driver_rest_call_mock.assert_has_calls([])

                        with self.member(
                            no_delete=True, pool_id=p['pool']['id'],
                            subnet=s, address='10.0.1.10') as m:

                            m_data = {
                                "id": m['member']['id'],
                                "address": "10.0.1.10",
                                "protocol_port": 80,
                                "weight": 1, "admin_state_up": True,
                                "subnet": "255.255.255.255",
                                "mask": "255.255.255.255",
                                "gw": "255.255.255.255",
                                "admin_state_up": True}
                            wf_apply_params = {'parameters': {
                                'listeners': [{
                                    "id": l['listener']['id'],
                                    "admin_state_up": True,
                                    "protocol_port": 80,
                                    "protocol": lb_const.PROTOCOL_HTTP,
                                    "connection_limit": -1,
                                    "admin_state_up": True,
                                    "default_pool": {
                                        "id": p['pool']['id'],
                                        "protocol": lb_const.PROTOCOL_HTTP,
                                        "lb_algorithm":
                                            "ROUND_ROBIN",
                                        "admin_state_up": True,
                                        "members": [m_data]}}],
                                "admin_state_up": True,
                                "pip_address": "10.0.0.2",
                                "vip_address": "10.0.0.2"}}
                            calls = [
                                mock.call(
                                    'POST', '/api/workflowTemplate/' +
                                    'os_lb_v2?name=LB_' + lb_id, mock.ANY,
                                    v2_driver.TEMPLATE_HEADER),
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]

                            self.driver_rest_call_mock.assert_has_calls(calls)
                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            calls = [
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.plugin_instance.update_loadbalancer(
                                context.get_admin_context(),
                                lb_id, {'loadbalancer': lb})
                            self.driver_rest_call_mock.assert_has_calls(calls)
                            self.driver_rest_call_mock.reset_mock()

                            lb_db = self.plugin_instance.db.get_loadbalancer(
                                context.get_admin_context(), lb_id)
                            self.driver.load_balancer.refresh(
                                context.get_admin_context(), lb_db)
                            self.driver_rest_call_mock.assert_has_calls(calls)
                            self.driver_rest_call_mock.reset_mock()

                self.plugin_instance.delete_loadbalancer(
                    context.get_admin_context(), lb_id)
                self.driver_rest_call_mock.assert_any_call(
                    'DELETE', '/api/workflow/LB_' + lb_id,
                    None, None)
                self.assertRaises(loadbalancerv2.EntityNotFound,
                                  self.plugin_instance.get_loadbalancer,
                                  context.get_admin_context(), lb_id)

    def test_lb_stats(self):
        with self.subnet(cidr='10.0.0.0/24') as s:
            with self.loadbalancer(subnet=s) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as l:
                    with self.pool(
                        protocol=lb_const.PROTOCOL_HTTP,
                        listener_id=l['listener']['id']) as p:
                        with self.member(
                            no_delete=True, pool_id=p['pool']['id'],
                            subnet=s, address='10.0.1.10'):

                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            stats = self.plugin_instance.stats(
                                context.get_admin_context(), lb_id,)
                            self.assertEqual({'stats': {'bytes_in': 100,
                                'total_connections': 2,
                                'active_connections': 1, 'bytes_out': 200}},
                                stats)

    def test_member_crud(self):
        with self.subnet(cidr='10.0.0.0/24') as s:
            with self.loadbalancer(subnet=s) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as l:
                    with self.pool(
                        protocol=lb_const.PROTOCOL_HTTP,
                        listener_id=l['listener']['id']) as p:
                        with contextlib.nested(
                            self.member(
                                no_delete=True, pool_id=p['pool']['id'],
                                subnet=s, address='10.0.1.10'),
                            self.member(
                                no_delete=True, pool_id=p['pool']['id'],
                                subnet=s, address='10.0.1.20')) as (m1, m2):

                            m1_data = {
                                "id": m1['member']['id'],
                                "address": "10.0.1.10",
                                "protocol_port": 80,
                                "weight": 1, "admin_state_up": True,
                                "subnet": "255.255.255.255",
                                "mask": "255.255.255.255",
                                "gw": "255.255.255.255",
                                "admin_state_up": True}
                            m2_data = {
                                "id": m2['member']['id'],
                                "address": "10.0.1.20",
                                "protocol_port": 80,
                                "weight": 1, "admin_state_up": True,
                                "subnet": "255.255.255.255",
                                "mask": "255.255.255.255",
                                "gw": "255.255.255.255",
                                "admin_state_up": True}
                            pool_data = {
                                "id": p['pool']['id'],
                                "protocol": lb_const.PROTOCOL_HTTP,
                                "lb_algorithm": "ROUND_ROBIN",
                                "admin_state_up": True,
                                "members": [m1_data, m2_data]}
                            listener_data = {
                                    "id": l['listener']['id'],
                                    "admin_state_up": True,
                                    "protocol_port": 80,
                                    "protocol": lb_const.PROTOCOL_HTTP,
                                    "connection_limit": -1,
                                    "admin_state_up": True,
                                    "default_pool": pool_data}
                            wf_apply_params = {'parameters': {
                                'listeners': [listener_data],
                                "admin_state_up": True,
                                "pip_address": "10.0.0.2",
                                "vip_address": "10.0.0.2"}}
                            calls = [
                                mock.call(
                                    'POST', '/api/workflowTemplate/' +
                                    'os_lb_v2?name=LB_' + lb_id, mock.ANY,
                                    v2_driver.TEMPLATE_HEADER),
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]

                            self.driver_rest_call_mock.assert_has_calls(calls)
                            self.driver_rest_call_mock.reset_mock()
                            member = self.plugin_instance.db.get_pool_member(
                                context.get_admin_context(),
                                m1['member']['id']).to_dict(pool=False)

                            member['weight'] = 2
                            m1_data['weight'] = 2
                            self.plugin_instance.update_pool_member(
                                context.get_admin_context(),
                                m1['member']['id'], p['pool']['id'],
                                {'member': member})
                            calls = [
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.driver_rest_call_mock.assert_has_calls(calls)
                            self.driver_rest_call_mock.reset_mock()

                            self.plugin_instance.delete_pool_member(
                                context.get_admin_context(),
                                m2['member']['id'], p['pool']['id'])
                            pool_data["members"] = [m1_data]
                            calls = [
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.driver_rest_call_mock.assert_has_calls(calls)
                            lb = self.plugin_instance.db.get_loadbalancer(
                                context.get_admin_context(),
                                lb_id).to_dict(listener=False)
                            self.assertEqual('ACTIVE',
                                             lb['provisioning_status'])

    def test_build_objects_with_tls(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with contextlib.nested(
                    mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                               'cert_parser', autospec=True),
                    mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                               'CERT_MANAGER_PLUGIN.CertManager',
                               autospec=True)
                ) as (cert_parser_mock, cert_manager_mock):
                    cert_mock = mock.Mock(spec=cert_manager.Cert)
                    cert_mock.get_certificate.return_value = 'certificate'
                    cert_mock.get_intermediates.return_value = 'intermediates'
                    cert_mock.get_private_key.return_value = 'private_key'
                    cert_mock.get_private_key_passphrase.return_value = \
                        'private_key_passphrase'
                    cert_manager_mock.get_cert.return_value = cert_mock
                    cert_parser_mock.validate_cert.return_value = True

                    with self.listener(
                        protocol=lb_const.PROTOCOL_TERMINATED_HTTPS,
                        loadbalancer_id=lb_id,
                        default_tls_container_ref='def1',
                        sni_container_refs=['sni1', 'sni2']) as listener:
                        with self.pool(
                            protocol=lb_const.PROTOCOL_HTTP,
                            listener_id=listener['listener']['id']) as pool:
                            with self.member(pool_id=pool['pool']['id'],
                                             subnet=vip_sub,
                                             address='10.0.1.10') as m:

                                wf_srv_params = copy.deepcopy(WF_SRV_PARAMS)
                                wf_params = copy.deepcopy(WF_CREATE_PARAMS)

                                wf_srv_params['name'] = 'srv_' + (
                                    vip_sub['subnet']['network_id'])
                                wf_srv_params['tenantId'] = self._tenant_id
                                wf_srv_params['primary']['network'][
                                    'portgroups'] = [vip_sub['subnet'][
                                         'network_id']]
                                wf_params['parameters']['service_params'] = (
                                    wf_srv_params)

                                m_data = {
                                    "id": m['member']['id'],
                                    "address": "10.0.1.10",
                                    "protocol_port": 80,
                                    "weight": 1, "admin_state_up": True,
                                    "subnet": "255.255.255.255",
                                    "mask": "255.255.255.255",
                                    "gw": "255.255.255.255",
                                    'admin_state_up': True}
                                default_tls_cert_data = {
                                    'id': 'def1',
                                    'certificate': 'certificate',
                                    'intermediates': 'intermediates',
                                    'private_key': 'private_key',
                                    'passphrase': 'private_key_passphrase'}
                                sni1_tls_cert_data = {
                                    'id': 'sni1',
                                    'position': 0,
                                    'certificate': 'certificate',
                                    'intermediates': 'intermediates',
                                    'private_key': 'private_key',
                                    'passphrase': 'private_key_passphrase'}
                                sni2_tls_cert_data = {
                                    'id': 'sni2',
                                    'position': 1,
                                    'certificate': 'certificate',
                                    'intermediates': 'intermediates',
                                    'private_key': 'private_key',
                                    'passphrase': 'private_key_passphrase'}
                                wf_apply_one_leg_params = {'parameters': {
                                    'listeners': [{
                                        "id": listener['listener']['id'],
                                        "admin_state_up": True,
                                        "protocol_port": 80,
                                        "protocol":
                                        lb_const.PROTOCOL_TERMINATED_HTTPS,
                                        "connection_limit": -1,
                                        "default_pool": {
                                            "id": pool['pool']['id'],
                                            "protocol": lb_const.PROTOCOL_HTTP,
                                            "lb_algorithm": "ROUND_ROBIN",
                                            "admin_state_up": True,
                                            "members": [m_data]},
                                        "default_tls_certificate":
                                        default_tls_cert_data,
                                        "sni_tls_certificates": [
                                             sni1_tls_cert_data,
                                             sni2_tls_cert_data]}],
                                    "admin_state_up": True,
                                    "pip_address": "10.0.0.2",
                                    "vip_address": "10.0.0.2"}}

                                calls = [
                                    mock.call('GET',
                                              '/api/workflow/LB_' + lb_id,
                                              None, None),
                                    mock.call(
                                        'POST',
                                        '/api/workflowTemplate/' +
                                        'os_lb_v2?name=LB_' + lb_id,
                                        wf_params,
                                        v2_driver.TEMPLATE_HEADER),
                                    mock.call(
                                        'POST',
                                        '/api/workflow/LB_' + lb_id +
                                        '/action/apply',
                                        wf_apply_one_leg_params,
                                        v2_driver.TEMPLATE_HEADER)
                                ]
                                self.driver_rest_call_mock.assert_has_calls(
                                    calls, any_order=True)

    def test_build_objects_graph_one_leg(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as listener:
                    with self.pool(
                        protocol='HTTP',
                        listener_id=listener['listener']['id']) as pool:
                        with contextlib.nested(
                            self.member(pool_id=pool['pool']['id'],
                                        subnet=vip_sub, address='10.0.1.10'),
                            self.member(pool_id=pool['pool']['id'],
                                        subnet=vip_sub, address='10.0.1.20')
                        ) as (member1, member2):

                            wf_srv_params = copy.deepcopy(WF_SRV_PARAMS)
                            wf_params = copy.deepcopy(WF_CREATE_PARAMS)

                            wf_srv_params['name'] = 'srv_' + (
                                vip_sub['subnet']['network_id'])
                            wf_srv_params['tenantId'] = self._tenant_id
                            wf_srv_params['primary']['network'][
                                'portgroups'] = [vip_sub['subnet'][
                                     'network_id']]
                            wf_params['parameters']['service_params'] = (
                                wf_srv_params)

                            member1_data = {
                                "id": member1['member']['id'],
                                "address": "10.0.1.10", "protocol_port": 80,
                                "weight": 1, "admin_state_up": True,
                                "subnet": "255.255.255.255",
                                "mask": "255.255.255.255",
                                "gw": "255.255.255.255",
                                'admin_state_up': True}
                            member2_data = {
                                "id": member2['member']['id'],
                                "address": "10.0.1.20", "protocol_port": 80,
                                "weight": 1, "admin_state_up": True,
                                "subnet": "255.255.255.255",
                                "mask": "255.255.255.255",
                                "gw": "255.255.255.255",
                                "admin_state_up": True}
                            wf_apply_one_leg_params = {'parameters': {
                                'listeners': [{
                                    "id": listener['listener']['id'],
                                    "admin_state_up": True,
                                    "protocol_port": 80,
                                    "protocol": "HTTP",
                                    "connection_limit": -1,
                                    "default_pool": {
                                        "id": pool['pool']['id'],
                                        "protocol": "HTTP",
                                        "lb_algorithm": "ROUND_ROBIN",
                                        "admin_state_up": True,
                                        "members": [
                                            member1_data, member2_data]}}],
                                "admin_state_up": True,
                                "pip_address": "10.0.0.2",
                                "vip_address": "10.0.0.2"}}

                            calls = [
                                mock.call('GET', '/api/workflow/LB_' + lb_id,
                                          None, None),
                                mock.call(
                                    'POST',
                                    '/api/workflowTemplate/' +
                                    'os_lb_v2?name=LB_' + lb_id,
                                    wf_params,
                                    v2_driver.TEMPLATE_HEADER),
                                mock.call(
                                    'POST',
                                    '/api/workflow/LB_' + lb_id +
                                    '/action/apply',
                                    wf_apply_one_leg_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.driver_rest_call_mock.assert_has_calls(
                                calls, any_order=True)

    def test_build_objects_graph_two_legs_full(self):
        with contextlib.nested(
            self.subnet(cidr='10.0.0.0/24'),
            self.subnet(cidr='20.0.0.0/24'),
            self.subnet(cidr='30.0.0.0/24')
        ) as (vip_sub, member_sub1, member_sub2):
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as listener:
                    with self.pool(
                        protocol='HTTP',
                        listener_id=listener['listener']['id'],
                        session_persistence={
                            'type': "APP_COOKIE",
                            'cookie_name': 'sessionId'}) as pool:
                        with self.healthmonitor(
                            type='HTTP', pool_id=pool['pool']['id']) as hm:
                            with self.member(
                                pool_id=pool['pool']['id'],
                                subnet=member_sub1,
                                address='20.0.1.10') as member:

                                    wf_params = copy.deepcopy(WF_CREATE_PARAMS)
                                    wf_srv_params = copy.deepcopy(
                                        WF_SRV_PARAMS)
                                    wf_srv_params['name'] = (
                                        'srv_' + vip_sub['subnet'][
                                            'network_id'])
                                    wf_srv_params['tenantId'] = self._tenant_id
                                    wf_srv_params['primary']['network'][
                                        'portgroups'] = [
                                            vip_sub['subnet']['network_id'],
                                        member_sub1['subnet']['network_id']]
                                    wf_params['parameters'][
                                        'twoleg_enabled'] = True
                                    wf_params['parameters'][
                                        'service_params'] = (wf_srv_params)
                                    hm_data = {
                                        "admin_state_up": True,
                                        "id": hm['healthmonitor']['id'],
                                        "type": "HTTP", "delay": 1,
                                        "timeout": 1,
                                        "max_retries": 1,
                                        "admin_state_up": True,
                                        "url_path": "/", "http_method": "GET",
                                        "expected_codes": '200'}
                                    sp_data = {
                                        "type": "APP_COOKIE",
                                        "cookie_name": "sessionId"}
                                    m_data = {
                                        "id": member['member']['id'],
                                        "address": "20.0.1.10",
                                        "protocol_port": 80,
                                        "weight": 1, "admin_state_up": True,
                                        "subnet": "20.0.1.10",
                                        "mask": "255.255.255.255",
                                        "gw": "20.0.0.1",
                                        "admin_state_up": True}
                                    wf_apply_full_params = {'parameters': {
                                        'listeners': [{
                                            "id": listener['listener']['id'],
                                            "admin_state_up": True,
                                            "protocol_port": 80,
                                            "protocol": "HTTP",
                                            "connection_limit": -1,
                                            "default_pool": {
                                                "id": pool['pool']['id'],
                                                "protocol": "HTTP",
                                                "lb_algorithm":
                                                    "ROUND_ROBIN",
                                                "admin_state_up": True,
                                                "healthmonitor": hm_data,
                                                "sessionpersistence":
                                                    sp_data,
                                                "members": [m_data]}}],
                                        "admin_state_up": True,
                                        "pip_address": "20.0.0.2",
                                        "vip_address": "10.0.0.2"}}
                                    calls = [
                                        mock.call(
                                            'GET',
                                            '/api/workflow/LB_' + lb_id,
                                            None, None),
                                        mock.call(
                                            'POST', '/api/workflowTemplate/' +
                                            'os_lb_v2?name=LB_' + lb_id,
                                            wf_params,
                                            v2_driver.TEMPLATE_HEADER),
                                        mock.call(
                                            'POST', '/api/workflow/LB_' +
                                            lb_id + '/action/apply',
                                            wf_apply_full_params,
                                            v2_driver.TEMPLATE_HEADER),
                                        mock.call('GET', 'some_uri',
                                                  None, None)]
                                    self.driver_rest_call_mock.\
                                        assert_has_calls(
                                            calls, any_order=True)


class TestLBaaSDriverDebugOptions(TestLBaaSDriverBase):
    def setUp(self):
        cfg.CONF.set_override('configure_l3', False,
                              group='radwarev2_debug')
        cfg.CONF.set_override('configure_l4', False,
                              group='radwarev2_debug')
        super(TestLBaaSDriverDebugOptions, self).setUp()

        templates_to_return = [{'name': self.driver.workflow_template_name}]
        for t in self.driver.child_workflow_template_names:
            templates_to_return.append({'name': t})
        rest_call_function_mock.__dict__.update(
            {'RESPOND_WITH_ERROR': False, 'WORKFLOW_MISSING': True,
             'WORKFLOW_TEMPLATE_MISSING': True,
             'RESPOND_WITH_SERVER_DOWN': 200,
             'WF_TEMPLATES_TO_RETURN': templates_to_return})

        self.operation_completer_start_mock = mock.Mock(
            return_value=None)
        self.operation_completer_join_mock = mock.Mock(
            return_value=None)
        self.driver_rest_call_mock = mock.Mock(
            side_effect=rest_call_function_mock)
        self.flip_servers_mock = mock.Mock(
            return_value=None)
        self.recover_mock = mock.Mock(
            side_effect=_recover_function_mock)

        self.driver.completion_handler.start = (
            self.operation_completer_start_mock)
        self.driver.completion_handler.join = (
            self.operation_completer_join_mock)
        self.driver.rest_client.call = self.driver_rest_call_mock
        self.driver.rest_client._call = self.driver_rest_call_mock
        self.driver.completion_handler.rest_client.call = (
            self.driver_rest_call_mock)

        self.driver.queue = QueueMock(
            self.driver.completion_handler.handle_operation_completion)

    def test_debug_options(self):
        with self.subnet(cidr='10.0.0.0/24') as s:
            with self.loadbalancer(subnet=s) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as l:
                    with self.pool(
                        protocol='HTTP',
                        listener_id=l['listener']['id']) as p:
                        with self.member(
                            pool_id=p['pool']['id'],
                            subnet=s, address='10.0.1.10'):
                            wf_srv_params = copy.deepcopy(WF_SRV_PARAMS)
                            wf_params = copy.deepcopy(WF_CREATE_PARAMS)

                            wf_srv_params['name'] = 'srv_' + (
                                s['subnet']['network_id'])
                            wf_srv_params['tenantId'] = self._tenant_id
                            wf_srv_params['primary']['network'][
                                'portgroups'] = [s['subnet'][
                                     'network_id']]
                            wf_params['parameters']['service_params'] = (
                                wf_srv_params)
                            wf_params['parameters']['configure_l3'] = False
                            wf_params['parameters']['configure_l4'] = False
                            calls = [
                                mock.call('GET', '/api/workflow/LB_' + lb_id,
                                          None, None),
                                mock.call(
                                    'POST',
                                    '/api/workflowTemplate/' +
                                    'os_lb_v2?name=LB_' + lb_id,
                                    wf_params,
                                    v2_driver.TEMPLATE_HEADER)
                            ]
                            self.driver_rest_call_mock.assert_has_calls(
                                calls, any_order=True)
