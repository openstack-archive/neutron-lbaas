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
import re

import mock
from neutron_lib import context
from neutron_lib.plugins import constants
from neutron_lib.plugins import directory
from oslo_config import cfg
from oslo_serialization import jsonutils
from six.moves import queue as Queue

from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.drivers.radware import exceptions as r_exc
from neutron_lbaas.drivers.radware import v2_driver
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_con
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
     "gateway": "192.168.200.1", "ha_port": 2}, 'tenants': "_REPLACE_"}

WF_APPLY_PARAMS = {
    'parameters': {'listeners': [], 'pools': [], 'admin_state_up': True,
    'configure_allowed_address_pairs': False,
    'pip_address': u'10.0.0.2', 'vip_address': u'10.0.0.2'}}

LISTENER = {
    'id': None,
    'admin_state_up': True,
    'protocol_port': 80,
    'protocol': lb_con.PROTOCOL_HTTP,
    'default_pool': None,
    'connection_limit': -1,
    'l7_policies': []}

L7_POLICY = {
    'id': None,
    'rules': [],
    'redirect_pool_id': None,
    'redirect_url': None,
    'action': lb_con.L7_POLICY_ACTION_REJECT,
    'position': 1,
    'admin_state_up': True}

L7_RULE = {
    'id': None,
    'type': lb_con.L7_RULE_TYPE_HOST_NAME,
    'compare_type': lb_con.L7_RULE_COMPARE_TYPE_EQUAL_TO,
    'admin_state_up': True,
    'key': None,
    'value': u'val1'}

DEFAULT_POOL = {'id': None}

SESSION_PERSISTENCE = {
    'type': 'APP_COOKIE',
    'cookie_name': 'sessionId'}

CERTIFICATE = {
    'id': None,
    'certificate': 'certificate',
    'intermediates': 'intermediates',
    'private_key': 'private_key',
    'passphrase': 'private_key_passphrase'}

SNI_CERTIFICATE = {
    'id': None,
    'position': 0,
    'certificate': 'certificate',
    'intermediates': 'intermediates',
    'private_key': 'private_key',
    'passphrase': 'private_key_passphrase'}

POOL = {
    'id': None,
    'protocol': lb_con.PROTOCOL_HTTP,
    'lb_algorithm': 'ROUND_ROBIN',
    'admin_state_up': True,
    'members': []}

MEMBER = {
    'id': None,
    'address': '10.0.1.10',
    'protocol_port': 80,
    'weight': 1, 'admin_state_up': True,
    'subnet': '255.255.255.255',
    'mask': '255.255.255.255',
    'gw': '255.255.255.255',
    'admin_state_up': True}

HM = {
    'id': None,
    'expected_codes': '200',
    'type': 'HTTP',
    'delay': 1,
    'timeout': 1,
    'max_retries': 1,
    'admin_state_up': True,
    'url_path': '/',
    'http_method': 'GET'}


