# Copyright 2017, Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import uuid

import requests_mock
import webob.exc

from neutron.api import extensions
from neutron.common import config
from neutron.tests.unit.api.v2 import test_base
from neutron_lib import constants as n_constants
from neutron_lib import context
from neutron_lib import exceptions as lib_exc
from oslo_config import cfg
from oslo_utils import uuidutils

from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import \
    proxy_plugin as loadbalancer_plugin
from neutron_lbaas.tests import base
from neutron_lbaas.tests.unit.db.loadbalancer import util

LB_PLUGIN_CLASS = (
    "neutron_lbaas.services.loadbalancer."
    "proxy_plugin.LoadBalancerProxyPluginv2"
)

_uuid = uuidutils.generate_uuid
_get_path = test_base._get_path


_subnet_id = "0c798ed8-33ba-11e2-8b28-000c291c4d14"
base_url = '{}/{}'.format('http://127.0.0.1:9876', 'v2.0/lbaas')


class TestLbaasProxyPluginDbTestCase(util.LbaasTestMixin,
                                     base.NeutronDbPluginV2TestCase):
    fmt = 'json'

    def setUp(self, core_plugin=None, lb_plugin=None, lbaas_provider=None,
              ext_mgr=None):
        service_plugins = {'lb_plugin_name': LB_PLUGIN_CLASS}

        # removing service-type because it resides in neutron and tests
        # dont care
        LBPlugin = loadbalancer_plugin.LoadBalancerProxyPluginv2
        sea_index = None
        for index, sea in enumerate(LBPlugin.supported_extension_aliases):
            if sea == 'service-type':
                sea_index = index
        if sea_index:
            del LBPlugin.supported_extension_aliases[sea_index]

        super(TestLbaasProxyPluginDbTestCase, self).setUp(
            ext_mgr=ext_mgr,
            service_plugins=service_plugins
        )

        if not ext_mgr:
            self.plugin = loadbalancer_plugin.LoadBalancerProxyPluginv2()
            # This is necessary because the automatic extension manager
            # finding algorithm below will find the loadbalancerv2
            # extension and fail to initizlize the main API router with
            # extensions' resources
            ext_mgr = util.ExtendedPluginAwareExtensionManager(
                LBPlugin.supported_extension_aliases)

            app = config.load_paste_app('extensions_test_app')
            self.ext_api = extensions.ExtensionMiddleware(app, ext_mgr=ext_mgr)

        self._subnet_id = _subnet_id
        # set quotas to -1 (unlimited)
        cfg.CONF.set_override('quota_loadbalancer', -1, group='QUOTAS')

    def _update_loadbalancer_api(self, lb_id, data):
        req = self.new_update_request('loadbalancers', data, lb_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, req.get_response(self.ext_api))
        return resp, body

    def _delete_loadbalancer_api(self, lb_id):
        req = self.new_delete_request('loadbalancers', lb_id)
        resp = req.get_response(self.ext_api)
        return resp

    def _get_loadbalancer_api(self, lb_id):
        req = self.new_show_request('loadbalancers', lb_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _list_loadbalancers_api(self):
        req = self.new_list_request('loadbalancers')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _get_loadbalancer_stats_api(self, lb_id):
        req = self.new_show_request('loadbalancers', lb_id,
                                    subresource='stats')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _get_loadbalancer_statuses_api(self, lb_id):
        req = self.new_show_request('loadbalancers', lb_id,
                                    subresource='statuses')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body


class LbaasLoadBalancerTests(TestLbaasProxyPluginDbTestCase):
    url = '{}/{}'.format(base_url, 'loadbalancers')

    @requests_mock.mock()
    def test_create_loadbalancer(self, m, **extras):
        expected = {
            'name': 'vip1',
            'description': '',
            'admin_state_up': True,
            'provisioning_status': n_constants.ACTIVE,
            'operating_status': lb_const.ONLINE,
            'tenant_id': self._tenant_id,
            'listeners': [],
            'pools': [],
            'provider': 'lbaas'
        }

        res = expected.copy()
        res['id'] = 'fake_uuid'
        expected.update(extras)

        m.post(self.url, json={'loadbalancer': res})
        with self.subnet() as subnet:
            name = expected['name']
            with self.loadbalancer(name=name, subnet=subnet,
                                   no_delete=True, **extras) as lb:
                lb_id = lb['loadbalancer']['id']
                self.assertEqual('fake_uuid', lb_id)
                actual = dict((k, v)
                              for k, v in lb['loadbalancer'].items()
                              if k in expected)
                self.assertEqual(expected, actual)
            return lb

    @requests_mock.mock()
    def test_list_loadbalancers(self, m):
        name = 'lb_show'
        description = 'lb_show description'
        expected_values = {'name': name,
                           'description': description,
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas'}

        m.get(self.url, json={'loadbalancers': [expected_values]})
        resp, body = self._list_loadbalancers_api()
        self.assertEqual(1, len(body['loadbalancers']))
        for k in expected_values:
            self.assertEqual(expected_values[k],
                             body['loadbalancers'][0][k])

    def _build_lb_list(self):
        expected_values = []
        for name in ['lb1', 'lb2', 'lb3']:
            expected_values.append({'name': name,
                                    'description': 'lb_show description',
                                    'vip_address': '10.0.0.10',
                                    'admin_state_up': True,
                                    'provisioning_status': n_constants.ACTIVE,
                                    'operating_status': lb_const.ONLINE,
                                    'listeners': [],
                                    'provider': 'lbaas',
                                    'id': name})
        return expected_values

    @requests_mock.mock()
    def test_list_loadbalancers_with_sort_emulated(self, m):
        expected_values = self._build_lb_list()
        m.get(self.url, json={'loadbalancers': expected_values})

        self._test_list_with_sort(
            'loadbalancer',
            ({'loadbalancer': expected_values[0]},
             {'loadbalancer': expected_values[1]},
             {'loadbalancer': expected_values[2]}),
            [('name', 'asc')]
        )

    @requests_mock.mock()
    def test_list_loadbalancers_with_pagination_emulated(self, m):
        expected_values = self._build_lb_list()
        m.get(self.url, json={'loadbalancers': expected_values})
        self._test_list_with_pagination(
            'loadbalancer',
            ({'loadbalancer': expected_values[0]},
             {'loadbalancer': expected_values[1]},
             {'loadbalancer': expected_values[2]}),
            ('name', 'asc'), 2, 2
        )

    @requests_mock.mock()
    def test_list_loadbalancers_with_pagination_reverse_emulated(self, m):
        expected_values = self._build_lb_list()
        m.get(self.url, json={'loadbalancers': expected_values})
        self._test_list_with_pagination_reverse(
            'loadbalancer',
            ({'loadbalancer': expected_values[0]},
             {'loadbalancer': expected_values[1]},
             {'loadbalancer': expected_values[2]}),
            ('name', 'asc'), 2, 2
        )

    @requests_mock.mock()
    def test_show_loadbalancer(self, m):
        name = 'lb_show'
        description = 'lb_show description'
        lb_id = "testid"
        expected_values = {'name': name,
                           'description': description,
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas',
                           'id': lb_id}
        m.get("{}/{}".format(self.url, lb_id),
              json={'loadbalancer': expected_values})
        resp, body = self._get_loadbalancer_api(lb_id)
        for k in expected_values:
            self.assertEqual(expected_values[k],
                             body['loadbalancer'][k])

    @requests_mock.mock()
    def test_update_loadbalancer(self, m):
        loadbalancer_id = "test_uuid"
        name = 'new_loadbalancer'
        description = 'a crazy loadbalancer'
        expected_values = {'name': name,
                           'description': description,
                           'admin_state_up': False,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas',
                           'id': loadbalancer_id}

        m.put("{}/{}".format(self.url, loadbalancer_id),
              json={'loadbalancer': expected_values})
        # wonder why an update triggers a get...
        m.get("{}/{}".format(self.url, loadbalancer_id),
              json={'loadbalancer': expected_values})
        data = {'loadbalancer': {'name': name,
                                 'description': description,
                                 'admin_state_up': False}}
        resp, res = self._update_loadbalancer_api(loadbalancer_id,
                                                  data)
        for k in expected_values:
            self.assertEqual(expected_values[k],
                             res['loadbalancer'][k])

    @requests_mock.mock()
    def test_delete_loadbalancer(self, m):
        loadbalancer_id = "test_uuid"
        expected_values = {'name': "test",
                           'description': "test",
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas',
                           'id': loadbalancer_id}
        # wonder why an delete triggers a get...
        m.get("{}/{}".format(self.url, loadbalancer_id),
              json={'loadbalancer': expected_values})
        m.delete("{}/{}".format(self.url, loadbalancer_id))
        resp = self._delete_loadbalancer_api(loadbalancer_id)
        self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    @requests_mock.mock()
    def test_delete_loadbalancer_when_loadbalancer_in_use(self, m):
        lb_id = "123"
        m.delete("{}/{}".format(self.url, lb_id), status_code=409)
        ctx = context.get_admin_context()
        # notice we raise a more generic exception then the stabdard plugin
        self.assertRaises(lib_exc.Conflict,
                          self.plugin.delete_loadbalancer,
                          ctx, lb_id)


class ListenerTestBase(TestLbaasProxyPluginDbTestCase):
    lb_id = uuid.uuid4().hex

    def _create_listener_api(self, data):
        req = self.new_create_request("listeners", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_listener_api(self, listener_id, data):
        req = self.new_update_request('listeners', data, listener_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, req.get_response(self.ext_api))
        return resp, body

    def _delete_listener_api(self, listener_id):
        req = self.new_delete_request('listeners', listener_id)
        resp = req.get_response(self.ext_api)
        return resp

    def _get_listener_api(self, listener_id):
        req = self.new_show_request('listeners', listener_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _list_listeners_api(self):
        req = self.new_list_request('listeners')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body


class LbaasListenerTests(ListenerTestBase):
    url = '{}/{}'.format(base_url, 'listeners')

    @requests_mock.mock()
    def test_create_listener(self, m):
        expected = {
            'protocol': 'HTTP',
            'protocol_port': 80,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'default_pool_id': None,
            'loadbalancers': [{'id': self.lb_id}],
            'id': '123'
        }

        m.post(self.url, json={'listener': expected})
        with self.listener(loadbalancer_id=self.lb_id,
                           no_delete=True) as listener:
            listener_id = listener['listener'].get('id')
            self.assertTrue(listener_id)
            actual = {}
            for k, v in listener['listener'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
        return listener

    @requests_mock.mock()
    def test_create_listener_same_port_same_load_balancer(self, m):
        m.post(self.url, status_code=409)
        self._create_listener(self.fmt, 'HTTP', 80,
                              loadbalancer_id=self.lb_id,
                              expected_res_status=409,
                              no_delete=True)

    @requests_mock.mock()
    def test_create_listener_with_tls_no_default_container(self, m, **extras):
        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': None,
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id,
        }
        m.post(self.url, status_code=400)
        listener_data.update(extras)
        self.assertRaises(
                        lib_exc.BadRequest,
                        self.plugin.create_listener,
                        context.get_admin_context(),
                        {'listener': listener_data})

    @requests_mock.mock()
    def test_create_listener_loadbalancer_id_does_not_exist(self, m):
        m.post(self.url, status_code=404)
        self._create_listener(self.fmt, 'HTTP', 80,
                              loadbalancer_id=uuidutils.generate_uuid(),
                              expected_res_status=404)

    @requests_mock.mock()
    def test_update_listener(self, m):
        name = 'new_listener'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': 100,
                           'admin_state_up': False,
                           'tenant_id': self._tenant_id,
                           'loadbalancers': [{'id': self.lb_id}]}

        listener_id = uuidutils.generate_uuid()
        # needs a get before a put...
        m.get("{}/{}".format(self.url, listener_id),
              json={'listener': expected_values})
        m.put("{}/{}".format(self.url, listener_id),
              json={'listener': expected_values})
        data = {'listener': {'name': name,
                             'connection_limit': 100,
                             'admin_state_up': False}}
        resp, body = self._update_listener_api(listener_id, data)
        for k in expected_values:
            self.assertEqual(expected_values[k], body['listener'][k])

    @requests_mock.mock()
    def test_delete_listener(self, m):
        expected_values = {'name': 'test',
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': 100,
                           'admin_state_up': False,
                           'tenant_id': self._tenant_id,
                           'loadbalancers': [{'id': self.lb_id}]}
        listener_id = uuidutils.generate_uuid()
        m.get("{}/{}".format(self.url, listener_id),
              json={'listener': expected_values})
        m.delete("{}/{}".format(self.url, listener_id))

        resp = self._delete_listener_api(listener_id)
        self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    @requests_mock.mock()
    def test_show_listener(self, m):
        name = 'show_listener'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': -1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'default_pool_id': None,
                           'loadbalancers': [{'id': self.lb_id}]}
        listener_id = uuidutils.generate_uuid()
        m.get("{}/{}".format(self.url, listener_id),
              json={'listener': expected_values})
        resp, body = self._get_listener_api(listener_id)
        for k in expected_values:
            self.assertEqual(expected_values[k], body['listener'][k])

    @requests_mock.mock()
    def test_list_listeners(self, m):
        name = 'list_listeners'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': -1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'loadbalancers': [{'id': self.lb_id}]}

        listener_id = uuidutils.generate_uuid()
        m.get(self.url, json={'listeners': [expected_values]})
        expected_values['id'] = listener_id
        resp, body = self._list_listeners_api()
        listener_list = body['listeners']
        self.assertEqual(1, len(listener_list))
        for k in expected_values:
            self.assertEqual(expected_values[k], listener_list[0][k])


class LbaasL7Tests(ListenerTestBase):
    url = '{}/{}'.format(base_url, 'l7policies')

    def _rules(self, policy_id=uuidutils.generate_uuid()):
        return "{}/{}/rules".format(self.url, policy_id)

    @requests_mock.mock()
    def test_create_l7policy_invalid_listener_id(self, m, **extras):
        m.post(self.url, status_code=404)
        self._create_l7policy(self.fmt, uuidutils.generate_uuid(),
                              lb_const.L7_POLICY_ACTION_REJECT,
                              expected_res_status=webob.exc.HTTPNotFound.code)

    @requests_mock.mock()
    def test_create_l7policy(self, m, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)
        listener_id = uuidutils.generate_uuid()
        expected['listener_id'] = listener_id

        m.post(self.url, json={'l7policy': expected})
        with self.l7policy(listener_id, no_delete=True) as p:
            actual = {}
            for k, v in p['l7policy'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(actual, expected)

    @requests_mock.mock()
    def test_create_l7policy_pool_redirect(self, m, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)
        listener_id = uuidutils.generate_uuid()
        pool_id = uuidutils.generate_uuid()
        expected['listener_id'] = listener_id
        expected['redirect_pool_id'] = pool_id

        m.post(self.url, json={'l7policy': expected})
        with self.l7policy(
            listener_id,
            action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            redirect_pool_id=pool_id, no_delete=True) as p:
                actual = {}
                for k, v in p['l7policy'].items():
                    if k in expected:
                        actual[k] = v
                self.assertEqual(actual, expected)

    @requests_mock.mock()
    def test_update_l7policy(self, m, **extras):
        l7policy_id = uuidutils.generate_uuid()
        expected = {
            'admin_state_up': False,
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'redirect_pool_id': None,
            'redirect_url': 'redirect_url',
            'tenant_id': self._tenant_id,
            'position': 1,
        }
        expected.update(extras)

        m.get('{}/{}'.format(self.url, l7policy_id),
              json={'l7policy': expected})
        m.put('{}/{}'.format(self.url, l7policy_id),
              json={'l7policy': expected})

        data = {
            'l7policy': {
                'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
                'redirect_url': 'redirect_url',
                'admin_state_up': False}}

        ctx = context.get_admin_context()
        self.plugin.update_l7policy(ctx, l7policy_id, data)
        l7policy = self.plugin.get_l7policy(ctx, l7policy_id)
        actual = {}
        for k, v in l7policy.items():
            if k in expected:
                actual[k] = v
        self.assertEqual(actual, expected)

    @requests_mock.mock()
    def test_delete_l7policy(self, m, **extras):
        l7policy_id = uuidutils.generate_uuid()

        m.delete('{}/{}'.format(self.url, l7policy_id))

        c = context.get_admin_context()
        self.plugin.delete_l7policy(c, l7policy_id)

    @requests_mock.mock()
    def test_show_l7policy(self, m, **extras):
        listener_id = uuidutils.generate_uuid()
        l7policy_id = uuidutils.generate_uuid()
        expected = {
            'position': 1,
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
            'listener_id': listener_id,
            'id': l7policy_id,
        }
        expected.update(extras)

        m.get('{}/{}'.format(self.url, l7policy_id),
            json={'l7policy': expected})

        req = self.new_show_request('l7policies',
                                    l7policy_id,
                                    fmt=self.fmt)
        res = self.deserialize(self.fmt,
                               req.get_response(self.ext_api))
        actual = {}
        for k, v in res['l7policy'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

    @requests_mock.mock()
    def test_list_l7policies_with_sort_emulated(self, m):
        listener_id = uuidutils.generate_uuid()
        l7policy_id = uuidutils.generate_uuid()
        expected = {
            'position': 1,
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
            'listener_id': listener_id,
            'id': l7policy_id,
        }
        m.get(self.url, json={'l7policies': [expected]})
        self._test_list_with_sort('l7policy', [{'l7policy': expected}],
                                  [('name', 'asc')],
                                  resources='l7policies')

    @requests_mock.mock()
    def test_create_l7rule_invalid_policy_id(self, m, **extras):
        l7_policy_id = uuidutils.generate_uuid()
        m.post(self._rules(l7_policy_id), status_code=404)
        self._create_l7policy_rule(
            self.fmt, l7_policy_id,
            lb_const.L7_RULE_TYPE_HOST_NAME,
            lb_const.L7_RULE_COMPARE_TYPE_REGEX,
            'value',
            expected_res_status=webob.exc.HTTPNotFound.code)

    @requests_mock.mock()
    def test_create_l7rule(self, m, **extras):
        l7_policy_id = uuidutils.generate_uuid()
        expected = {
            'type': lb_const.L7_RULE_TYPE_HOST_NAME,
            'compare_type': lb_const.L7_RULE_COMPARE_TYPE_EQUAL_TO,
            'key': None,
            'value': 'value1'
        }

        m.post(self._rules(l7_policy_id), json={'rule': expected})
        with self.l7policy_rule(l7_policy_id, no_delete=True) as r_def:
            self.assertEqual(expected, r_def['rule'])

    @requests_mock.mock()
    def test_update_l7rule(self, m, **extras):
        l7_policy_id = uuidutils.generate_uuid()
        l7_policy_rule_id = uuidutils.generate_uuid()

        expected = {}
        expected['type'] = lb_const.L7_RULE_TYPE_HEADER
        expected['compare_type'] = (
            lb_const.L7_RULE_COMPARE_TYPE_REGEX)
        expected['value'] = '/.*/'
        expected['key'] = 'HEADER1'
        expected['invert'] = True
        expected['admin_state_up'] = False

        m.get("{}/{}".format(self._rules(l7_policy_id),
                             l7_policy_rule_id),
              json={'rule': expected})
        m.put("{}/{}".format(self._rules(l7_policy_id),
                             l7_policy_rule_id),
              json={'rule': expected})
        req = self.new_update_request(
            'l7policies', {'rule': expected},
            l7_policy_id, subresource='rules',
            sub_id=l7_policy_rule_id)
        res = self.deserialize(
            self.fmt,
            req.get_response(self.ext_api)
        )
        actual = {}
        for k, v in res['rule'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(actual, expected)

    @requests_mock.mock()
    def test_delete_l7rule(self, m):
        l7_policy_id = uuidutils.generate_uuid()
        l7_policy_rule_id = uuidutils.generate_uuid()

        m.get("{}/{}".format(
            self._rules(l7_policy_id), l7_policy_rule_id),
            json={'rule': {}})
        m.delete("{}/{}".format(self._rules(l7_policy_id),
                             l7_policy_rule_id))

        req = self.new_delete_request('l7policies',
                                      l7_policy_id,
                                      subresource='rules',
                                      sub_id=l7_policy_rule_id)
        res = req.get_response(self.ext_api)
        self.assertEqual(res.status_int,
                         webob.exc.HTTPNoContent.code)

    @requests_mock.mock()
    def test_list_l7rules_with_sort_emulated(self, m):
        l7_policy_id = uuidutils.generate_uuid()
        expected = {
            'position': 1,
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
            'listener_id': uuidutils.generate_uuid(),
            'id': uuidutils.generate_uuid(),
        }

        m.get(self._rules(l7_policy_id),
              json={'rules': [expected]})

        self._test_list_with_sort('l7policy', [{'rule': expected}],
                                  [('value', 'asc')],
                                  id=l7_policy_id,
                                  resources='l7policies',
                                  subresource='rule',
                                  subresources='rules')


class PoolTestBase(ListenerTestBase):

    def _create_pool_api(self, data):
        req = self.new_create_request("pools", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_pool_api(self, pool_id, data):
        req = self.new_update_request('pools', data, pool_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _delete_pool_api(self, pool_id):
        req = self.new_delete_request('pools', pool_id)
        resp = req.get_response(self.ext_api)
        return resp

    def _get_pool_api(self, pool_id):
        req = self.new_show_request('pools', pool_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _list_pools_api(self):
        req = self.new_list_request('pools')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body


class LbaasPoolTests(PoolTestBase):
    url = '{}/{}'.format(base_url, 'pools')
    listener_id = uuidutils.generate_uuid()

    @requests_mock.mock()
    def test_create_pool(self, m, **extras):
        expected = {
            'name': '',
            'description': '',
            'protocol': 'HTTP',
            'lb_algorithm': 'ROUND_ROBIN',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'healthmonitor_id': None,
            'members': [],
            'id': uuidutils.generate_uuid()
        }

        expected.update(extras)
        m.post(self.url, json={'pool': expected})
        m.get(self.url, json={'pools': [expected]})

        with self.pool(listener_id=self.listener_id, no_delete=True,
                       **extras) as pool:
            pool_id = pool['pool'].get('id')
            if ('session_persistence' in expected.keys() and
                    expected['session_persistence'] is not None and
                    not expected['session_persistence'].get('cookie_name')):
                expected['session_persistence']['cookie_name'] = None
            self.assertTrue(pool_id)

            actual = {}
            for k, v in pool['pool'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
        return pool

    @requests_mock.mock()
    def test_show_pool(self, m, **extras):
        pool_id = uuidutils.generate_uuid()
        expected = {
            'name': '',
            'description': '',
            'protocol': 'HTTP',
            'lb_algorithm': 'ROUND_ROBIN',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'listeners': [{'id': self.listener_id}],
            'healthmonitor_id': None,
            'members': []
        }

        expected.update(extras)

        m.get('{}/{}'.format(self.url, pool_id), json={'pool': expected})
        resp, body = self._get_pool_api(pool_id)
        actual = {}
        for k, v in body['pool'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)
        return resp

    @requests_mock.mock()
    def test_update_pool(self, m, **extras):
        pool_id = uuidutils.generate_uuid()
        expected = {
            'name': '',
            'description': '',
            'protocol': 'HTTP',
            'lb_algorithm': 'LEAST_CONNECTIONS',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'listeners': [{'id': self.listener_id}],
            'healthmonitor_id': None,
            'members': []
        }

        expected.update(extras)
        m.get('{}/{}'.format(self.url, pool_id), json={'pool': expected})
        m.put('{}/{}'.format(self.url, pool_id), json={'pool': expected})

        data = {'pool': {'lb_algorithm': 'LEAST_CONNECTIONS'}}
        resp, body = self._update_pool_api(pool_id, data)
        actual = {}
        for k, v in body['pool'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

        return resp

    @requests_mock.mock()
    def test_delete_pool(self, m):
        pool_id = uuidutils.generate_uuid()
        m.get('{}/{}'.format(self.url, pool_id), json={'pool': {}})
        m.delete('{}/{}'.format(self.url, pool_id))
        resp = self._delete_pool_api(pool_id)
        self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    @requests_mock.mock()
    def test_cannot_add_multiple_pools_to_listener(self, m):
        data = {'pool': {'name': '',
                         'description': '',
                         'protocol': 'HTTP',
                         'lb_algorithm': 'ROUND_ROBIN',
                         'admin_state_up': True,
                         'tenant_id': self._tenant_id,
                         'listener_id': self.listener_id}}
        m.get(self.url, json={'pools': [data]})
        m.post(self.url, status_code=webob.exc.HTTPConflict.code)
        resp, body = self._create_pool_api(data)
        self.assertEqual(webob.exc.HTTPConflict.code, resp.status_int)

    @requests_mock.mock()
    def test_create_pool_with_protocol_invalid(self, m):
        data = {'pool': {
            'name': '',
            'description': '',
            'protocol': 'BLANK',
            'lb_algorithm': 'LEAST_CONNECTIONS',
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }}
        m.get(self.url, json={'pools': [data]})
        m.post(self.url, status_code=webob.exc.HTTPBadRequest.code)
        resp, body = self._create_pool_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    @requests_mock.mock()
    def test_list_pools(self, m):
        name = 'list_pools'
        expected_values = {'name': name,
                           'protocol': 'HTTP',
                           'description': 'apool',
                           'lb_algorithm': 'ROUND_ROBIN',
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'session_persistence': {'cookie_name': None,
                                                   'type': 'HTTP_COOKIE'},
                           'loadbalancers': [{'id': self.lb_id}],
                           'members': []}

        m.get(self.url, json={'pools': [expected_values]})
        resp, body = self._list_pools_api()
        pool_list = body['pools']
        self.assertEqual(1, len(pool_list))
        for k in expected_values:
            self.assertEqual(expected_values[k], pool_list[0][k])


class MemberTestBase(PoolTestBase):

    def _create_member_api(self, pool_id, data):
        req = self.new_create_request("pools", data, self.fmt, id=pool_id,
                                      subresource='members')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_member_api(self, pool_id, member_id, data):
        req = self.new_update_request('pools', data, pool_id,
                                      subresource='members', sub_id=member_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _delete_member_api(self, pool_id, member_id):
        req = self.new_delete_request('pools', pool_id, subresource='members',
                                      sub_id=member_id)
        resp = req.get_response(self.ext_api)
        return resp

    def _get_member_api(self, pool_id, member_id):
        req = self.new_show_request('pools', pool_id, subresource='members',
                                    sub_id=member_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _list_members_api(self, pool_id):
        req = self.new_list_request('pools', id=pool_id, subresource='members')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body


class LbaasMemberTests(MemberTestBase):
    pool_id = uuidutils.generate_uuid()
    member_id = uuidutils.generate_uuid()
    url = '{}/{}'.format(base_url, 'pools')
    test_subnet_id = uuidutils.generate_uuid()

    def _members(self, pool_id=None, member_id=None):
        pool_id = pool_id if pool_id else self.pool_id
        member = '/{}'.format(member_id) if member_id else ''
        return "{}/{}/members{}".format(self.url, pool_id, member)

    @requests_mock.mock()
    def test_create_member(self, m, **extras):
        network = self._make_network(self.fmt, 'test-net', True)
        self.test_subnet = self._make_subnet(
            self.fmt, network, gateway=n_constants.ATTR_NOT_SPECIFIED,
            cidr='10.0.0.0/24')
        self.test_subnet_id = self.test_subnet['subnet']['id']
        expected = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'subnet_id': '',
            'name': 'member1',
            'id': uuidutils.generate_uuid()
        }

        expected.update(extras)
        expected['subnet_id'] = self.test_subnet_id

        m.post(self._members(), json={'member': expected})
        with self.member(pool_id=self.pool_id, name='member1',
                         no_delete=True) as member:
            member_id = member['member'].get('id')
            self.assertTrue(member_id)

            actual = {}
            for k, v in member['member'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
        return member

    @requests_mock.mock()
    def test_update_member(self, m):
        expected = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'subnet_id': '',
            'name': 'member1',
            'id': uuidutils.generate_uuid()
        }

        m.get(self._members(member_id=self.member_id),
              json={'member': expected})
        m.put(self._members(member_id=self.member_id),
              json={'member': expected})

        data = {'member': {'weight': 10, 'admin_state_up': False,
                           'name': 'member2'}}
        resp, body = self._update_member_api(self.pool_id,
                                             self.member_id, data)

        actual = {}
        for k, v in body['member'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

    @requests_mock.mock()
    def test_delete_member(self, m):
        m.get(self._members(member_id=self.member_id), json={'member': {}})
        m.delete(self._members(member_id=self.member_id))
        resp = self._delete_member_api(self.pool_id, self.member_id)
        self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    @requests_mock.mock()
    def test_show_member(self, m):
        expected = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'subnet_id': '',
            'name': 'member1',
            'id': uuidutils.generate_uuid()
        }

        m.get(self._members(member_id=self.member_id),
              json={'member': expected})
        resp, body = self._get_member_api(self.pool_id, self.member_id)
        actual = {}
        for k, v in body['member'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

    @requests_mock.mock()
    def test_list_members(self, m):
        expected = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'subnet_id': '',
            'name': 'member1',
            'id': uuidutils.generate_uuid()
        }
        m.get(self._members(), json={'members': [expected]})
        resp, body = self._list_members_api(self.pool_id)
        self.assertEqual(1, len(body['members']))

    @requests_mock.mock()
    def test_create_member_invalid_pool_id(self, m):
        data = {'member': {'address': '127.0.0.1',
                           'protocol_port': 80,
                           'weight': 1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'subnet_id': self.test_subnet_id}}
        m.post(self._members(pool_id='WRONG_POOL_ID'), status_code=404)
        resp, body = self._create_member_api('WRONG_POOL_ID', data)
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    @requests_mock.mock()
    def test_create_member_invalid_name(self, m):
        m.post(self._members(), status_code=webob.exc.HTTPBadRequest.code)
        data = {'member': {'address': '127.0.0.1',
                           'protocol_port': 80,
                           'weight': 1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'subnet_id': self.test_subnet_id,
                           'name': 123}}
        resp, body = self._create_member_api('POOL_ID', data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    @requests_mock.mock()
    def test_delete_member_invalid_pool_id(self, m):
        m.get(self._members('WRONG_POOL_ID', self.member_id), status_code=404)

        resp = self._delete_member_api('WRONG_POOL_ID', self.member_id)
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)


class HealthMonitorTestBase(MemberTestBase):

    def _create_healthmonitor_api(self, data):
        req = self.new_create_request("healthmonitors", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_healthmonitor_api(self, hm_id, data):
        req = self.new_update_request('healthmonitors', data, hm_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _delete_healthmonitor_api(self, hm_id):
        req = self.new_delete_request('healthmonitors', hm_id)
        resp = req.get_response(self.ext_api)
        return resp

    def _get_healthmonitor_api(self, hm_id):
        req = self.new_show_request('healthmonitors', hm_id)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _list_healthmonitors_api(self):
        req = self.new_list_request('healthmonitors')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body


class TestLbaasHealthMonitorTests(HealthMonitorTestBase):
    url = '{}/{}'.format(base_url, 'healthmonitors')
    hm_id = uuidutils.generate_uuid()
    pool_id = uuidutils.generate_uuid()

    @requests_mock.mock()
    def test_create_healthmonitor(self, m, **extras):
        expected = {
            'type': 'HTTP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 2,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1',
            'id': self.hm_id
        }

        expected.update(extras)
        m.post(self.url, json={'healthmonitor': expected})

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1', no_delete=True,
                                **extras) as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            self.assertTrue(hm_id)

            actual = {}
            for k, v in healthmonitor['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
        return healthmonitor

    @requests_mock.mock()
    def test_show_healthmonitor(self, m, **extras):
        expected = {
            'type': 'HTTP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 2,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'
        }

        expected.update(extras)

        m.get('{}/{}'.format(self.url, self.hm_id),
              json={'healthmonitor': expected})

        resp, body = self._get_healthmonitor_api(self.hm_id)
        actual = {}
        for k, v in body['healthmonitor'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

    @requests_mock.mock()
    def test_update_healthmonitor(self, m, **extras):
        expected = {
            'type': 'HTTP',
            'delay': 30,
            'timeout': 10,
            'max_retries': 4,
            'http_method': 'GET',
            'url_path': '/index.html',
            'expected_codes': '200,404',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor2'
        }

        expected.update(extras)
        m.get('{}/{}'.format(self.url, self.hm_id),
              json={'healthmonitor': expected})
        m.put('{}/{}'.format(self.url, self.hm_id),
              json={'healthmonitor': expected})

        data = {'healthmonitor': {'delay': 30,
                                  'timeout': 10,
                                  'max_retries': 4,
                                  'expected_codes': '200,404',
                                  'url_path': '/index.html',
                                  'name': 'monitor2'}}
        resp, body = self._update_healthmonitor_api(self.hm_id, data)
        actual = {}
        for k, v in body['healthmonitor'].items():
            if k in expected:
                actual[k] = v
        self.assertEqual(expected, actual)

    @requests_mock.mock()
    def test_delete_healthmonitor(self, m):
        m.get('{}/{}'.format(self.url, self.hm_id), json={'healthmonitor': {}})
        m.delete('{}/{}'.format(self.url, self.hm_id))
        resp = self._delete_healthmonitor_api(self.hm_id)
        self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    @requests_mock.mock()
    def test_create_health_monitor_with_timeout_invalid(self, m):
        m.post(self.url, status_code=webob.exc.HTTPBadRequest.code)
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 1,
                                  'timeout': -1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    @requests_mock.mock()
    def test_create_healthmonitor_invalid_pool_id(self, m):
        m.post(self.url, status_code=webob.exc.HTTPNotFound.code)
        data = {'healthmonitor': {'type': lb_const.HEALTH_MONITOR_TCP,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 1,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': uuidutils.generate_uuid()}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    @requests_mock.mock()
    def test_only_one_healthmonitor_per_pool(self, m):
        m.post(self.url, status_code=webob.exc.HTTPConflict.code)
        data = {'healthmonitor': {'type': lb_const.HEALTH_MONITOR_TCP,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 1,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPConflict.code, resp.status_int)

    @requests_mock.mock()
    def test_list_healthmonitors(self, m):
        expected = {
            'type': 'HTTP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 2,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': '',
            'max_retries_down': 3,
            'id': self.hm_id
        }

        m.get(self.url, json={'healthmonitors': [expected]})

        resp, body = self._list_healthmonitors_api()
        self.assertEqual([expected], body['healthmonitors'])


class LbaasStatusesTest(TestLbaasProxyPluginDbTestCase):
    lb_id = uuidutils.generate_uuid()
    url = '{}/{}'.format(base_url, 'loadbalancers')

    @requests_mock.mock()
    def test_status_tree_lb(self, m):
        expected = {
            "loadbalancer": {
                "operating_status": "ONLINE",
                "provisioning_status": "ACTIVE",
                "listeners": [
                    {
                        "id": "6978ba19-1090-48a2-93d5-3523592b562a",
                        "operating_status": "ONLINE",
                        "provisioning_status": "ACTIVE",
                        "pools": [
                            {
                                "id": "f6aedfcb-9f7d-4cc5-83e1-8c02fd833922",
                                "operating_status": "ONLINE",
                                "provisioning_status": "ACTIVE",
                                "members": [
                                    {
                                        "id":
                                       "fcf23bde-8cf9-4616-883f-208cebcbf858",
                                        "operating_status": "ONLINE",
                                        "provisioning_status": "ACTIVE",
                                    }
                                ],
                                "healthmonitor": {
                                    "id":
                                        "785131d2-8f7b-4fee-a7e7-3196e11b4518",
                                    "provisioning_status": "ACTIVE",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        m.get('{}/{}'.format(self.url, self.lb_id),
              json={'loadbalancer': {'id': self.lb_id}})
        m.get('{}/{}/status'.format(self.url, self.lb_id),
              json={'statuses': expected})
        statuses = self._get_loadbalancer_statuses_api(self.lb_id)[1]
        self.assertEqual(expected, statuses['statuses'])


class LbaasStatsTest(MemberTestBase):
    lb_id = uuidutils.generate_uuid()
    url = '{}/{}'.format(base_url, 'loadbalancers')

    @requests_mock.mock()
    def test_stats(self, m):
        expected = {
            "stats": {
                "bytes_in": "131342840",
                "total_connections": "52378345",
                "active_connections": "97258",
                "bytes_out": "1549542372",
                "request_errors": "0"
            }
        }
        m.get('{}/{}'.format(self.url, self.lb_id),
              json={'loadbalancer': {'id': self.lb_id}})
        m.get('{}/{}/stats'.format(self.url, self.lb_id),
              json={'stats': expected})
        stats = self._get_loadbalancer_stats_api(self.lb_id)[1]
        self.assertEqual(expected, stats['stats'])


class LbaasGraphTest(MemberTestBase):
    lb_id = uuidutils.generate_uuid()
    url = '{}/{}'.format(base_url, 'graph')

    @requests_mock.mock()
    def create_graph(self, m, expected_lb_graph, listeners):
        with self.subnet() as subnet:
            expected_lb_graph['vip_subnet_id'] = subnet['subnet']['id']
            for listener in listeners:
                for member in listener.get('default_pool',
                                           {}).get('members', []):
                    member['subnet_id'] = subnet['subnet']['id']
            for listener in expected_lb_graph.get('listeners', []):
                for member in listener.get('default_pool',
                                           {}).get('members', []):
                    member['subnet_id'] = subnet['subnet']['id']
            name = expected_lb_graph.get('name')
            kwargs = {'name': name, 'subnet': subnet, 'listeners': listeners}
            m.post(self.url, json={'graph': expected_lb_graph})
            with self.graph(no_delete=True, **kwargs) as graph:
                lb = graph['graph']['loadbalancer']
                self._assert_graphs_equal(expected_lb_graph, lb)