class TestLBaaSDriverBase(
    test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def setUp(self):
        super(TestLBaaSDriverBase, self).setUp(
            lbaas_provider=RADWARE_PROVIDER)

        self.plugin_instance = directory.get_plugin(constants.LOADBALANCERV2)
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

    @contextlib.contextmanager
    def loadbalancer(self, fmt=None, subnet=None, no_delete=False, **kwargs):
        with super(TestLBaaSDriver, self).loadbalancer(
            fmt, subnet, no_delete,
            vip_address=WF_APPLY_PARAMS['parameters']['vip_address'],
            **kwargs) as lb:
            self.wf_srv_params['name'] = 'srv_' + (
                subnet['subnet']['network_id'])
            self.wf_srv_params['tenantId'] = self._tenant_id
            self.wf_srv_params['primary']['network']['portgroups'] =\
                [subnet['subnet']['network_id']]
            self.wf_create_params['parameters']['service_params'] =\
                self.wf_srv_params
            yield lb

    @contextlib.contextmanager
    def listener(self, fmt=None, protocol='HTTP', loadbalancer_id=None,
                 protocol_port=80, default_pool_id=None, no_delete=False,
                 **kwargs):
        with super(TestLBaaSDriver, self).listener(
            fmt, protocol, loadbalancer_id, protocol_port, default_pool_id,
            no_delete, **kwargs) as listener:

            l = copy.deepcopy(LISTENER)
            self._update_dict(l, listener['listener'])
            if 'default_tls_container_ref' in kwargs:
                c = copy.deepcopy(CERTIFICATE)
                self._update_dict(c,
                                  {'id': kwargs['default_tls_container_ref']})
                l['default_tls_certificate'] = c
            if 'sni_container_refs' in kwargs:
                l['sni_tls_certificates'] = []
                pos = 0
                for ref in kwargs['sni_container_refs']:
                    s = copy.deepcopy(SNI_CERTIFICATE)
                    self._update_dict(s, {'id': ref, 'position': pos})
                    l['sni_tls_certificates'].append(s)
                    pos = pos + 1
            self.wf_apply_params['parameters']['listeners'].append(l)
            yield listener

    @contextlib.contextmanager
    def l7policy(self, listener_id, fmt=None,
                 action=lb_con.L7_POLICY_ACTION_REJECT,
                 no_delete=False, **kwargs):
        with super(TestLBaaSDriver, self).l7policy(
            listener_id, fmt, action, no_delete, **kwargs) as policy:

            p = copy.deepcopy(L7_POLICY)
            self._update_dict(p, policy['l7policy'])
            for l in self.wf_apply_params['parameters']['listeners']:
                if l['id'] == listener_id:
                    l['l7_policies'].append(p)
                    break
            yield policy

    @contextlib.contextmanager
    def l7policy_rule(self, l7policy_id, fmt=None, value='value1',
                      type=lb_con.L7_RULE_TYPE_HOST_NAME,
                      compare_type=lb_con.L7_RULE_COMPARE_TYPE_EQUAL_TO,
                      no_delete=False, **kwargs):
        with super(TestLBaaSDriver, self).l7policy_rule(
            l7policy_id, fmt, value, type, compare_type,
            no_delete, **kwargs) as rule:

            r = copy.deepcopy(L7_RULE)
            self._update_dict(r, rule['rule'])
            for l in self.wf_apply_params['parameters']['listeners']:
                #if l['id'] == listener_id:
                for p in l['l7_policies']:
                    if p['id'] == l7policy_id:
                        p['rules'].append(r)
                        break
            yield rule

    @contextlib.contextmanager
    def pool(self, fmt=None, protocol='HTTP', lb_algorithm='ROUND_ROBIN',
             no_delete=False, listener_id=None,
             loadbalancer_id=None, **kwargs):
        with super(TestLBaaSDriver, self).pool(
            fmt, protocol, lb_algorithm, no_delete, listener_id,
            loadbalancer_id, **kwargs) as pool:

            p = copy.deepcopy(POOL)
            self._update_dict(p, pool['pool'])
            self.wf_apply_params['parameters']['pools'].append(p)
            if listener_id:
                p = copy.deepcopy(DEFAULT_POOL)
                self._update_dict(p, pool['pool'])
                for l in self.wf_apply_params['parameters']['listeners']:
                    if l['id'] == listener_id:
                        l['default_pool'] = p
                        break
            if 'session_persistence' in kwargs:
                s = copy.deepcopy(SESSION_PERSISTENCE)
                self._update_dict(s, kwargs['session_persistence'])
                l['default_pool']['sessionpersistence'] = s
            yield pool

    @contextlib.contextmanager
    def member(self, fmt=None, pool_id='pool1id', address='127.0.0.1',
               protocol_port=80, subnet=None, no_delete=False,
               **kwargs):
        with super(TestLBaaSDriver, self).member(
            fmt, pool_id, address, protocol_port, subnet,
            no_delete, **kwargs) as member:

            m = copy.deepcopy(MEMBER)
            self._update_dict(m, member['member'])
            for p in self.wf_apply_params['parameters']['pools']:
                if p['id'] == pool_id:
                    p['members'].append(m)
                    break
            yield member

    @contextlib.contextmanager
    def healthmonitor(self, fmt=None, pool_id='pool1id', type='TCP', delay=1,
                      timeout=1, max_retries=1, no_delete=False, **kwargs):
        with super(TestLBaaSDriver, self).healthmonitor(
            fmt, pool_id, type, delay, timeout, max_retries,
            no_delete, **kwargs) as hm:

            m = copy.deepcopy(HM)
            self._update_dict(m, hm['healthmonitor'])
            for p in self.wf_apply_params['parameters']['pools']:
                if p['id'] == pool_id:
                    p['healthmonitor'] = m
                    break
            yield hm

    def _update_dict(self, o, d):
        for p in list(o.keys()):
            if p in d:
                o[p] = d[p]

    def update_member(self, pool_id, **kwargs):
        m = copy.deepcopy(MEMBER)
        self._update_dict(m, kwargs)
        for p in self.wf_apply_params['parameters']['pools']:
            if p['id'] == pool_id:
                for mem in p['members']:
                    if mem['id'] == kwargs['id']:
                        mem.update(m)
                        break

    def delete_member(self, id, pool_id):
        for p in self.wf_apply_params['parameters']['pools']:
            if p['id'] == pool_id:
                for mem in p['members']:
                    if mem['id'] == id:
                        index = p['members'].index(mem)
                        del p['members'][index]
                        break

    def delete_pool(self, id):
        for p in self.wf_apply_params['parameters']['pools']:
            if p['id'] == id:
                index = self.wf_apply_params['parameters']['pools'].index(p)
                del self.wf_apply_params['parameters']['pools'][index]
                break
        for l in self.wf_apply_params['parameters']['listeners']:
            if l['default_pool']['id'] == id:
                index = self.wf_apply_params['parameters']['listeners']\
                    .index(l)
                del self.wf_apply_params['parameters']['listeners'][index]
                break

    def add_network_to_service(self, subnet):
        self.wf_srv_params['primary']['network']['portgroups'].append(
            subnet['subnet']['network_id'])
        self.wf_create_params['parameters']['service_params'] =\
            self.wf_srv_params

    def set_two_leg_mode(self, two_leg_mode):
        self.wf_create_params['parameters']['twoleg_enabled'] = two_leg_mode

    def compare_create_call(self):
        create_call = self.driver_rest_call_mock.mock_calls[2][1][2]
        self.assertEqual(create_call, self.wf_create_params)

    def compare_apply_call(self):
        def _sort_lists_by_id(o):
            if isinstance(o, list):
                o = sorted(o, key=lambda x: x['id'])
                for i in o:
                    i = _sort_lists_by_id(i)
            elif isinstance(o, dict):
                for k in o.keys():
                    o[k] = _sort_lists_by_id(o[k])
            return o

        apply_call_i = len(self.driver_rest_call_mock.mock_calls) - 2
        apply_call = self.driver_rest_call_mock.mock_calls[apply_call_i][1][2]
        apply_call = _sort_lists_by_id(apply_call)
        self.wf_apply_params = _sort_lists_by_id(self.wf_apply_params)
        self.assertEqual(apply_call, self.wf_apply_params)

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

        self.wf_srv_params = copy.deepcopy(WF_SRV_PARAMS)
        self.wf_create_params = copy.deepcopy(WF_CREATE_PARAMS)
        self.wf_create_params['tenants'] = [self._tenant_id]
        self.wf_apply_params = copy.deepcopy(WF_APPLY_PARAMS)

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
                with self.listener(loadbalancer_id=lb_id) as l:
                    listener_id = l['listener']['id']
                    with self.pool(
                        protocol=lb_con.PROTOCOL_HTTP,
                        listener_id=listener_id) as p:
                        pool_id = p['pool']['id']
                        self.driver_rest_call_mock.reset_mock()
                        with self.member(
                            pool_id=pool_id,
                            subnet=vip_sub, address='10.0.1.10'):

                            self.compare_create_call()
                            self.compare_apply_call()

    def test_wf_deleted_on_lb_deletion(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                get_calls = [
                    mock.call('GET', u'/api/workflow/LB_' +
                        lb['loadbalancer']['id'], None, None)]
                with self.listener(
                    loadbalancer_id=lb['loadbalancer']['id']) as listener:
                    with self.pool(
                        protocol=lb_con.PROTOCOL_HTTP,
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
                        protocol=lb_con.PROTOCOL_HTTP,
                        listener_id=l['listener']['id']) as p:

                        self.plugin_instance.update_loadbalancer(
                            context.get_admin_context(),
                            lb_id, {'loadbalancer': lb})
                        lb_db = self.plugin_instance.db.get_loadbalancer(
                            context.get_admin_context(),
                            lb_id)
                        self.driver.load_balancer.refresh(
                            context.get_admin_context(), lb_db)

                        with self.member(
                            no_delete=True, pool_id=p['pool']['id'],
                            subnet=s, address='10.0.1.10'):

                            self.compare_apply_call()

                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            self.plugin_instance.update_loadbalancer(
                                context.get_admin_context(),
                                lb_id, {'loadbalancer': lb})
                            self.compare_apply_call()

                            self.driver_rest_call_mock.reset_mock()
                            lb_db = self.plugin_instance.db.get_loadbalancer(
                                context.get_admin_context(), lb_id)
                            self.driver.load_balancer.refresh(
                                context.get_admin_context(), lb_db)
                            self.compare_apply_call()

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
                        protocol=lb_con.PROTOCOL_HTTP,
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
                    listener_id = l['listener']['id']
                    with self.pool(
                        protocol=lb_con.PROTOCOL_HTTP,
                        listener_id=listener_id) as p:
                        pool_id = p['pool']['id']
                        with self.member(
                            no_delete=True, address='10.0.1.10',
                            pool_id=pool_id, subnet=s) as m1:
                            member1_id = m1['member']['id']

                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            with self.member(
                                no_delete=True, pool_id=pool_id,
                                subnet=s, address='10.0.1.20') as m2:
                                member2_id = m2['member']['id']
                                self.compare_apply_call()

                                self.driver_rest_call_mock.reset_mock()
                                m = self.plugin_instance.db.get_pool_member(
                                    context.get_admin_context(),
                                    m1['member']['id']).to_dict(pool=False)

                                m['weight'] = 2
                                self.plugin_instance.update_pool_member(
                                    context.get_admin_context(),
                                    m1['member']['id'], p['pool']['id'],
                                    {'member': m})
                                self.update_member(pool_id, id=member1_id,
                                                   weight=2)
                                self.compare_apply_call()

                                self.driver_rest_call_mock.reset_mock()

                                self.plugin_instance.delete_pool_member(
                                    context.get_admin_context(),
                                    member2_id, pool_id)
                                self.delete_member(member2_id, pool_id)
                                self.compare_apply_call()

                                lb = self.plugin_instance.db.get_loadbalancer(
                                    context.get_admin_context(),
                                    lb_id).to_dict(listener=False)
                                self.assertEqual('ACTIVE',
                                             lb['provisioning_status'])

    def test_build_objects_with_tls(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                                'cert_parser',
                                autospec=True) as cert_parser_mock, \
                        mock.patch('neutron_lbaas.services.loadbalancer.'
                                   'plugin.CERT_MANAGER_PLUGIN.CertManager',
                                   autospec=True) as cert_manager_mock:
                    cert_mock = mock.Mock(spec=cert_manager.Cert)
                    cert_mock.get_certificate.return_value = 'certificate'
                    cert_mock.get_intermediates.return_value = 'intermediates'
                    cert_mock.get_private_key.return_value = 'private_key'
                    cert_mock.get_private_key_passphrase.return_value = \
                        'private_key_passphrase'
                    cert_manager_mock().get_cert.return_value = cert_mock
                    cert_parser_mock.validate_cert.return_value = True

                    with self.listener(
                        protocol=lb_con.PROTOCOL_TERMINATED_HTTPS,
                        loadbalancer_id=lb_id,
                        default_tls_container_ref='def1',
                        sni_container_refs=['sni1', 'sni2']) as listener:
                        with self.pool(
                            protocol=lb_con.PROTOCOL_HTTP,
                            listener_id=listener['listener']['id']) as pool:
                            with self.member(pool_id=pool['pool']['id'],
                                             subnet=vip_sub,
                                             address='10.0.1.10'):
                                self.compare_apply_call()

    def test_build_objects_with_l7(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(
                    protocol=lb_con.PROTOCOL_HTTP,
                    loadbalancer_id=lb_id) as listener:
                    listener_id = listener['listener']['id']
                    with self.pool(protocol=lb_con.PROTOCOL_HTTP,
                                   listener_id=listener_id) as def_pool, \
                            self.pool(protocol=lb_con.PROTOCOL_HTTP,
                                      loadbalancer_id=lb_id) as pol_pool:
                        def_pool_id = def_pool['pool']['id']
                        pol_pool_id = pol_pool['pool']['id']
                        with self.l7policy(
                            listener_id,
                            action=lb_con.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                            redirect_pool_id=pol_pool_id) as policy:
                            policy_id = policy['l7policy']['id']

                            self.driver_rest_call_mock.reset_mock()
                            with self.l7policy_rule(l7policy_id=policy_id,
                                                    key=u'key1',
                                                    value=u'val1'), \
                                    self.l7policy_rule(l7policy_id=policy_id,
                                                       key=u'key2',
                                                       value=u'val2'), \
                                    self.member(pool_id=def_pool_id,
                                                subnet=vip_sub,
                                                address=u'10.0.1.10'):
                                self.driver_rest_call_mock.reset_mock()
                                rest_call_function_mock.__dict__.update(
                                    {'WORKFLOW_MISSING': False})

                                with self.member(
                                    pool_id=pol_pool_id,
                                    subnet=vip_sub,
                                    address=u'10.0.1.20'):

                                    self.compare_apply_call()

    def test_build_objects_graph_lb_pool(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as listener:
                    listener_id = listener['listener']['id']
                    with self.pool(
                        protocol=lb_con.PROTOCOL_HTTP,
                        listener_id=listener_id) as pool:
                        with self.member(pool_id=pool['pool']['id'],
                                         subnet=vip_sub,
                                         address='10.0.1.10'), \
                                self.member(pool_id=pool['pool']['id'],
                                            subnet=vip_sub,
                                            address='10.0.1.20'):
                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            with self.pool(
                                protocol=lb_con.PROTOCOL_HTTP,
                                loadbalancer_id=lb_id):
                                self.compare_apply_call()

    def test_build_objects_graph_one_leg(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as listener:
                    listener_id = listener['listener']['id']
                    with self.pool(
                        protocol='HTTP',
                        listener_id=listener_id) as pool:
                        with self.member(pool_id=pool['pool']['id'],
                                         subnet=vip_sub,
                                         address='10.0.1.10'), \
                                self.member(pool_id=pool['pool']['id'],
                                            subnet=vip_sub,
                                            address='10.0.1.20'):
                            self.compare_apply_call()

    def test_build_objects_graph_two_legs_full(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub, \
                self.subnet(cidr='20.0.0.0/24') as member_sub1, \
                self.subnet(cidr='30.0.0.0/24'):
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
                            type='HTTP', pool_id=pool['pool']['id']):

                            self.driver_rest_call_mock.reset_mock()

                            with self.member(
                                pool_id=pool['pool']['id'],
                                subnet=member_sub1,
                                address='20.0.1.10') as member:

                                    self.update_member(
                                        pool['pool']['id'],
                                        id=member['member']['id'],
                                        address='20.0.1.10',
                                        subnet='20.0.1.10', gw='20.0.0.1')
                                    self.set_two_leg_mode(True)
                                    self.add_network_to_service(member_sub1)
                                    self.wf_apply_params['parameters'][
                                        'pip_address'] =\
                                        self.driver_rest_call_mock.mock_calls[
                                            len(self.driver_rest_call_mock.
                                            mock_calls) - 2][1][2][
                                                'parameters']['pip_address']

                                    self.compare_create_call()
                                    self.compare_apply_call()

    def test_pool_deletion_for_listener(self):
        with self.subnet(cidr='10.0.0.0/24') as vip_sub:
            with self.loadbalancer(subnet=vip_sub) as lb:
                lb_id = lb['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as listener:
                    with self.pool(
                        protocol='HTTP',
                        listener_id=listener['listener']['id'],
                        no_delete=True) as p:

                        with self.member(
                            no_delete=True,
                            pool_id=p['pool']['id'],
                            subnet=vip_sub, address='10.0.1.10'):

                            self.driver_rest_call_mock.reset_mock()
                            rest_call_function_mock.__dict__.update(
                                {'WORKFLOW_MISSING': False})

                            self.plugin_instance.delete_pool(
                                context.get_admin_context(), p['pool']['id'])
                            self.delete_pool(p['pool']['id'])

                            self.compare_apply_call()


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
                            wf_params['tenants'] = [self._tenant_id]
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
