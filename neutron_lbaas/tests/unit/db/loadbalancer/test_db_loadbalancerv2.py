# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy

import mock
import six
import testtools
import webob.exc

from neutron.api import extensions
from neutron.common import config
from neutron_lib import constants as n_constants
from neutron_lib import context
from neutron_lib import exceptions as n_exc
from neutron_lib.plugins import constants
from neutron_lib.plugins import directory
from oslo_config import cfg
from oslo_utils import uuidutils

from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.common import exceptions
from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2
from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.drivers.logging_noop import driver as noop_driver
import neutron_lbaas.extensions
from neutron_lbaas.extensions import l7
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.extensions import sharedpools
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import plugin as loadbalancer_plugin
from neutron_lbaas.tests import base
from neutron_lbaas.tests.unit.db.loadbalancer import util


DB_CORE_PLUGIN_CLASS = 'neutron.db.db_base_plugin_v2.NeutronDbPluginV2'
DB_LB_PLUGIN_CLASS = (
    "neutron_lbaas.services.loadbalancer."
    "plugin.LoadBalancerPluginv2"
)
NOOP_DRIVER_CLASS = ('neutron_lbaas.drivers.logging_noop.driver.'
                     'LoggingNoopLoadBalancerDriver')

extensions_path = ':'.join(neutron_lbaas.extensions.__path__)

_subnet_id = "0c798ed8-33ba-11e2-8b28-000c291c4d14"


class LbaasPluginDbTestCase(util.LbaasTestMixin,
                            base.NeutronDbPluginV2TestCase):
    def setUp(self, core_plugin=None, lb_plugin=None, lbaas_provider=None,
              ext_mgr=None):
        service_plugins = {'lb_plugin_name': DB_LB_PLUGIN_CLASS}
        if not lbaas_provider:
            lbaas_provider = (
                constants.LOADBALANCERV2 +
                ':lbaas:' + NOOP_DRIVER_CLASS + ':default')
        # override the default service provider
        self.set_override([lbaas_provider])

        # removing service-type because it resides in neutron and tests
        # dont care
        LBPlugin = loadbalancer_plugin.LoadBalancerPluginv2
        sea_index = None
        for index, sea in enumerate(LBPlugin.supported_extension_aliases):
            if sea == 'service-type':
                sea_index = index
        if sea_index:
            del LBPlugin.supported_extension_aliases[sea_index]

        super(LbaasPluginDbTestCase, self).setUp(
            ext_mgr=ext_mgr,
            service_plugins=service_plugins
        )

        if not ext_mgr:
            self.plugin = loadbalancer_plugin.LoadBalancerPluginv2()
            # This is necessary because the automatic extension manager
            # finding algorithm below will find the loadbalancerv2
            # extension and fail to initizlize the main API router with
            # extensions' resources
            ext_mgr = util.ExtendedPluginAwareExtensionManager(
                LBPlugin.supported_extension_aliases)

            app = config.load_paste_app('extensions_test_app')
            self.ext_api = extensions.ExtensionMiddleware(app, ext_mgr=ext_mgr)

        get_lbaas_agent_patcher = mock.patch(
            'neutron_lbaas.agent_scheduler'
            '.LbaasAgentSchedulerDbMixin.get_agent_hosting_loadbalancer')
        mock_lbaas_agent = mock.MagicMock()
        get_lbaas_agent_patcher.start().return_value = mock_lbaas_agent
        mock_lbaas_agent.__getitem__.return_value = {'host': 'host'}

        self._subnet_id = _subnet_id

    def _update_loadbalancer_api(self, lb_id, data):
        req = self.new_update_request_lbaas('loadbalancers', data, lb_id)
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

    def _validate_statuses(self, lb_id, listener_id=None,
                           l7policy_id=None, l7rule_id=None,
                           pool_id=None, member_id=None, hm_id=None,
                           member_disabled=False, listener_disabled=False,
                           l7policy_disabled=False, l7rule_disabled=False,
                           loadbalancer_disabled=False):
        resp, body = self._get_loadbalancer_statuses_api(lb_id)
        lb_statuses = body['statuses']['loadbalancer']
        self.assertEqual(n_constants.ACTIVE,
                         lb_statuses['provisioning_status'])
        if loadbalancer_disabled:
            self.assertEqual(lb_const.DISABLED,
                            lb_statuses['operating_status'])
        else:
            self.assertEqual(lb_const.ONLINE,
                         lb_statuses['operating_status'])
        if listener_id:
            listener_statuses = None
            for listener in lb_statuses['listeners']:
                if listener['id'] == listener_id:
                    listener_statuses = listener
            self.assertIsNotNone(listener_statuses)
            self.assertEqual(n_constants.ACTIVE,
                             listener_statuses['provisioning_status'])
            if listener_disabled:
                self.assertEqual(lb_const.DISABLED,
                                 listener_statuses['operating_status'])
            else:
                self.assertEqual(lb_const.ONLINE,
                                 listener_statuses['operating_status'])
            if l7policy_id:
                policy_statuses = None
                for policy in listener_statuses['l7policies']:
                    if policy['id'] == l7policy_id:
                        policy_statuses = policy
                self.assertIsNotNone(policy_statuses)
                self.assertEqual(n_constants.ACTIVE,
                                 policy_statuses['provisioning_status'])
                if l7rule_id:
                    rule_statuses = None
                    for rule in policy_statuses['rules']:
                        if rule['id'] == l7rule_id:
                            rule_statuses = rule
                    self.assertIsNotNone(rule_statuses)
                    self.assertEqual(n_constants.ACTIVE,
                                     rule_statuses['provisioning_status'])

        if pool_id:
            pool_statuses = None
            for pool in lb_statuses['pools']:
                if pool['id'] == pool_id:
                    pool_statuses = pool
            self.assertIsNotNone(pool_statuses)
            self.assertEqual(n_constants.ACTIVE,
                             pool_statuses['provisioning_status'])
            self.assertEqual(lb_const.ONLINE,
                             pool_statuses['operating_status'])
            if member_id:
                member_statuses = None
                for member in pool_statuses['members']:
                    if member['id'] == member_id:
                        member_statuses = member
                self.assertIsNotNone(member_statuses)
                self.assertEqual(n_constants.ACTIVE,
                                 member_statuses['provisioning_status'])
                if member_disabled:
                    self.assertEqual(lb_const.DISABLED,
                                     member_statuses["operating_status"])
                else:
                    self.assertEqual(lb_const.ONLINE,
                                     member_statuses['operating_status'])
            if hm_id:
                hm_status = pool_statuses['healthmonitor']
                self.assertEqual(n_constants.ACTIVE,
                                 hm_status['provisioning_status'])

    def test_assert_modification_allowed(self):
        mock_lb = mock.MagicMock()
        mock_lb.provisioning_status = n_constants.PENDING_UPDATE
        mock_lb.id = uuidutils.generate_uuid()
        LBPluginDBv2 = loadbalancer_dbv2.LoadBalancerPluginDbv2()

        self.assertRaises(
            loadbalancerv2.StateInvalid,
            LBPluginDBv2.assert_modification_allowed, mock_lb)
        # Check that this is a sub-exception of conflict to return 409
        self.assertRaises(
            n_exc.Conflict,
            LBPluginDBv2.assert_modification_allowed, mock_lb)


class LbaasLoadBalancerTests(LbaasPluginDbTestCase):

    def test_create_loadbalancer(self, **extras):
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

        expected.update(extras)

        with self.subnet() as subnet:
            expected['vip_subnet_id'] = subnet['subnet']['id']
            name = expected['name']

            with self.loadbalancer(name=name, subnet=subnet, **extras) as lb:
                lb_id = lb['loadbalancer']['id']
                for k in ('id', 'vip_address', 'vip_subnet_id'):
                    self.assertTrue(lb['loadbalancer'].get(k, None))

                expected['vip_port_id'] = lb['loadbalancer']['vip_port_id']
                actual = dict((k, v)
                              for k, v in lb['loadbalancer'].items()
                              if k in expected)
                self.assertEqual(expected, actual)
                self._validate_statuses(lb_id)
            return lb

    def test_create_loadbalancer_with_vip_address(self):
        self.test_create_loadbalancer(vip_address='10.0.0.7')

    def test_create_loadbalancer_with_vip_address_outside_subnet(self):
        with testtools.ExpectedException(webob.exc.HTTPClientError):
            self.test_create_loadbalancer(vip_address='9.9.9.9')

    def test_create_loadbalancer_with_no_vip_network_or_subnet(self):
        with testtools.ExpectedException(webob.exc.HTTPClientError):
            self.test_create_loadbalancer(
                vip_network_id=None,
                vip_subnet_id=None,
                expected_res_status=400)

    def test_create_loadbalancer_with_vip_network_id(self):
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

        with self.subnet() as subnet:
            expected['vip_subnet_id'] = subnet['subnet']['id']
            name = expected['name']
            extras = {
                'vip_network_id': subnet['subnet']['network_id'],
                'vip_subnet_id': None
            }

            with self.loadbalancer(name=name, subnet=subnet, **extras) as lb:
                lb_id = lb['loadbalancer']['id']
                for k in ('id', 'vip_address', 'vip_subnet_id'):
                    self.assertTrue(lb['loadbalancer'].get(k, None))

                expected['vip_port_id'] = lb['loadbalancer']['vip_port_id']
                actual = dict((k, v)
                              for k, v in lb['loadbalancer'].items()
                              if k in expected)
                self.assertEqual(expected, actual)
                self._validate_statuses(lb_id)
            return lb

    def test_create_loadbalancer_with_vip_network_id_no_subnets(self):
        with self.network() as net:
            with testtools.ExpectedException(webob.exc.HTTPClientError):
                self.test_create_loadbalancer(
                    vip_network_id=net['network']['id'],
                    vip_subnet_id=None,
                    expected_res_status=400)

    def test_update_loadbalancer(self):
        name = 'new_loadbalancer'
        description = 'a crazy loadbalancer'
        expected_values = {'name': name,
                           'description': description,
                           'admin_state_up': False,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas'}
        with self.subnet() as subnet:
            expected_values['vip_subnet_id'] = subnet['subnet']['id']
            with self.loadbalancer(subnet=subnet) as loadbalancer:
                expected_values['vip_port_id'] = (
                    loadbalancer['loadbalancer']['vip_port_id'])
                loadbalancer_id = loadbalancer['loadbalancer']['id']
                data = {'loadbalancer': {'name': name,
                                         'description': description,
                                         'admin_state_up': False}}
                resp, res = self._update_loadbalancer_api(loadbalancer_id,
                                                          data)
                for k in expected_values:
                    self.assertEqual(expected_values[k],
                                     res['loadbalancer'][k])
                self._validate_statuses(loadbalancer_id,
                                        loadbalancer_disabled=True)

    def test_delete_loadbalancer(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet,
                                   no_delete=True) as loadbalancer:
                loadbalancer_id = loadbalancer['loadbalancer']['id']
                resp = self._delete_loadbalancer_api(loadbalancer_id)
                self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    def test_delete_loadbalancer_when_loadbalancer_in_use(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet) as loadbalancer:
                lb_id = loadbalancer['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id):
                    ctx = context.get_admin_context()
                    self.assertRaises(loadbalancerv2.EntityInUse,
                                      self.plugin.delete_loadbalancer,
                                      ctx, lb_id)
                    self._validate_statuses(lb_id)

    def test_show_loadbalancer(self):
        name = 'lb_show'
        description = 'lb_show description'
        vip_address = '10.0.0.10'
        expected_values = {'name': name,
                           'description': description,
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas'}
        with self.subnet() as subnet:
            vip_subnet_id = subnet['subnet']['id']
            expected_values['vip_subnet_id'] = vip_subnet_id
            with self.loadbalancer(subnet=subnet, name=name,
                                   description=description,
                                   vip_address=vip_address) as lb:
                lb_id = lb['loadbalancer']['id']
                expected_values['id'] = lb_id
                expected_values['vip_port_id'] = (
                    lb['loadbalancer']['vip_port_id'])
                resp, body = self._get_loadbalancer_api(lb_id)
                for k in expected_values:
                    self.assertEqual(expected_values[k],
                                     body['loadbalancer'][k])

    def test_list_loadbalancers(self):
        name = 'lb_show'
        description = 'lb_show description'
        vip_address = '10.0.0.10'
        expected_values = {'name': name,
                           'description': description,
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': [],
                           'provider': 'lbaas'}
        with self.subnet() as subnet:
            vip_subnet_id = subnet['subnet']['id']
            expected_values['vip_subnet_id'] = vip_subnet_id
            with self.loadbalancer(subnet=subnet, name=name,
                                   description=description,
                                   vip_address=vip_address) as lb:
                lb_id = lb['loadbalancer']['id']
                expected_values['id'] = lb_id
                expected_values['vip_port_id'] = (
                    lb['loadbalancer']['vip_port_id'])
                resp, body = self._list_loadbalancers_api()
                self.assertEqual(1, len(body['loadbalancers']))
                for k in expected_values:
                    self.assertEqual(expected_values[k],
                                     body['loadbalancers'][0][k])

    def test_list_loadbalancers_with_sort_emulated(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet, name='lb1') as lb1:
                with self.loadbalancer(subnet=subnet, name='lb2') as lb2:
                    with self.loadbalancer(subnet=subnet, name='lb3') as lb3:
                        self._test_list_with_sort(
                            'loadbalancer',
                            (lb1, lb2, lb3),
                            [('name', 'asc')]
                        )

    def test_list_loadbalancers_with_pagination_emulated(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet, name='lb1') as lb1:
                with self.loadbalancer(subnet=subnet, name='lb2') as lb2:
                    with self.loadbalancer(subnet=subnet, name='lb3') as lb3:
                        self._test_list_with_pagination(
                            'loadbalancer',
                            (lb1, lb2, lb3),
                            ('name', 'asc'), 2, 2
                        )

    def test_list_loadbalancers_with_pagination_reverse_emulated(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet, name='lb1') as lb1:
                with self.loadbalancer(subnet=subnet, name='lb2') as lb2:
                    with self.loadbalancer(subnet=subnet, name='lb3') as lb3:
                        self._test_list_with_pagination_reverse(
                            'loadbalancer',
                            (lb1, lb2, lb3),
                            ('name', 'asc'), 2, 2
                        )

    def test_get_loadbalancer_stats(self):
        expected_values = {'stats': {lb_const.STATS_TOTAL_CONNECTIONS: 0,
                                     lb_const.STATS_ACTIVE_CONNECTIONS: 0,
                                     lb_const.STATS_OUT_BYTES: 0,
                                     lb_const.STATS_IN_BYTES: 0}}
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet) as lb:
                lb_id = lb['loadbalancer']['id']
                resp, body = self._get_loadbalancer_stats_api(lb_id)
                self.assertEqual(expected_values, body)

    def test_show_loadbalancer_with_listeners(self):
        name = 'lb_show'
        description = 'lb_show description'
        vip_address = '10.0.0.10'
        expected_values = {'name': name,
                           'description': description,
                           'vip_address': '10.0.0.10',
                           'admin_state_up': True,
                           'provisioning_status': n_constants.ACTIVE,
                           'operating_status': lb_const.ONLINE,
                           'listeners': []}
        with self.subnet() as subnet:
            vip_subnet_id = subnet['subnet']['id']
            expected_values['vip_subnet_id'] = vip_subnet_id
            with self.loadbalancer(subnet=subnet, name=name,
                                   description=description,
                                   vip_address=vip_address) as lb:
                lb_id = lb['loadbalancer']['id']
                expected_values['id'] = lb_id
                with self.listener(loadbalancer_id=lb_id,
                                   protocol_port=80) as listener1:
                    listener1_id = listener1['listener']['id']
                    expected_values['listeners'].append({'id': listener1_id})
                    with self.listener(loadbalancer_id=lb_id,
                                       protocol_port=81) as listener2:
                        listener2_id = listener2['listener']['id']
                        expected_values['listeners'].append(
                            {'id': listener2_id})
                        resp, body = self._get_loadbalancer_api(lb_id)
                        for k in expected_values:
                            self.assertEqual(expected_values[k],
                                             body['loadbalancer'][k])

    def test_port_delete_via_port_api(self):
        port = {
            'id': 'my_port_id',
            'device_owner': n_constants.DEVICE_OWNER_LOADBALANCERV2
        }
        ctx = context.get_admin_context()
        port['device_owner'] = n_constants.DEVICE_OWNER_LOADBALANCERV2
        plugin = mock.Mock()
        directory.add_plugin(constants.CORE, plugin)
        self.plugin.db.get_loadbalancer_ids = (
            mock.Mock(return_value=['1']))
        plugin._get_port.return_value = port
        self.assertRaises(n_exc.ServicePortInUse,
                          self.plugin.db.prevent_lbaasv2_port_deletion,
                          ctx,
                          port['id'])


class LoadBalancerDelegateVIPCreation(LbaasPluginDbTestCase):

    def setUp(self):
        driver_patcher = mock.patch.object(
            noop_driver.LoggingNoopLoadBalancerManager,
            'allocates_vip', new_callable=mock.PropertyMock)
        driver_patcher.start().return_value = True
        super(LoadBalancerDelegateVIPCreation, self).setUp()

    def test_create_loadbalancer(self):
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

        with self.subnet() as subnet:
            expected['vip_subnet_id'] = subnet['subnet']['id']
            name = expected['name']

            with self.loadbalancer(name=name, subnet=subnet) as lb:
                lb_id = lb['loadbalancer']['id']
                for k in ('id', 'vip_subnet_id'):
                    self.assertTrue(lb['loadbalancer'].get(k, None))

                self.assertIsNone(lb['loadbalancer'].get('vip_address'))
                expected['vip_port_id'] = lb['loadbalancer']['vip_port_id']
                actual = dict((k, v)
                              for k, v in lb['loadbalancer'].items()
                              if k in expected)
                self.assertEqual(expected, actual)
                self._validate_statuses(lb_id)
            return lb

    def test_delete_loadbalancer(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet, no_delete=True) as lb:
                lb_id = lb['loadbalancer']['id']
                acontext = context.get_admin_context()
                db_port = self.plugin.db._core_plugin.create_port(
                    acontext,
                    {'port': {'network_id': subnet['subnet']['network_id'],
                              'name': '', 'admin_state_up': True,
                              'device_id': lb_id, 'device_owner': '',
                              'mac_address': '', 'fixed_ips': [],
                              'tenant_id': acontext.tenant_id}})
                port_id = db_port['id']
                self.addCleanup(self.plugin.db._core_plugin.delete_port,
                                acontext, port_id)
                self.plugin.db.update_loadbalancer(
                    acontext, lb_id,
                    {'loadbalancer': {'vip_port_id': port_id}})
                self.plugin.db.delete_loadbalancer(
                    acontext, lb_id, delete_vip_port=True)
                port = self.plugin.db._core_plugin.get_port(acontext, port_id)
                self.assertIsNotNone(port)


class TestLoadBalancerGraphCreation(LbaasPluginDbTestCase):

    def _assert_graphs_equal(self, expected_graph, observed_graph):
        observed_graph_copy = copy.deepcopy(observed_graph)
        for k in ('id', 'vip_address', 'vip_subnet_id'):
            self.assertTrue(observed_graph_copy.get(k, None))

        expected_graph['id'] = observed_graph_copy['id']
        expected_graph['vip_port_id'] = observed_graph_copy['vip_port_id']
        expected_listeners = expected_graph.pop('listeners', [])
        observed_listeners = observed_graph_copy.pop('listeners', [])
        actual = dict((k, v)
                      for k, v in observed_graph_copy.items()
                      if k in expected_graph)
        self.assertEqual(expected_graph, actual)
        for observed_listener in observed_listeners:
            self.assertTrue(observed_listener.get('id'))
            listener_id = observed_listener.pop('id')
            default_pool = observed_listener.get('default_pool')
            l7_policies = observed_listener.get('l7policies')
            if default_pool:
                self.assertTrue(default_pool.get('id'))
                default_pool.pop('id')
                hm = default_pool.get('healthmonitor')
                if hm:
                    self.assertTrue(hm.get('id'))
                    hm.pop('id')
                for member in default_pool.get('members', []):
                    self.assertTrue(member.get('id'))
                    member.pop('id')
            if l7_policies:
                for policy in l7_policies:
                    self.assertTrue(policy.get('id'))
                    self.assertTrue(policy.get('listener_id'))
                    self.assertEqual(listener_id, policy.get('listener_id'))
                    policy.pop('id')
                    policy.pop('listener_id')
                    r_pool = policy.get('redirect_pool')
                    rules = policy.get('rules')
                    if r_pool:
                        self.assertTrue(r_pool.get('id'))
                        r_pool.pop('id')
                        r_hm = r_pool.get('healthmonitor')
                        if r_hm:
                            self.assertTrue(r_hm.get('id'))
                            r_hm.pop('id')
                        for r_member in r_pool.get('members', []):
                            self.assertTrue(r_member.get('id'))
                            r_member.pop('id')
                    if rules:
                        for rule in rules:
                            self.assertTrue(rule.get('id'))
                            rule.pop('id')
            self.assertIn(observed_listener, expected_listeners)

    def _validate_graph_statuses(self, graph):
        lb_id = graph['id']
        for listener in graph.get('listeners', []):
            kwargs = {'listener_id': listener['id']}
            pool = listener.get('default_pool')
            if pool:
                kwargs['pool_id'] = pool['id']
                hm = pool.get('health_monitor')
                if hm:
                    kwargs['hm_id'] = hm['id']
                for member in pool.get('members', []):
                    kwargs['member_id'] = member['id']
                    self._validate_statuses(lb_id, **kwargs)
                if pool.get('members'):
                    continue
            self._validate_statuses(lb_id, **kwargs)

    def _get_expected_lb(self, expected_listeners):
        expected_lb = {
            'name': 'vip1',
            'description': '',
            'admin_state_up': True,
            'provisioning_status': n_constants.ACTIVE,
            'operating_status': lb_const.ONLINE,
            'tenant_id': self._tenant_id,
            'listeners': expected_listeners,
            'provider': 'lbaas'
        }
        return expected_lb

    def _get_listener_bodies(self, name='listener1', protocol_port=80,
                             create_default_pool=None,
                             expected_default_pool=None,
                             create_l7_policies=None,
                             expected_l7_policies=None):
        create_listener = {
            'name': name,
            'protocol_port': protocol_port,
            'protocol': lb_const.PROTOCOL_HTTP,
            'tenant_id': self._tenant_id,
        }
        if create_default_pool:
            create_listener['default_pool'] = create_default_pool
        if create_l7_policies:
            create_listener['l7policies'] = create_l7_policies
        expected_listener = {
            'description': '',
            'default_tls_container_ref': None,
            'sni_container_refs': [],
            'connection_limit': -1,
            'admin_state_up': True,
            'l7policies': []
        }
        expected_listener.update(create_listener)
        if expected_default_pool:
            expected_listener['default_pool'] = expected_default_pool
        expected_listener['default_tls_container_id'] = None
        expected_listener['l7policies'] = expected_l7_policies or []
        return create_listener, expected_listener

    def _get_pool_bodies(self, name='pool1', create_members=None,
                         expected_members=None, create_hm=None,
                         expected_hm=None):
        create_pool = {
            'name': name,
            'protocol': lb_const.PROTOCOL_HTTP,
            'lb_algorithm': lb_const.LB_METHOD_ROUND_ROBIN,
            'tenant_id': self._tenant_id
        }
        if create_members:
            create_pool['members'] = create_members
        if create_hm:
            create_pool['healthmonitor'] = create_hm
        expected_pool = {
            'description': '',
            'session_persistence': None,
            'members': [],
            'admin_state_up': True
        }
        expected_pool.update(create_pool)
        if expected_members:
            expected_pool['members'] = expected_members
        if expected_hm:
            expected_pool['healthmonitor'] = expected_hm
        return create_pool, expected_pool

    def _get_member_bodies(self, name='member1'):
        create_member = {
            'name': name,
            'address': '10.0.0.1',
            'protocol_port': 80,
            'subnet_id': self._subnet_id,
            'tenant_id': self._tenant_id
        }
        expected_member = {
            'weight': 1,
            'admin_state_up': True,
        }
        expected_member.update(create_member)
        return create_member, expected_member

    def _get_hm_bodies(self, name='hm1'):
        create_hm = {
            'name': name,
            'type': lb_const.HEALTH_MONITOR_HTTP,
            'delay': 1,
            'timeout': 1,
            'max_retries': 1,
            'tenant_id': self._tenant_id,
            'max_retries_down': 1
        }
        expected_hm = {
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True
        }
        expected_hm.update(create_hm)
        return create_hm, expected_hm

    def _get_l7policies_bodies(self, name='l7policy_name', create_rules=None,
                               expected_rules=None, create_r_pool=None,
                               expected_r_pool=None):
        c_policy = {
            'name': name,
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }
        if create_r_pool:
            c_policy['redirect_pool'] = create_r_pool
        if create_rules:
            c_policy['rules'] = create_rules
        e_policy = {
            'description': '',
            'position': 1
        }
        e_policy.update(c_policy)
        if expected_r_pool:
            e_policy['redirect_pool'] = expected_r_pool
        if expected_rules:
            e_policy['rules'] = expected_rules
        create_l7policies = [c_policy]
        expected_l7policies = [e_policy]
        return create_l7policies, expected_l7policies

    def _get_l7rules_bodes(self):
        create_rule = {
            'compare_type': lb_const.L7_RULE_COMPARE_TYPE_EQUAL_TO,
            'type': lb_const.L7_RULE_TYPE_HOST_NAME,
            'invert': False,
            'value': 'localhost',
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }
        create_rules = [create_rule]
        expected_rule = {
            'key': None
        }
        expected_rule.update(create_rule)
        expected_rules = [expected_rule]
        return create_rules, expected_rules

    def create_graph(self, expected_lb_graph, listeners):
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
            with self.graph(**kwargs) as graph:
                lb = graph['graph']['loadbalancer']
                self._assert_graphs_equal(expected_lb_graph, lb)
                self._validate_graph_statuses(lb)
            return graph

    def test_with_one_listener(self):
        create_listener, expected_listener = self._get_listener_bodies()
        expected_lb = self._get_expected_lb([expected_listener])
        self.create_graph(expected_lb, [create_listener])

    def test_with_many_listeners(self):
        create_listener1, expected_listener1 = self._get_listener_bodies()
        create_listener2, expected_listener2 = self._get_listener_bodies(
            name='listener2', protocol_port=81)
        expected_lb = self._get_expected_lb(
            [expected_listener1, expected_listener2])
        self.create_graph(expected_lb,
                          [create_listener1, create_listener2])

    def test_with_many_listeners_same_port(self):
        create_listener1, expected_listener1 = self._get_listener_bodies()
        create_listener2, expected_listener2 = self._get_listener_bodies()
        try:
            self.create_graph(
                {}, [create_listener1, create_listener2])
        except webob.exc.HTTPClientError as exc:
            self.assertEqual(exc.status_code, 409)

    def test_with_one_listener_one_pool(self):
        create_pool, expected_pool = self._get_pool_bodies()
        create_listener, expected_listener = self._get_listener_bodies(
            create_default_pool=create_pool,
            expected_default_pool=expected_pool)
        expected_lb = self._get_expected_lb([expected_listener])
        self.create_graph(expected_lb, [create_listener])

    def test_with_many_listeners_many_pools(self):
        create_pool1, expected_pool1 = self._get_pool_bodies()
        create_pool2, expected_pool2 = self._get_pool_bodies(name='pool2')
        create_listener1, expected_listener1 = self._get_listener_bodies(
            create_default_pool=create_pool1,
            expected_default_pool=expected_pool1)
        create_listener2, expected_listener2 = self._get_listener_bodies(
            name='listener2', protocol_port=81,
            create_default_pool=create_pool2,
            expected_default_pool=expected_pool2)
        expected_lb = self._get_expected_lb(
            [expected_listener1, expected_listener2])
        self.create_graph(
            expected_lb, [create_listener1, create_listener2])

    def test_with_one_listener_one_member(self):
        create_member, expected_member = self._get_member_bodies()
        create_pool, expected_pool = self._get_pool_bodies(
            create_members=[create_member],
            expected_members=[expected_member])
        create_listener, expected_listener = self._get_listener_bodies(
            create_default_pool=create_pool,
            expected_default_pool=expected_pool)
        expected_lb = self._get_expected_lb([expected_listener])
        self.create_graph(expected_lb, [create_listener])

    def test_with_one_listener_one_hm(self):
        create_hm, expected_hm = self._get_hm_bodies()
        create_pool, expected_pool = self._get_pool_bodies(
            create_hm=create_hm,
            expected_hm=expected_hm)
        create_listener, expected_listener = self._get_listener_bodies(
            create_default_pool=create_pool,
            expected_default_pool=expected_pool)
        expected_lb = self._get_expected_lb([expected_listener])
        self.create_graph(expected_lb, [create_listener])

    def test_with_one_of_everything(self):
        create_member, expected_member = self._get_member_bodies()
        create_hm, expected_hm = self._get_hm_bodies()
        create_pool, expected_pool = self._get_pool_bodies(
            create_members=[create_member],
            expected_members=[expected_member],
            create_hm=create_hm,
            expected_hm=expected_hm)
        create_r_member, expected_r_member = self._get_member_bodies(
            name='r_member1')
        create_r_hm, expected_r_hm = self._get_hm_bodies(name='r_hm1')
        create_r_pool, expected_r_pool = self._get_pool_bodies(
            create_members=[create_r_member],
            expected_members=[expected_r_member],
            create_hm=create_r_hm,
            expected_hm=expected_r_hm)
        create_rules, expected_rules = self._get_l7rules_bodes()
        create_l7_policies, expected_l7_policies = self._get_l7policies_bodies(
            create_rules=create_rules, expected_rules=expected_rules,
            create_r_pool=create_r_pool, expected_r_pool=expected_r_pool)
        create_listener, expected_listener = self._get_listener_bodies(
            create_default_pool=create_pool,
            expected_default_pool=expected_pool,
            create_l7_policies=create_l7_policies,
            expected_l7_policies=expected_l7_policies)
        expected_lb = self._get_expected_lb([expected_listener])
        self.create_graph(expected_lb, [create_listener])


class ListenerTestBase(LbaasPluginDbTestCase):
    def setUp(self):
        super(ListenerTestBase, self).setUp()
        network = self._make_network(self.fmt, 'test-net', True)
        self.test_subnet = self._make_subnet(
            self.fmt, network, gateway=n_constants.ATTR_NOT_SPECIFIED,
            cidr='10.0.0.0/24')
        self.test_subnet_id = self.test_subnet['subnet']['id']
        lb_res = self._create_loadbalancer(
            self.fmt, subnet_id=self.test_subnet_id)
        self.lb = self.deserialize(self.fmt, lb_res)
        self.lb_id = self.lb['loadbalancer']['id']
        self.addCleanup(self._delete_loadbalancer_api, self.lb_id)
        lb_res2 = self._create_loadbalancer(
            self.fmt, subnet_id=self.test_subnet_id)
        self.lb2 = self.deserialize(self.fmt, lb_res2)
        self.lb_id2 = self.lb2['loadbalancer']['id']

    def _create_listener_api(self, data):
        req = self.new_create_request("listeners", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_listener_api(self, listener_id, data):
        req = self.new_update_request_lbaas('listeners', data, listener_id)
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


class CertMock(cert_manager.Cert):
    def __init__(self, cert_container):
        pass

    def get_certificate(self):
        return "mock"

    def get_intermediates(self):
        return "mock"

    def get_private_key(self):
        return "mock"

    def get_private_key_passphrase(self):
        return "mock"


class Exceptions(object):
    def __iter__(self):
        return self
    pass


class LbaasListenerTests(ListenerTestBase):

    def test_create_listener(self, **extras):
        expected = {
            'protocol': 'HTTP',
            'protocol_port': 80,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'default_pool_id': None,
            'loadbalancers': [{'id': self.lb_id}]
        }

        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener'].get('id')
            self.assertTrue(listener_id)
            actual = {}
            for k, v in listener['listener'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, listener_id)
        return listener

    def test_create_listener_with_default_pool_no_lb(self, **extras):
        listener_pool_res = self._create_pool(
            self.fmt, lb_const.PROTOCOL_HTTP,
            lb_const.LB_METHOD_ROUND_ROBIN,
            loadbalancer_id=self.lb_id)
        listener_pool = self.deserialize(self.fmt, listener_pool_res)
        listener_pool_id = listener_pool['pool']['id']
        expected = {
            'protocol': 'HTTP',
            'protocol_port': 80,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'default_pool_id': listener_pool_id
        }

        expected.update(extras)

        with self.listener(default_pool_id=listener_pool_id) as listener:
            listener_id = listener['listener'].get('id')
            self.assertTrue(listener_id)
            actual = {}
            for k, v in listener['listener'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(actual, expected)
            self._validate_statuses(self.lb_id, listener_id)
        return listener

    def test_create_listener_same_port_same_load_balancer(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           protocol_port=80):
            self._create_listener(self.fmt, 'HTTP', 80,
                                  loadbalancer_id=self.lb_id,
                                  expected_res_status=409)

    def test_create_listener_with_tls_no_default_container(self, **extras):
        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': None,
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id,
        }

        listener_data.update(extras)
        self.assertRaises(
                        loadbalancerv2.TLSDefaultContainerNotSpecified,
                        self.plugin.create_listener,
                        context.get_admin_context(),
                        {'listener': listener_data})

    def test_create_listener_with_tls_missing_container(self, **extras):
        default_tls_container_ref = uuidutils.generate_uuid()

        class ReplaceClass(Exception):
            def __init__(self, status_code, message):
                self.status_code = status_code
                self.message = message

        cfg.CONF.set_override('service_name',
                              'lbaas',
                              'service_auth')
        cfg.CONF.set_override('region',
                              'RegionOne',
                              'service_auth')
        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }
        listener_data.update(extras)

        exc = ReplaceClass(status_code=404, message='Cert Not Found')

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                        'CERT_MANAGER_PLUGIN.CertManager.get_cert',
                        side_effect=exc), \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.delete_cert'):
            self.assertRaises(loadbalancerv2.TLSContainerNotFound,
                              self.plugin.create_listener,
                              context.get_admin_context(),
                              {'listener': listener_data})

    def test_create_listener_with_tls_invalid_service_acct(self, **extras):
        default_tls_container_ref = uuidutils.generate_uuid()
        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }
        listener_data.update(extras)

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                        'CERT_MANAGER_PLUGIN.CertManager.get_cert') as \
                get_cert_mock, \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.delete_cert'):
            get_cert_mock.side_effect = Exception('RandomFailure')

            self.assertRaises(loadbalancerv2.CertManagerError,
                              self.plugin.create_listener,
                              context.get_admin_context(),
                              {'listener': listener_data})

    def test_create_listener_with_tls_invalid_container(self, **extras):
        default_tls_container_ref = uuidutils.generate_uuid()
        cfg.CONF.set_override('service_name',
                              'lbaas',
                              'service_auth')
        cfg.CONF.set_override('region',
                              'RegionOne',
                              'service_auth')
        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }
        listener_data.update(extras)

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                        'cert_parser.validate_cert') as validate_cert_mock, \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.get_cert') as \
                get_cert_mock, \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.delete_cert') as \
                rm_consumer_mock:
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.side_effect = exceptions.MisMatchedKey

            self.assertRaises(loadbalancerv2.TLSContainerInvalid,
                              self.plugin.create_listener,
                              context.get_admin_context(),
                              {'listener': listener_data})
            rm_consumer_mock.assert_called_once_with(
                cert_ref=listener_data['default_tls_container_ref'],
                project_id=self._tenant_id,
                resource_ref=cert_manager.CertManager.get_service_url(
                    self.lb_id))

    def test_create_listener_with_tls(self, **extras):
        default_tls_container_ref = uuidutils.generate_uuid()
        sni_tls_container_ref_1 = uuidutils.generate_uuid()
        sni_tls_container_ref_2 = uuidutils.generate_uuid()

        expected = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [sni_tls_container_ref_1,
                                   sni_tls_container_ref_2]}

        extras['default_tls_container_ref'] = default_tls_container_ref
        extras['sni_container_refs'] = [sni_tls_container_ref_1,
                                        sni_tls_container_ref_2]

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                        'cert_parser.validate_cert') as validate_cert_mock, \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.get_cert') as \
                get_cert_mock:
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.start().return_value = True

            with self.listener(protocol=lb_const.PROTOCOL_TERMINATED_HTTPS,
                               loadbalancer_id=self.lb_id, protocol_port=443,
                               **extras) as listener:
                self.assertEqual(
                    expected,
                    dict((k, v)
                         for k, v in listener['listener'].items()
                         if k in expected)
                )

    def test_create_listener_loadbalancer_id_does_not_exist(self):
        self._create_listener(self.fmt, 'HTTP', 80,
                              loadbalancer_id=uuidutils.generate_uuid(),
                              expected_res_status=404)

    def test_can_create_listener_with_pool_loadbalancer_match(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet) as loadbalancer:
                lb_id = loadbalancer['loadbalancer']['id']
                with self.pool(loadbalancer_id=lb_id) as p1:
                    p_id = p1['pool']['id']
                    with self.listener(default_pool_id=p_id,
                                       loadbalancer_id=lb_id):
                        pass

    def test_cannot_create_listener_with_pool_loadbalancer_mismatch(self):
        with self.subnet() as subnet, \
                self.loadbalancer(subnet=subnet) as lb1, \
                self.loadbalancer(subnet=subnet) as lb2:
            lb_id1 = lb1['loadbalancer']['id']
            lb_id2 = lb2['loadbalancer']['id']
            with self.pool(loadbalancer_id=lb_id1) as p1:
                p_id = p1['pool']['id']
                data = {'listener': {'name': '',
                                     'protocol_port': 80,
                                     'protocol': 'HTTP',
                                     'connection_limit': 100,
                                     'admin_state_up': True,
                                     'tenant_id': self._tenant_id,
                                     'default_pool_id': p_id,
                                     'loadbalancer_id': lb_id2}}
                resp, body = self._create_listener_api(data)
                self.assertEqual(resp.status_int,
                                 webob.exc.HTTPBadRequest.code)

    def test_update_listener(self):
        name = 'new_listener'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': 100,
                           'admin_state_up': False,
                           'tenant_id': self._tenant_id,
                           'loadbalancers': [{'id': self.lb_id}]}

        with self.listener(name=name, loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            data = {'listener': {'name': name,
                                 'connection_limit': 100,
                                 'admin_state_up': False}}
            resp, body = self._update_listener_api(listener_id, data)
            for k in expected_values:
                self.assertEqual(expected_values[k], body['listener'][k])
            self._validate_statuses(self.lb_id, listener_id,
                                    listener_disabled=True)

    def test_update_listener_with_tls(self):
        default_tls_container_ref = uuidutils.generate_uuid()
        sni_tls_container_ref_1 = uuidutils.generate_uuid()
        sni_tls_container_ref_2 = uuidutils.generate_uuid()
        sni_tls_container_ref_3 = uuidutils.generate_uuid()
        sni_tls_container_ref_4 = uuidutils.generate_uuid()
        sni_tls_container_ref_5 = uuidutils.generate_uuid()

        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [sni_tls_container_ref_1,
                                   sni_tls_container_ref_2],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                        'cert_parser.validate_cert') as validate_cert_mock, \
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.get_cert') as \
                get_cert_mock:
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.start().return_value = True

            # Default container and two SNI containers
            # Test order and validation behavior.
            listener = self.plugin.create_listener(context.get_admin_context(),
                                                   {'listener': listener_data})
            self.assertEqual([sni_tls_container_ref_1,
                              sni_tls_container_ref_2],
                             listener['sni_container_refs'])

            # Default container and two other SNI containers
            # Test order and validation behavior.
            listener_data.pop('loadbalancer_id')
            listener_data.pop('protocol')
            listener_data.pop('provisioning_status')
            listener_data.pop('operating_status')
            listener_data['sni_container_refs'] = [sni_tls_container_ref_3,
                                                   sni_tls_container_ref_4]
            listener = self.plugin.update_listener(
                context.get_admin_context(),
                listener['id'],
                {'listener': listener_data}
            )
            self.assertEqual([sni_tls_container_ref_3,
                              sni_tls_container_ref_4],
                             listener['sni_container_refs'])

            # Default container, two old SNI containers ordered differently
            # and one new SNI container.
            # Test order and validation behavior.
            listener_data.pop('protocol')
            listener_data['sni_container_refs'] = [sni_tls_container_ref_4,
                                                   sni_tls_container_ref_3,
                                                   sni_tls_container_ref_5]
            listener = self.plugin.update_listener(context.get_admin_context(),
                                                   listener['id'],
                                                   {'listener': listener_data})
            self.assertEqual([sni_tls_container_ref_4,
                              sni_tls_container_ref_3,
                              sni_tls_container_ref_5],
                             listener['sni_container_refs'])

    def test_update_listener_with_empty_tls(self):
        default_tls_container_ref = uuidutils.generate_uuid()
        sni_tls_container_ref_1 = uuidutils.generate_uuid()
        sni_tls_container_ref_2 = uuidutils.generate_uuid()
        sni_tls_container_ref_3 = uuidutils.generate_uuid()
        sni_tls_container_ref_4 = uuidutils.generate_uuid()

        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [sni_tls_container_ref_1,
                                   sni_tls_container_ref_2],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'cert_parser.validate_cert') as validate_cert_mock,\
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.'
                           'get_cert') as get_cert_mock:
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.start().return_value = True

            # Default container and two SNI containers
            # Test order and validation behavior.
            listener = self.plugin.create_listener(
                context.get_admin_context(), {'listener': listener_data})
            expected = [sni_tls_container_ref_1, sni_tls_container_ref_2]
            self.assertEqual(expected, listener['sni_container_refs'])
            # Default container and two other SNI containers
            # Test order and validation behavior.
            listener_data.pop('loadbalancer_id')
            listener_data.pop('protocol')
            listener_data.pop('provisioning_status')
            listener_data.pop('operating_status')
            listener_data['sni_container_refs'] = [
                sni_tls_container_ref_3, sni_tls_container_ref_4]
            listener_data['default_tls_container_ref'] = ''
            listener = self.plugin.update_listener(
                context.get_admin_context(),
                listener['id'],
                {'listener': listener_data}
            )
            self.assertEqual('', listener['default_tls_container_ref'])

    def test_update_listener_without_sni_container_refs(self):
        default_tls_container_ref = uuidutils.generate_uuid()
        sni_tls_container_ref_1 = uuidutils.generate_uuid()
        sni_tls_container_ref_2 = uuidutils.generate_uuid()

        listener_data = {
            'protocol': lb_const.PROTOCOL_TERMINATED_HTTPS,
            'default_tls_container_ref': default_tls_container_ref,
            'sni_container_refs': [sni_tls_container_ref_1,
                                   sni_tls_container_ref_2],
            'protocol_port': 443,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'loadbalancer_id': self.lb_id
        }

        with mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'cert_parser.validate_cert') as validate_cert_mock,\
                mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                           'CERT_MANAGER_PLUGIN.CertManager.'
                           'get_cert') as get_cert_mock:
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.start().return_value = True

            # Default container and two SNI containers
            # Test order and validation behavior.
            listener = self.plugin.create_listener(
                context.get_admin_context(), {'listener': listener_data})
            expected = [sni_tls_container_ref_1, sni_tls_container_ref_2]
            self.assertEqual(expected, listener['sni_container_refs'])
            # No changes on default container and the containers list
            # Only update the listener name
            # Test getting info from current and validation behavior.
            updated_name = 'Updated Listener'
            listener_data = {'name': updated_name}
            listener = self.plugin.update_listener(
                context.get_admin_context(),
                listener['id'],
                {'listener': listener_data}
            )
            self.assertEqual(default_tls_container_ref,
                             listener['default_tls_container_ref'])
            self.assertEqual(expected, listener['sni_container_refs'])
            self.assertEqual(updated_name, listener['name'])

    def test_delete_listener(self):
        with self.listener(no_delete=True,
                           loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            resp = self._delete_listener_api(listener_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)
            resp, body = self._get_loadbalancer_api(self.lb_id)
            self.assertEqual(0, len(body['loadbalancer']['listeners']))

    def test_delete_listener_with_l7policy(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           no_delete=True) as listener:
            with self.l7policy(listener['listener']['id'], no_delete=True):
                ctx = context.get_admin_context()
                self.assertRaises(
                    loadbalancerv2.EntityInUse,
                    self.plugin.delete_listener,
                    ctx, listener['listener']['id'])

    def test_show_listener(self):
        name = 'show_listener'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': -1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'default_pool_id': None,
                           'loadbalancers': [{'id': self.lb_id}]}

        with self.listener(name=name, loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            resp, body = self._get_listener_api(listener_id)
            for k in expected_values:
                self.assertEqual(expected_values[k], body['listener'][k])

    def test_list_listeners(self):
        name = 'list_listeners'
        expected_values = {'name': name,
                           'protocol_port': 80,
                           'protocol': 'HTTP',
                           'connection_limit': -1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'loadbalancers': [{'id': self.lb_id}]}

        with self.listener(name=name, loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            expected_values['id'] = listener_id
            resp, body = self._list_listeners_api()
            listener_list = body['listeners']
            self.assertEqual(1, len(listener_list))
            for k in expected_values:
                self.assertEqual(expected_values[k], listener_list[0][k])

    def test_list_listeners_with_sort_emulated(self):
        with self.listener(name='listener1', protocol_port=81,
                           loadbalancer_id=self.lb_id) as listener1:
            with self.listener(name='listener2',
                               protocol_port=82,
                               loadbalancer_id=self.lb_id) as listener2:
                with self.listener(name='listener3',
                                   protocol_port=83,
                                   loadbalancer_id=self.lb_id) as listener3:
                    self._test_list_with_sort(
                        'listener',
                        (listener1, listener2, listener3),
                        [('protocol_port', 'asc'), ('name', 'desc')]
                    )

    def test_list_listeners_with_pagination_emulated(self):
        with self.listener(name='listener1', protocol_port=80,
                           loadbalancer_id=self.lb_id) as listener1:
            with self.listener(name='listener2', protocol_port=81,
                               loadbalancer_id=self.lb_id) as listener2:
                with self.listener(name='listener3', protocol_port=82,
                                   loadbalancer_id=self.lb_id) as listener3:
                    self._test_list_with_pagination(
                        'listener',
                        (listener1, listener2, listener3),
                        ('name', 'asc'), 2, 2
                    )

    def test_list_listeners_with_pagination_reverse_emulated(self):
        with self.listener(name='listener1', protocol_port=80,
                           loadbalancer_id=self.lb_id) as listener1:
            with self.listener(name='listener2', protocol_port=81,
                               loadbalancer_id=self.lb_id) as listener2:
                with self.listener(name='listener3', protocol_port=82,
                                   loadbalancer_id=self.lb_id) as listener3:
                    self._test_list_with_pagination(
                        'listener',
                        (listener3, listener2, listener1),
                        ('name', 'desc'), 2, 2
                    )


class LbaasL7Tests(ListenerTestBase):
    def test_create_l7policy_invalid_listener_id(self, **extras):
        self._create_l7policy(self.fmt, uuidutils.generate_uuid(),
                              lb_const.L7_POLICY_ACTION_REJECT,
                              expected_res_status=webob.exc.HTTPNotFound.code)

    def test_create_l7policy_redirect_no_pool(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'redirect_url': 'http://radware.com',
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            ctx = context.get_admin_context()
            l7policy_data['listener_id'] = listener['listener']['id']

            l7policy_data['action'] = (
                lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL)
            self.assertRaises(
                l7.L7PolicyRedirectPoolIdMissing,
                self.plugin.create_l7policy,
                ctx, {'l7policy': l7policy_data})

    def test_create_l7policy_redirect_invalid_pool(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            ctx = context.get_admin_context()
            l7policy_data['listener_id'] = listener['listener']['id']

            # Test pool redirect action with invalid pool id specified
            l7policy_data['redirect_pool_id'] = uuidutils.generate_uuid()
            self.assertRaises(
                loadbalancerv2.EntityNotFound,
                self.plugin.create_l7policy,
                ctx, {'l7policy': l7policy_data})

    def test_create_l7policy_redirect_foreign_pool(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            ctx = context.get_admin_context()
            l7policy_data['listener_id'] = listener['listener']['id']

            # Test pool redirect action with another loadbalancer pool id
            with self.pool(loadbalancer_id=self.lb_id2) as p:
                l7policy_data['redirect_pool_id'] = p['pool']['id']
                self.assertRaises(
                    sharedpools.ListenerAndPoolMustBeOnSameLoadbalancer,
                    self.plugin.create_l7policy,
                    ctx, {'l7policy': l7policy_data})

    def test_create_l7policy_redirect_no_url(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'redirect_url': 'http://radware.com',
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            ctx = context.get_admin_context()
            l7policy_data['listener_id'] = listener['listener']['id']

            # Test url redirect action without url specified
            del l7policy_data['redirect_url']
            l7policy_data['action'] = lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL
            self.assertRaises(
                l7.L7PolicyRedirectUrlMissing,
                self.plugin.create_l7policy,
                ctx, {'l7policy': l7policy_data})

    def test_create_l7policy_redirect_invalid_url(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'redirect_url': 'http://radware.com',
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            l7policy_data['listener_id'] = listener['listener']['id']

            # Test url redirect action with invalid url specified
            try:
                with self.l7policy(listener['listener']['id'],
                        action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
                        redirect_url='https:/acme.com'):
                    self.assertTrue(False)
            except webob.exc.HTTPClientError:
                pass

    def test_create_l7policy_invalid_position(self, **extras):
        l7policy_data = {
            'name': '',
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'description': '',
            'position': 1,
            'redirect_pool_id': None,
            'redirect_url': 'http://radware.com',
            'tenant_id': self._tenant_id,
            'admin_state_up': True,
        }
        l7policy_data.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            l7policy_data['listener_id'] = listener['listener']['id']

            # Test invalid zero position for policy
            try:
                with self.l7policy(listener['listener']['id'], position=0):
                    self.assertTrue(False)
            except webob.exc.HTTPClientError:
                pass

    def test_create_l7policy(self, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id) as p:
                expected['listener_id'] = listener_id
                actual = {}
                for k, v in p['l7policy'].items():
                    if k in expected:
                        actual[k] = v
                self.assertEqual(actual, expected)
                self._validate_statuses(self.lb_id, listener_id,
                                        p['l7policy']['id'])

    def test_create_l7policy_pool_redirect(self, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.pool(loadbalancer_id=self.lb_id) as pool:
                pool_id = pool['pool']['id']
                with self.l7policy(
                    listener_id,
                    action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                    redirect_pool_id=pool_id) as p:
                    expected['listener_id'] = listener_id
                    expected['redirect_pool_id'] = pool_id
                    actual = {}
                    for k, v in p['l7policy'].items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

    def test_l7policy_pool_deletion(self, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener1, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=8080) as listener2, \
                self.pool(loadbalancer_id=self.lb_id,
                          no_delete=True) as pool1, \
                self.pool(loadbalancer_id=self.lb_id) as pool2, \
                self.l7policy(listener1['listener']['id'],
                    action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                    redirect_pool_id=pool1['pool']['id']) as policy1, \
                self.l7policy(listener1['listener']['id'],
                    action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                    redirect_pool_id=pool2['pool']['id']), \
                self.l7policy(listener2['listener']['id'],
                    action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                    redirect_pool_id=pool1['pool']['id']) as policy3:
            ctx = context.get_admin_context()
            self.plugin.delete_pool(ctx, pool1['pool']['id'])

            l7policy1 = self.plugin.get_l7policy(
                ctx, policy1['l7policy']['id'])
            self.assertEqual(l7policy1['action'],
                lb_const.L7_POLICY_ACTION_REJECT)
            self.assertIsNone(l7policy1['redirect_pool_id'])

            l7policy3 = self.plugin.get_l7policy(
                ctx, policy3['l7policy']['id'])
            self.assertEqual(l7policy3['action'],
                lb_const.L7_POLICY_ACTION_REJECT)
            self.assertIsNone(l7policy3['redirect_pool_id'])

    def test_create_l7policies_ordering(self, **extras):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="1"), \
                    self.l7policy(listener_id, name="2"), \
                    self.l7policy(listener_id, name="3"), \
                    self.l7policy(listener_id, position=1, name="4"), \
                    self.l7policy(listener_id, position=2, name="5"), \
                    self.l7policy(listener_id, position=4, name="6"), \
                    self.l7policy(listener_id, name="7"), \
                    self.l7policy(listener_id, position=8, name="8"), \
                    self.l7policy(listener_id, position=1, name="9"), \
                    self.l7policy(listener_id, position=1, name="10"):
                c = context.get_admin_context()
                listener_db = self.plugin.db._get_resource(
                    c,
                    models.Listener, listener['listener']['id'])
                names = ['10', '9', '4', '5', '1', '6', '2', '3', '7', '8']
                for pos in range(0, 10):
                    self.assertEqual(
                        listener_db.l7_policies[pos]['position'], pos + 1)
                    self.assertEqual(
                        listener_db.l7_policies[pos]['name'], names[pos])

    def test_update_l7policy(self, **extras):
        expected = {
            'admin_state_up': False,
            'action': lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'redirect_pool_id': None,
            'redirect_url': 'redirect_url',
            'tenant_id': self._tenant_id,
            'position': 1,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id) as p:
                l7policy_id = p['l7policy']['id']

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
                self._validate_statuses(self.lb_id, listener_id,
                                        p['l7policy']['id'],
                                        l7policy_disabled=True)

    def test_update_l7policies_ordering(self, **extras):
        expected = {
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': '',
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="1") as p1, \
                    self.l7policy(listener_id, name="2") as p2, \
                    self.l7policy(listener_id, name="3"), \
                    self.l7policy(listener_id, name="4"), \
                    self.l7policy(listener_id, name="5") as p5, \
                    self.l7policy(listener_id, name="6") as p6, \
                    self.l7policy(listener_id, name="7"), \
                    self.l7policy(listener_id, name="8"), \
                    self.l7policy(listener_id, name="9"), \
                    self.l7policy(listener_id, name="10") as p10:
                c = context.get_admin_context()

                listener_db = self.plugin.db._get_resource(
                    context.get_admin_context(),
                    models.Listener, listener['listener']['id'])

                expected['position'] = 1
                self.plugin.db.update_status(
                    c, models.L7Policy, p2['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p2['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 3
                self.plugin.db.update_status(
                    c, models.L7Policy, p1['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p1['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 4
                self.plugin.db.update_status(
                    c, models.L7Policy, p6['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p6['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 11
                self.plugin.db.update_status(
                    c, models.L7Policy, p2['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p2['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 1
                self.plugin.db.update_status(
                    c, models.L7Policy, p1['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p1['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 8
                self.plugin.db.update_status(
                    c, models.L7Policy, p5['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p5['l7policy']['id'],
                                            {'l7policy': expected})
                expected['position'] = 3
                self.plugin.db.update_status(
                    c, models.L7Policy, p10['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.update_l7policy(c, p10['l7policy']['id'],
                                            {'l7policy': expected})

                c2 = context.get_admin_context()
                listener_db = self.plugin.db._get_resource(
                    c2,
                    models.Listener, listener['listener']['id'])
                names = ['1', '3', '10', '6', '4', '7', '8', '9', '5', '2']
                for pos in range(0, 10):
                    self.assertEqual(
                        listener_db.l7_policies[pos]['position'], pos + 1)
                    self.assertEqual(
                        listener_db.l7_policies[pos]['name'], names[pos])

    def test_delete_l7policy(self, **extras):
        expected = {
            'position': 1,
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': '',
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="0"), \
                    self.l7policy(listener_id, name="1"), \
                    self.l7policy(listener_id, name="2"), \
                    self.l7policy(listener_id, name="3",
                                  no_delete=True) as p3, \
                    self.l7policy(listener_id, name="4"), \
                    self.l7policy(listener_id, name="5",
                                  no_delete=True) as p5, \
                    self.l7policy(listener_id, name="6"):
                c = context.get_admin_context()

                self.plugin.db.update_status(
                    c, models.L7Policy, p3['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.delete_l7policy(c, p3['l7policy']['id'])
                self.plugin.db.update_status(
                    c, models.L7Policy, p5['l7policy']['id'],
                    lb_const.OFFLINE)
                self.plugin.delete_l7policy(c, p5['l7policy']['id'])

                c2 = context.get_admin_context()
                listener_db = self.plugin.db._get_resource(
                    c2,
                    models.Listener, listener['listener']['id'])
                names = ['0', '1', '2', '4', '6']
                for pos in range(0, 4):
                    self.assertEqual(
                        listener_db.l7_policies[pos]['position'], pos + 1)
                    self.assertEqual(
                        listener_db.l7_policies[pos]['name'], names[pos])

                self.assertRaises(
                    loadbalancerv2.EntityNotFound,
                    self.plugin.get_l7policy,
                    c, p3['l7policy']['id'])
                self.assertRaises(
                    loadbalancerv2.EntityNotFound,
                    self.plugin.get_l7policy,
                    c, p5['l7policy']['id'])

    def test_show_l7policy(self, **extras):
        expected = {
            'position': 1,
            'action': lb_const.L7_POLICY_ACTION_REJECT,
            'redirect_pool_id': None,
            'redirect_url': None,
            'tenant_id': self._tenant_id,
        }
        expected.update(extras)

        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            expected['listener_id'] = listener_id
            with self.l7policy(listener_id, name="0") as p:
                req = self.new_show_request('l7policies',
                                            p['l7policy']['id'],
                                            fmt=self.fmt)
                res = self.deserialize(self.fmt,
                                       req.get_response(self.ext_api))
                actual = {}
                for k, v in res['l7policy'].items():
                    if k in expected:
                        actual[k] = v
                self.assertEqual(expected, actual)
            return p

    def test_list_l7policies_with_sort_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="b") as p1, \
                    self.l7policy(listener_id, name="c") as p2, \
                    self.l7policy(listener_id, name="a") as p3:
                self._test_list_with_sort('l7policy', (p3, p1, p2),
                                          [('name', 'asc')],
                                          resources='l7policies')

    def test_list_l7policies_with_pagination_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="b") as p1, \
                    self.l7policy(listener_id, name="c") as p2, \
                    self.l7policy(listener_id, name="e") as p3, \
                    self.l7policy(listener_id, name="d") as p4, \
                    self.l7policy(listener_id, name="f") as p5, \
                    self.l7policy(listener_id, name="g") as p6, \
                    self.l7policy(listener_id, name="a") as p7:
                self._test_list_with_pagination(
                    'l7policy', (p6, p5, p3, p4, p2, p1, p7),
                    ('name', 'desc'), 2, 4, resources='l7policies')

    def test_list_l7policies_with_pagination_reverse_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id, name="b") as p1, \
                    self.l7policy(listener_id, name="c") as p2, \
                    self.l7policy(listener_id, name="e") as p3, \
                    self.l7policy(listener_id, name="d") as p4, \
                    self.l7policy(listener_id, name="f") as p5, \
                    self.l7policy(listener_id, name="g") as p6, \
                    self.l7policy(listener_id, name="a") as p7:
                self._test_list_with_pagination_reverse(
                    'l7policy', (p6, p5, p3, p4, p2, p1, p7),
                    ('name', 'desc'), 2, 4, resources='l7policies')

    def test_create_l7rule_invalid_policy_id(self, **extras):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']):
                self._create_l7policy_rule(
                    self.fmt, uuidutils.generate_uuid(),
                    lb_const.L7_RULE_TYPE_HOST_NAME,
                    lb_const.L7_RULE_COMPARE_TYPE_REGEX,
                    'value',
                    expected_res_status=webob.exc.HTTPNotFound.code)

    def test_create_invalid_l7rule(self, **extras):
        rule = {
            'type': lb_const.L7_RULE_TYPE_HEADER,
            'compare_type': lb_const.L7_RULE_COMPARE_TYPE_REGEX,
            'value': '*'
        }
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']) as policy:
                policy_id = policy['l7policy']['id']
                ctx = context.get_admin_context()

                # test invalid regex
                self.assertRaises(
                    l7.L7RuleInvalidRegex,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test missing key for HEADER type
                rule['value'] = '/*/'
                self.assertRaises(
                    l7.L7RuleKeyMissing,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test missing key for COOKIE type
                rule['type'] = lb_const.L7_RULE_TYPE_COOKIE
                self.assertRaises(
                    l7.L7RuleKeyMissing,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test invalid key for HEADER type
                rule['type'] = lb_const.L7_RULE_TYPE_HEADER
                rule['key'] = '/'
                self.assertRaises(
                    l7.L7RuleInvalidKey,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test invalid value for COOKIE type
                rule['compare_type'] =\
                    lb_const.L7_RULE_COMPARE_TYPE_CONTAINS
                rule['type'] = lb_const.L7_RULE_TYPE_COOKIE
                rule['key'] = 'a'
                rule['value'] = ';'
                self.assertRaises(
                    l7.L7RuleInvalidCookieValue,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test invalid value for !COOKIE type
                rule['type'] = lb_const.L7_RULE_TYPE_PATH
                rule['value'] = '	'
                self.assertRaises(
                    l7.L7RuleInvalidHeaderValue,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test invalid value for !COOKIE type quated
                rule['value'] = '  '
                self.assertRaises(
                    l7.L7RuleInvalidHeaderValue,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

                # test unsupported compare type for FILE type
                rule['type'] = lb_const.L7_RULE_TYPE_FILE_TYPE
                self.assertRaises(
                    l7.L7RuleUnsupportedCompareType,
                    self.plugin.db.create_l7policy_rule,
                    ctx, rule, policy_id)

    def test_create_l7rule(self, **extras):
        expected = {
            'type': lb_const.L7_RULE_TYPE_HOST_NAME,
            'compare_type': lb_const.L7_RULE_COMPARE_TYPE_EQUAL_TO,
            'key': None,
            'value': 'value1'
        }
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id) as r_def, \
                        self.l7policy_rule(policy_id,
                                           key='key1') as r_key, \
                        self.l7policy_rule(policy_id,
                                           value='value2') as r_value, \
                        self.l7policy_rule(policy_id,
                            type=lb_const.L7_RULE_TYPE_PATH) as r_type, \
                        self.l7policy_rule(policy_id, compare_type=lb_const.
                            L7_RULE_COMPARE_TYPE_REGEX) as r_compare_type, \
                        self.l7policy_rule(policy_id,
                                           invert=True) as r_invert:
                    ctx = context.get_admin_context()
                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_def['rule']['id'], policy_id)
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_key['rule']['id'], policy_id)
                    expected['key'] = 'key1'
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_value['rule']['id'], policy_id)
                    expected['key'] = None
                    expected['value'] = 'value2'
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_type['rule']['id'], policy_id)
                    expected['value'] = 'value1'
                    expected['type'] = lb_const.L7_RULE_TYPE_PATH
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_compare_type['rule']['id'], policy_id)
                    expected['type'] = lb_const.L7_RULE_TYPE_HOST_NAME
                    expected['compare_type'] =\
                        lb_const.L7_RULE_COMPARE_TYPE_REGEX
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

                    rdb = self.plugin.get_l7policy_rule(
                        ctx, r_invert['rule']['id'], policy_id)
                    expected['invert'] = True
                    expected['compare_type'] =\
                        lb_const.L7_RULE_COMPARE_TYPE_EQUAL_TO
                    actual = {}
                    for k, v in rdb.items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)

    def test_invalid_update_l7rule(self, **extras):
        rule = {
            'type': lb_const.L7_RULE_TYPE_HEADER,
            'compare_type': lb_const.L7_RULE_COMPARE_TYPE_REGEX,
            'value': '*'
        }
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id) as r:
                    rule_id = r['rule']['id']
                    ctx = context.get_admin_context()

                    # test invalid regex
                    self.assertRaises(
                        l7.L7RuleInvalidRegex,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test missing key for HEADER type
                    rule['value'] = '/*/'
                    self.assertRaises(
                        l7.L7RuleKeyMissing,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test missing key for COOKIE type
                    rule['type'] = lb_const.L7_RULE_TYPE_COOKIE
                    self.assertRaises(
                        l7.L7RuleKeyMissing,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test invalid key for HEADER type
                    rule['type'] = lb_const.L7_RULE_TYPE_HEADER
                    rule['key'] = '/'
                    self.assertRaises(
                        l7.L7RuleInvalidKey,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test invalid value for COOKIE type
                    rule['compare_type'] =\
                        lb_const.L7_RULE_COMPARE_TYPE_CONTAINS
                    rule['type'] = lb_const.L7_RULE_TYPE_COOKIE
                    rule['key'] = 'a'
                    rule['value'] = ';'
                    self.assertRaises(
                        l7.L7RuleInvalidCookieValue,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test invalid value for !COOKIE type
                    rule['type'] = lb_const.L7_RULE_TYPE_PATH
                    rule['value'] = '	'
                    self.assertRaises(
                        l7.L7RuleInvalidHeaderValue,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test invalid value for !COOKIE type quated
                    rule['value'] = '  '
                    self.assertRaises(
                        l7.L7RuleInvalidHeaderValue,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

                    # test unsupported compare type for FILE type
                    rule['type'] = lb_const.L7_RULE_TYPE_FILE_TYPE
                    self.assertRaises(
                        l7.L7RuleUnsupportedCompareType,
                        self.plugin.db.update_l7policy_rule,
                        ctx, rule_id, rule, policy_id)

    def test_update_l7rule(self, **extras):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id) as r:
                    req = self.new_show_request('l7policies',
                                                policy_id,
                                                fmt=self.fmt)
                    policy_show = self.deserialize(
                        self.fmt,
                        req.get_response(self.ext_api)
                    )
                    self.assertEqual(
                        len(policy_show['l7policy']['rules']), 1)

                    expected = {}
                    expected['type'] = lb_const.L7_RULE_TYPE_HEADER
                    expected['compare_type'] = (
                        lb_const.L7_RULE_COMPARE_TYPE_REGEX)
                    expected['value'] = '/.*/'
                    expected['key'] = 'HEADER1'
                    expected['invert'] = True
                    expected['admin_state_up'] = False

                    req = self.new_update_request_lbaas(
                        'l7policies', {'rule': expected},
                        policy_id, subresource='rules',
                        sub_id=r['rule']['id'])
                    res = self.deserialize(
                        self.fmt,
                        req.get_response(self.ext_api)
                    )
                    actual = {}
                    for k, v in res['rule'].items():
                        if k in expected:
                            actual[k] = v
                    self.assertEqual(actual, expected)
                    self._validate_statuses(self.lb_id,
                                            listener['listener']['id'],
                                            policy_id, r['rule']['id'],
                                            l7rule_disabled=True)

    def test_delete_l7rule(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            with self.l7policy(listener['listener']['id']) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id, no_delete=True) as r0, \
                        self.l7policy_rule(policy_id, no_delete=True):
                    req = self.new_show_request('l7policies',
                                                policy_id,
                                                fmt=self.fmt)
                    policy_update = self.deserialize(
                        self.fmt,
                        req.get_response(self.ext_api)
                    )
                    self.assertEqual(
                        len(policy_update['l7policy']['rules']), 2)

                    req = self.new_delete_request('l7policies',
                                                  policy_id,
                                                  subresource='rules',
                                                  sub_id=r0['rule']['id'])
                    res = req.get_response(self.ext_api)
                    self.assertEqual(res.status_int,
                                     webob.exc.HTTPNoContent.code)

                    req = self.new_show_request('l7policies',
                                                policy_id,
                                                fmt=self.fmt)
                    policy_update = self.deserialize(
                        self.fmt,
                        req.get_response(self.ext_api)
                    )
                    self.assertEqual(
                        len(policy_update['l7policy']['rules']), 1)

    def test_list_l7rules_with_sort_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id, value="b") as r1, \
                        self.l7policy_rule(policy_id, value="c") as r2, \
                        self.l7policy_rule(policy_id, value="a") as r3:
                    self._test_list_with_sort('l7policy', (r3, r1, r2),
                                              [('value', 'asc')],
                                              id=policy_id,
                                              resources='l7policies',
                                              subresource='rule',
                                              subresources='rules')

    def test_list_l7rules_with_pagination_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id) as policy:
                policy_id = policy['l7policy']['id']
                with self.l7policy_rule(policy_id, value="b") as r1, \
                        self.l7policy_rule(policy_id, value="c") as r2, \
                        self.l7policy_rule(policy_id, value="e") as r3, \
                        self.l7policy_rule(policy_id, value="d") as r4, \
                        self.l7policy_rule(policy_id, value="f") as r5, \
                        self.l7policy_rule(policy_id, value="g") as r6, \
                        self.l7policy_rule(policy_id, value="a") as r7:
                    self._test_list_with_pagination(
                        'l7policy', (r6, r5, r3, r4, r2, r1, r7),
                        ('value', 'desc'), 2, 4,
                        id=policy_id,
                        resources='l7policies',
                        subresource='rule',
                        subresources='rules')

    def test_list_l7rules_with_pagination_reverse_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            with self.l7policy(listener_id) as p:
                policy_id = p['l7policy']['id']
                with self.l7policy_rule(policy_id, value="b") as r1, \
                        self.l7policy_rule(policy_id, value="c") as r2, \
                        self.l7policy_rule(policy_id, value="e") as r3, \
                        self.l7policy_rule(policy_id, value="d") as r4, \
                        self.l7policy_rule(policy_id, value="f") as r5, \
                        self.l7policy_rule(policy_id, value="g") as r6, \
                        self.l7policy_rule(policy_id, value="a") as r7:
                    self._test_list_with_pagination_reverse(
                        'l7policy', (r6, r5, r3, r4, r2, r1, r7),
                        ('value', 'desc'), 2, 4,
                        id=policy_id,
                        resources='l7policies',
                        subresource='rule',
                        subresources='rules')


class PoolTestBase(ListenerTestBase):

    def setUp(self):
        super(PoolTestBase, self).setUp()
        listener_res = self._create_listener(self.fmt, lb_const.PROTOCOL_HTTP,
                                             80, self.lb_id)
        self.def_listener = self.deserialize(self.fmt, listener_res)
        self.listener_id = self.def_listener['listener']['id']
        self.addCleanup(self._delete_listener_api, self.listener_id)
        listener_res2 = self._create_listener(self.fmt, lb_const.PROTOCOL_HTTP,
                                              80, self.lb_id2)
        self.def_listener2 = self.deserialize(self.fmt, listener_res2)
        self.listener_id2 = self.def_listener2['listener']['id']
        self.loadbalancer_id = self.lb_id
        self.loadbalancer_id2 = self.lb_id2

    def _create_pool_api(self, data):
        req = self.new_create_request("pools", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_pool_api(self, pool_id, data):
        req = self.new_update_request_lbaas('pools', data, pool_id)
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

    def test_create_pool(self, **extras):
        expected = {
            'name': '',
            'description': '',
            'protocol': 'HTTP',
            'lb_algorithm': 'ROUND_ROBIN',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'healthmonitor_id': None,
            'members': []
        }

        expected.update(extras)

        with self.pool(listener_id=self.listener_id, **extras) as pool:
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
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=pool_id)
        return pool

    def test_create_pool_with_loadbalancer_no_listener(self, **extras):
        expected = {
            'name': '',
            'description': '',
            'protocol': 'HTTP',
            'lb_algorithm': 'ROUND_ROBIN',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'healthmonitor_id': None,
            'members': []
        }

        expected.update(extras)

        with self.pool(loadbalancer_id=self.loadbalancer_id, **extras) as pool:
            pool_id = pool['pool'].get('id')
            if 'session_persistence' in expected:
                if not expected['session_persistence'].get('cookie_name'):
                    expected['session_persistence']['cookie_name'] = None
            self.assertTrue(pool_id)

            actual = {}
            for k, v in pool['pool'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, None, pool_id=pool_id)
        return pool

    def test_show_pool(self, **extras):
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

        with self.pool(listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            resp, body = self._get_pool_api(pool_id)
            actual = {}
            for k, v in body['pool'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
        return pool

    def test_update_pool(self, **extras):
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

        with self.pool(listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            self.assertTrue(pool_id)
            data = {'pool': {'lb_algorithm': 'LEAST_CONNECTIONS'}}
            resp, body = self._update_pool_api(pool_id, data)
            actual = {}
            for k, v in body['pool'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=pool_id)

        return pool

    def test_delete_pool(self):
        with self.pool(no_delete=True, listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            ctx = context.get_admin_context()
            qry = ctx.session.query(models.PoolV2)
            qry = qry.filter_by(id=pool_id)
            self.assertIsNotNone(qry.first())

            resp = self._delete_pool_api(pool_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)
            qry = ctx.session.query(models.PoolV2)
            qry = qry.filter_by(id=pool['pool']['id'])
            self.assertIsNone(qry.first())

    def test_delete_pool_and_members(self):
        with self.pool(listener_id=self.listener_id, no_delete=True) as pool:
            pool_id = pool['pool']['id']
            with self.member(pool_id=pool_id, no_delete=True) as member:
                member_id = member['member']['id']
                ctx = context.get_admin_context()
                # this will only set status, it requires driver to delete
                # from db.  Since the LoggingNoopDriver is being used it
                # should delete from db
                self.plugin.delete_pool(ctx, pool_id)
                # verify member got deleted as well
                self.assertRaises(
                    loadbalancerv2.EntityNotFound,
                    self.plugin.db.get_pool_member,
                    ctx, member_id)

    def test_delete_pool_and_hm(self):
        with self.pool(listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            with self.healthmonitor(pool_id=pool_id):
                # verify pool deletion is prevented if HM is associated
                ctx = context.get_admin_context()
                self.assertRaises(
                    loadbalancerv2.EntityInUse,
                    self.plugin.delete_pool,
                    ctx, pool_id)

    def test_cannot_add_multiple_pools_to_listener(self):
        with self.pool(listener_id=self.listener_id):
            data = {'pool': {'name': '',
                             'description': '',
                             'protocol': 'HTTP',
                             'lb_algorithm': 'ROUND_ROBIN',
                             'admin_state_up': True,
                             'tenant_id': self._tenant_id,
                             'listener_id': self.listener_id}}
            resp, body = self._create_pool_api(data)
            self.assertEqual(webob.exc.HTTPConflict.code, resp.status_int)

    def test_create_pool_with_pool_protocol_mismatch(self):
        with self.listener(protocol=lb_const.PROTOCOL_HTTPS,
                           loadbalancer_id=self.lb_id,
                           protocol_port=443) as listener:
            listener_id = listener['listener']['id']
            data = {'pool': {'listener_id': listener_id,
                             'protocol': lb_const.PROTOCOL_HTTP,
                             'lb_algorithm': lb_const.LB_METHOD_ROUND_ROBIN,
                             'tenant_id': self._tenant_id}}
            resp, body = self._create_pool_api(data)
            self.assertEqual(webob.exc.HTTPConflict.code, resp.status_int)

    def test_cannot_create_pool_with_listener_protocol_incompatible(self):
        with self.listener(protocol=lb_const.PROTOCOL_TCP,
                           loadbalancer_id=self.lb_id,
                           protocol_port=8000) as listener:
            listener_id = listener['listener']['id']
            data = {'pool': {'listener_id': listener_id,
                             'protocol': lb_const.PROTOCOL_HTTP,
                             'lb_algorithm': lb_const.LB_METHOD_ROUND_ROBIN,
                             'admin_state_up': True,
                             'tenant_id': self._tenant_id}}
            self.assertRaises(
                loadbalancerv2.ListenerPoolProtocolMismatch,
                self.plugin.create_pool,
                context.get_admin_context(),
                data)

    def test_create_pool_with_protocol_invalid(self):
        data = {'pool': {
            'name': '',
            'description': '',
            'protocol': 'BLANK',
            'lb_algorithm': 'LEAST_CONNECTIONS',
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }}
        resp, body = self._create_pool_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_can_create_pool_with_listener_loadbalancer_match(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet) as loadbalancer:
                lb_id = loadbalancer['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id) as l1:
                    l_id = l1['listener']['id']
                    with self.pool(listener_id=l_id,
                                   loadbalancer_id=lb_id):
                        pass

    def test_cannot_create_pool_with_listener_loadbalancer_mismatch(self):
        with self.subnet() as subnet:
            with self.loadbalancer(subnet=subnet) as lb1, \
                    self.loadbalancer(subnet=subnet) as lb2:
                lb_id1 = lb1['loadbalancer']['id']
                lb_id2 = lb2['loadbalancer']['id']
                with self.listener(loadbalancer_id=lb_id1) as l1:
                    l_id = l1['listener']['id']
                    data = {'pool': {'name': '',
                                     'description': '',
                                     'protocol': 'HTTP',
                                     'lb_algorithm': 'ROUND_ROBIN',
                                     'admin_state_up': True,
                                     'tenant_id': self._tenant_id,
                                     'listener_id': l_id,
                                     'loadbalancer_id': lb_id2}}
                    resp, body = self._create_pool_api(data)
                    self.assertEqual(resp.status_int,
                                     webob.exc.HTTPBadRequest.code)

    def test_create_pool_with_session_persistence(self):
        self.test_create_pool(session_persistence={'type': 'HTTP_COOKIE'})

    def test_create_pool_with_session_persistence_none(self):
        self.test_create_pool(session_persistence=None)

    def test_create_pool_with_session_persistence_with_app_cookie(self):
        sp = {'type': 'APP_COOKIE', 'cookie_name': 'sessionId'}
        self.test_create_pool(session_persistence=sp)

    def test_create_pool_with_session_persistence_unsupported_type(self):
        with testtools.ExpectedException(webob.exc.HTTPClientError):
            self.test_create_pool(session_persistence={'type': 'UNSUPPORTED'})

    def test_create_pool_with_unnecessary_cookie_name(self):
        sp = {'type': "SOURCE_IP", 'cookie_name': 'sessionId'}
        with testtools.ExpectedException(webob.exc.HTTPClientError):
            self.test_create_pool(session_persistence=sp)

    def test_create_pool_with_session_persistence_without_cookie_name(self):
        sp = {'type': "APP_COOKIE"}
        with testtools.ExpectedException(webob.exc.HTTPClientError):
            self.test_create_pool(session_persistence=sp)

    def test_validate_session_persistence_valid_with_cookie_name(self):
        sp = {'type': 'APP_COOKIE', 'cookie_name': 'MyCookie'}
        self.assertIsNone(
            self.plugin._validate_session_persistence_info(sp_info=sp))

    def test_validate_session_persistence_invalid_with_cookie_name(self):
        sp = {'type': 'HTTP', 'cookie_name': 'MyCookie'}
        with testtools.ExpectedException(
                loadbalancerv2.SessionPersistenceConfigurationInvalid):
            self.plugin._validate_session_persistence_info(sp_info=sp)

    def test_validate_session_persistence_invalid_without_cookie_name(self):
        sp = {'type': 'APP_COOKIE'}
        with testtools.ExpectedException(
                loadbalancerv2.SessionPersistenceConfigurationInvalid):
            self.plugin._validate_session_persistence_info(sp_info=sp)

    def test_reset_session_persistence(self):
        name = 'pool4'
        sp = {'type': "HTTP_COOKIE"}

        update_info = {'pool': {'session_persistence': None}}

        with self.pool(name=name, session_persistence=sp,
                       listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            sp['cookie_name'] = None
            # Ensure that pool has been created properly
            self.assertEqual(pool['pool']['session_persistence'],
                             sp)

            # Try resetting session_persistence
            resp, body = self._update_pool_api(pool_id, update_info)

            self.assertIsNone(body['pool'].get('session_persistence'))

    def test_update_no_change_session_persistence(self):
        name = 'pool4'
        sp = {'type': "HTTP_COOKIE"}

        update_info = {'pool': {'lb_algorithm': 'ROUND_ROBIN'}}

        with self.pool(name=name, session_persistence=sp,
                       listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            sp['cookie_name'] = None
            # Ensure that pool has been created properly
            self.assertEqual(pool['pool']['session_persistence'],
                             sp)

            # Try updating something other than session_persistence
            resp, body = self._update_pool_api(pool_id, update_info)
            # Make sure session_persistence is unchanged
            self.assertEqual(pool['pool']['session_persistence'],
                             sp)

    def test_update_pool_with_protocol(self):
        with self.pool(listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            data = {'pool': {'protocol': 'BLANK'}}
            resp, body = self._update_pool_api(pool_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_list_pools(self):
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

        with self.pool(name=name, listener_id=self.listener_id,
                       description='apool',
                       session_persistence={'type': 'HTTP_COOKIE'},
                       members=[]) as pool:
            pool_id = pool['pool']['id']
            expected_values['id'] = pool_id
            resp, body = self._list_pools_api()
            pool_list = body['pools']
            self.assertEqual(1, len(pool_list))
            for k in expected_values:
                self.assertEqual(expected_values[k], pool_list[0][k])

    def test_list_pools_with_sort_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           protocol_port=81,
                           protocol=lb_const.PROTOCOL_HTTPS) as l1, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=82,
                              protocol=lb_const.PROTOCOL_TCP) as l2, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=83,
                              protocol=lb_const.PROTOCOL_HTTP) as l3, \
                self.pool(listener_id=l1['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTPS) as p1, \
                self.pool(listener_id=l2['listener']['id'],
                          protocol=lb_const.PROTOCOL_TCP) as p2, \
                self.pool(listener_id=l3['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTP) as p3:
            self._test_list_with_sort('pool', (p2, p1, p3),
                                      [('protocol', 'desc')])

    def test_list_pools_with_pagination_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           protocol_port=81,
                           protocol=lb_const.PROTOCOL_HTTPS) as l1, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=82,
                              protocol=lb_const.PROTOCOL_TCP) as l2, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=83,
                              protocol=lb_const.PROTOCOL_HTTP) as l3, \
                self.pool(listener_id=l1['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTPS) as p1, \
                self.pool(listener_id=l2['listener']['id'],
                          protocol=lb_const.PROTOCOL_TCP) as p2, \
                self.pool(listener_id=l3['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTP) as p3:
            self._test_list_with_pagination('pool',
                                            (p3, p1, p2),
                                            ('protocol', 'asc'), 2, 2)

    def test_list_pools_with_pagination_reverse_emulated(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           protocol_port=81,
                           protocol=lb_const.PROTOCOL_HTTPS) as l1, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=82,
                              protocol=lb_const.PROTOCOL_TCP) as l2, \
                self.listener(loadbalancer_id=self.lb_id,
                              protocol_port=83,
                              protocol=lb_const.PROTOCOL_HTTP) as l3, \
                self.pool(listener_id=l1['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTPS) as p1, \
                self.pool(listener_id=l2['listener']['id'],
                          protocol=lb_const.PROTOCOL_TCP) as p2, \
                self.pool(listener_id=l3['listener']['id'],
                          protocol=lb_const.PROTOCOL_HTTP) as p3:
            self._test_list_with_pagination_reverse('pool',
                                                    (p3, p1, p2),
                                                    ('protocol', 'asc'),
                                                    2, 2)

    def test_get_listener_shows_default_pool(self):
        with self.pool(listener_id=self.listener_id) as pool:
            pool_id = pool['pool']['id']
            resp, body = self._get_listener_api(self.listener_id)
            self.assertEqual(pool_id, body['listener']['default_pool_id'])


class MemberTestBase(PoolTestBase):
    def setUp(self):
        super(MemberTestBase, self).setUp()
        pool_res = self._create_pool(
            self.fmt, lb_const.PROTOCOL_HTTP,
            lb_const.LB_METHOD_ROUND_ROBIN,
            self.listener_id,
            self.lb_id,
            session_persistence={'type':
                                 lb_const.SESSION_PERSISTENCE_HTTP_COOKIE})
        self.pool = self.deserialize(self.fmt, pool_res)
        self.pool_id = self.pool['pool']['id']

        alt_listener_res = self._create_listener(
            self.fmt, lb_const.PROTOCOL_HTTP,
            self.def_listener['listener']['protocol_port'] + 1,
            self.lb_id
        )
        self.alt_listener = self.deserialize(self.fmt, alt_listener_res)
        self.alt_listener_id = self.alt_listener['listener']['id']
        alt_pool_res = self._create_pool(
            self.fmt, lb_const.PROTOCOL_HTTP,
            lb_const.LB_METHOD_ROUND_ROBIN,
            self.alt_listener_id,
            session_persistence={'type':
                                 lb_const.SESSION_PERSISTENCE_HTTP_COOKIE})
        self.alt_pool = self.deserialize(self.fmt, alt_pool_res)
        self.alt_pool_id = self.alt_pool['pool']['id']

    def tearDown(self):
        self._delete('pools', self.alt_pool_id)
        self._delete('pools', self.pool_id)
        super(MemberTestBase, self).tearDown()

    def _create_member_api(self, pool_id, data):
        req = self.new_create_request("pools", data, self.fmt, id=pool_id,
                                      subresource='members')
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_member_api(self, pool_id, member_id, data):
        req = self.new_update_request_lbaas(
            'pools', data, pool_id, subresource='members', sub_id=member_id)
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

    def test_create_member(self, **extras):
        expected = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'subnet_id': '',
            'name': 'member1'
        }

        expected.update(extras)

        expected['subnet_id'] = self.test_subnet_id
        with self.member(pool_id=self.pool_id, name='member1') as member:
            member_id = member['member'].get('id')
            self.assertTrue(member_id)

            actual = {}
            for k, v in member['member'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id,
                                    member_id=member_id)
        return member

    def test_create_member_with_existing_address_port_pool_combination(self):
        with self.member(pool_id=self.pool_id) as member1:
            member1 = member1['member']
            member_data = {
                'address': member1['address'],
                'protocol_port': member1['protocol_port'],
                'weight': 1,
                'subnet_id': member1['subnet_id'],
                'admin_state_up': True,
                'tenant_id': member1['tenant_id']
            }
            self.assertRaises(
                loadbalancerv2.MemberExists,
                self.plugin.create_pool_member,
                context.get_admin_context(),
                self.pool_id,
                {'member': member_data})

    def test_create_member_nonexistent_subnet(self):
        member_data = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'subnet_id': uuidutils.generate_uuid(),
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }
        self.assertRaises(
            loadbalancerv2.EntityNotFound,
            self.plugin.create_pool_member,
            context.get_admin_context(),
            self.pool_id,
            {'member': member_data})

    def test_create_member_nonexistent_pool(self):
        member_data = {
            'address': '127.0.0.1',
            'protocol_port': 80,
            'weight': 1,
            'subnet_id': self.test_subnet_id,
            'admin_state_up': True,
            'tenant_id': self._tenant_id
        }
        self.assertRaises(
            loadbalancerv2.EntityNotFound,
            self.plugin.create_pool_member,
            context.get_admin_context(),
            uuidutils.generate_uuid(),
            {'member': member_data})

    def test_update_member(self):
        keys = [('address', "127.0.0.1"),
                ('tenant_id', self._tenant_id),
                ('protocol_port', 80),
                ('weight', 10),
                ('admin_state_up', False),
                ('name', 'member2')]
        with self.member(pool_id=self.pool_id) as member:
            member_id = member['member']['id']
            resp, pool1_update = self._get_pool_api(self.pool_id)
            self.assertEqual(1, len(pool1_update['pool']['members']))
            data = {'member': {'weight': 10, 'admin_state_up': False,
                               'name': 'member2'}}
            resp, body = self._update_member_api(self.pool_id, member_id, data)
            for k, v in keys:
                self.assertEqual(v, body['member'][k])
            resp, pool1_update = self._get_pool_api(self.pool_id)
            self.assertEqual(1, len(pool1_update['pool']['members']))
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id,
                                    member_id=member_id, member_disabled=True)

    def test_delete_member(self):
        with self.member(pool_id=self.pool_id, no_delete=True) as member:
            member_id = member['member']['id']
            resp = self._delete_member_api(self.pool_id, member_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)
            resp, pool_update = self._get_pool_api(self.pool_id)
            self.assertEqual(0, len(pool_update['pool']['members']))

    def test_show_member(self):
        keys = [('address', "127.0.0.1"),
                ('tenant_id', self._tenant_id),
                ('protocol_port', 80),
                ('weight', 1),
                ('admin_state_up', True),
                ('name', 'member1')]
        with self.member(pool_id=self.pool_id,
                         name='member1') as member:
            member_id = member['member']['id']
            resp, body = self._get_member_api(self.pool_id, member_id)
            for k, v in keys:
                self.assertEqual(v, body['member'][k])

    def test_list_members(self):
        with self.member(pool_id=self.pool_id,
                         name='member1', protocol_port=81):
            resp, body = self._list_members_api(self.pool_id)
            self.assertEqual(1, len(body['members']))

    def test_list_members_only_for_pool(self):
        with self.member(pool_id=self.alt_pool_id):
            with self.member(pool_id=self.pool_id,
                             protocol_port=81) as in_member:
                resp, body = self._list_members_api(self.pool_id)
                self.assertEqual(len(body['members']), 1)
                self.assertIn(in_member['member'], body['members'])

    def test_list_members_with_sort_emulated(self):
        with self.member(pool_id=self.pool_id, protocol_port=81) as m1:
            with self.member(pool_id=self.pool_id, protocol_port=82) as m2:
                with self.member(pool_id=self.pool_id, protocol_port=83) as m3:
                    self._test_list_with_sort(
                        'pool', (m3, m2, m1),
                        [('protocol_port', 'desc')],
                        id=self.pool_id,
                        subresource='member')

    def test_list_members_with_pagination_emulated(self):
        with self.member(pool_id=self.pool_id, protocol_port=81) as m1:
            with self.member(pool_id=self.pool_id, protocol_port=82) as m2:
                with self.member(pool_id=self.pool_id, protocol_port=83) as m3:
                    self._test_list_with_pagination(
                        'pool', (m1, m2, m3), ('protocol_port', 'asc'),
                        2, 2,
                        id=self.pool_id, subresource='member'
                    )

    def test_list_members_with_pagination_reverse_emulated(self):
        with self.member(pool_id=self.pool_id, protocol_port=81) as m1:
            with self.member(pool_id=self.pool_id, protocol_port=82) as m2:
                with self.member(pool_id=self.pool_id, protocol_port=83) as m3:
                    self._test_list_with_pagination_reverse(
                        'pool', (m1, m2, m3), ('protocol_port', 'asc'),
                        2, 2,
                        id=self.pool_id, subresource='member'
                    )

    def test_list_members_invalid_pool_id(self):
        resp, body = self._list_members_api('WRONG_POOL_ID')
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)
        resp, body = self._list_members_api(self.pool_id)
        self.assertEqual(webob.exc.HTTPOk.code, resp.status_int)

    def test_get_member_invalid_pool_id(self):
        with self.member(pool_id=self.pool_id) as member:
            member_id = member['member']['id']
            resp, body = self._get_member_api('WRONG_POOL_ID', member_id)
            self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)
            resp, body = self._get_member_api(self.pool_id, member_id)
            self.assertEqual(webob.exc.HTTPOk.code, resp.status_int)

    def test_create_member_invalid_pool_id(self):
        data = {'member': {'address': '127.0.0.1',
                           'protocol_port': 80,
                           'weight': 1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'subnet_id': self.test_subnet_id}}
        resp, body = self._create_member_api('WRONG_POOL_ID', data)
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    def test_update_member_invalid_pool_id(self):
        with self.member(pool_id=self.pool_id) as member:
            member_id = member['member']['id']
            data = {'member': {'weight': 1}}
            resp, body = self._update_member_api(
                'WRONG_POOL_ID', member_id, data)
            self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    def test_create_member_invalid_name(self):
        data = {'member': {'address': '127.0.0.1',
                           'protocol_port': 80,
                           'weight': 1,
                           'admin_state_up': True,
                           'tenant_id': self._tenant_id,
                           'subnet_id': self.test_subnet_id,
                           'name': 123}}
        resp, body = self._create_member_api('POOL_ID', data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_delete_member_invalid_pool_id(self):
        with self.member(pool_id=self.pool_id) as member:
            member_id = member['member']['id']
            resp = self._delete_member_api('WRONG_POOL_ID', member_id)
            self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    def test_get_pool_shows_members(self):
        with self.member(pool_id=self.pool_id,
                         name='member1') as member:
            expected = {'id': member['member']['id']}
            resp, body = self._get_pool_api(self.pool_id)
            self.assertIn(expected, body['pool']['members'])


class HealthMonitorTestBase(MemberTestBase):

    def _create_healthmonitor_api(self, data):
        req = self.new_create_request("healthmonitors", data, self.fmt)
        resp = req.get_response(self.ext_api)
        body = self.deserialize(self.fmt, resp)
        return resp, body

    def _update_healthmonitor_api(self, hm_id, data):
        req = self.new_update_request_lbaas('healthmonitors', data, hm_id)
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

    def test_create_healthmonitor(self, **extras):
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

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1', **extras) as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            self.assertTrue(hm_id)

            actual = {}
            for k, v in healthmonitor['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id,
                                    hm_id=hm_id)
            _, pool = self._get_pool_api(self.pool_id)
            self.assertEqual(
                {'type': lb_const.SESSION_PERSISTENCE_HTTP_COOKIE,
                 'cookie_name': None},
                pool['pool'].get('session_persistence'))
        return healthmonitor

    def test_show_healthmonitor(self, **extras):
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

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            resp, body = self._get_healthmonitor_api(hm_id)
            actual = {}
            for k, v in body['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)

        return healthmonitor

    def test_update_healthmonitor(self, **extras):
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

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'delay': 30,
                                      'timeout': 10,
                                      'max_retries': 4,
                                      'expected_codes': '200,404',
                                      'url_path': '/index.html',
                                      'name': 'monitor2'}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            actual = {}
            for k, v in body['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id,
                                    hm_id=hm_id)

        return healthmonitor

    def test_delete_healthmonitor(self):
        with self.healthmonitor(pool_id=self.pool_id,
                                no_delete=True) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            resp = self._delete_healthmonitor_api(hm_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

    def test_create_healthmonitor_with_type_tcp(self, **extras):
        expected = {
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 2,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'
        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id,
                                type='TCP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            self.assertTrue(hm_id)

            actual = {}
            for k, v in healthmonitor['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id, hm_id=hm_id)
        return healthmonitor

    def test_create_healthmonitor_with_l7policy_redirect_pool(self):
        with self.listener(loadbalancer_id=self.lb_id,
                           protocol_port=84) as listener:
            listener_id = listener['listener']['id']
            pool = self._create_pool(
                    self.fmt, lb_const.PROTOCOL_HTTP,
                    lb_const.LB_METHOD_ROUND_ROBIN,
                    loadbalancer_id=self.lb_id)
            pool = self.deserialize(self.fmt, pool)
            pool_id = pool['pool']['id']
            with self.l7policy(
                listener_id,
                action=lb_const.L7_POLICY_ACTION_REDIRECT_TO_POOL,
                redirect_pool_id=pool_id):
                self._create_healthmonitor(
                        None, pool_id=pool_id,
                        type='TCP', delay=1,
                        timeout=1, max_retries=1,
                        expected_res_status=webob.exc.HTTPCreated.code)

    def test_show_healthmonitor_with_type_tcp(self, **extras):
        expected = {
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 2,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'
        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id,
                                type='TCP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            resp, body = self._get_healthmonitor_api(hm_id)
            actual = {}
            for k, v in body['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)

        return healthmonitor

    def test_update_healthmonitor_with_type_tcp(self, **extras):
        expected = {
            'type': 'TCP',
            'delay': 30,
            'timeout': 10,
            'max_retries': 4,
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor2'
        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id,
                                type='TCP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'delay': 30,
                                      'timeout': 10,
                                      'max_retries': 4,
                                      'name': 'monitor2'}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            actual = {}
            for k, v in body['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id, hm_id=hm_id)

        return healthmonitor

    def test_create_health_monitor_with_timeout_invalid(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 1,
                                  'timeout': -1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_timeout_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'delay': 10,
                                      'timeout': -1,
                                      'max_retries': 2,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_delay_invalid(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': -1,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_delay_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'delay': -1,
                                      'timeout': 1,
                                      'max_retries': 2,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_max_retries_invalid(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 20,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_max_retries_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'delay': 1,
                                      'timeout': 1,
                                      'max_retries': 20,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_type_invalid(self):
        data = {'healthmonitor': {'type': 1,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_type_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'type': 1,
                                      'delay': 1,
                                      'timeout': 1,
                                      'max_retries': 2,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_http_method_non_default(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'http_method': 'POST',
                                  'delay': 2,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(201, resp.status_int)
        self._delete('healthmonitors', body['healthmonitor']['id'])

    def test_create_health_monitor_with_http_method_invalid(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'http_method': 'FOO',
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_http_method_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'type': 'HTTP',
                                      'http_method': 'FOO',
                                      'delay': 1,
                                      'timeout': 1,
                                      'max_retries': 2,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_url_path_non_default(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'url_path': '/a/b_c-d/e%20f',
                                  'delay': 2,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(201, resp.status_int)
        self._delete('healthmonitors', body['healthmonitor']['id'])

    def test_create_health_monitor_with_url_path_invalid(self):
        data = {'healthmonitor': {'type': 'HTTP',
                                  'url_path': 1,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 2,
                                  'admin_state_up': True,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_update_health_monitor_with_url_path_invalid(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            data = {'healthmonitor': {'url_path': 1,
                                      'delay': 1,
                                      'timeout': 1,
                                      'max_retries': 2,
                                      'admin_state_up': False}}
            resp, body = self._update_healthmonitor_api(hm_id, data)
            self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_healthmonitor_invalid_pool_id(self):
        data = {'healthmonitor': {'type': lb_const.HEALTH_MONITOR_TCP,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 1,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': uuidutils.generate_uuid()}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPNotFound.code, resp.status_int)

    def test_create_healthmonitor_invalid_name(self):
        data = {'healthmonitor': {'type': lb_const.HEALTH_MONITOR_TCP,
                                  'delay': 1,
                                  'timeout': 1,
                                  'max_retries': 1,
                                  'tenant_id': self._tenant_id,
                                  'pool_id': self.pool_id,
                                  'name': 123}}
        resp, body = self._create_healthmonitor_api(data)
        self.assertEqual(webob.exc.HTTPBadRequest.code, resp.status_int)

    def test_create_health_monitor_with_max_retries_down(self, **extras):
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
            'max_retries_down': 1
        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1', max_retries_down=1,
                                **extras) as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            self.assertTrue(hm_id)

            actual = {}
            for k, v in healthmonitor['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id,
                                    pool_id=self.pool_id,
                                    hm_id=hm_id)
            _, pool = self._get_pool_api(self.pool_id)
            self.assertEqual(
                {'type': lb_const.SESSION_PERSISTENCE_HTTP_COOKIE,
                 'cookie_name': None},
                pool['pool'].get('session_persistence'))
        return healthmonitor

    def test_only_one_healthmonitor_per_pool(self):
        with self.healthmonitor(pool_id=self.pool_id):
            data = {'healthmonitor': {'type': lb_const.HEALTH_MONITOR_TCP,
                                      'delay': 1,
                                      'timeout': 1,
                                      'max_retries': 1,
                                      'tenant_id': self._tenant_id,
                                      'pool_id': self.pool_id}}
            resp, body = self._create_healthmonitor_api(data)
            self.assertEqual(webob.exc.HTTPConflict.code, resp.status_int)

    def test_get_healthmonitor(self):
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
            'max_retries_down': 3
        }

        with self.healthmonitor(pool_id=self.pool_id, type='HTTP',
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            expected['id'] = hm_id
            resp, body = self._get_healthmonitor_api(hm_id)
            self.assertEqual(expected, body['healthmonitor'])

    def test_list_healthmonitors(self):
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
            'max_retries_down': 3
        }

        with self.healthmonitor(pool_id=self.pool_id,
                                type='HTTP') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            expected['id'] = hm_id
            resp, body = self._list_healthmonitors_api()
            self.assertEqual([expected], body['healthmonitors'])

    def test_get_pool_shows_healthmonitor_id(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            resp, body = self._get_pool_api(self.pool_id)
            self.assertEqual(hm_id, body['pool']['healthmonitor_id'])

    def test_update_healthmonitor_status(self):
        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            ctx = context.get_admin_context()
            self.plugin.db.update_status(
                ctx, models.HealthMonitorV2, hm_id,
                provisioning_status=n_constants.ACTIVE,
                operating_status=lb_const.DEGRADED)
            db_hm = self.plugin.db.get_healthmonitor(ctx, hm_id)
            self.assertEqual(n_constants.ACTIVE, db_hm.provisioning_status)
            self.assertFalse(hasattr(db_hm, 'operating_status'))

    def test_create_healthmonitor_admin_state_down(self):
        self.test_create_healthmonitor(admin_state_up=False)


class LbaasStatusesTest(MemberTestBase):
    def setUp(self):
        super(LbaasStatusesTest, self).setUp()
        self.lbs_to_clean = []
        self.addCleanup(self.cleanup_lbs)

    def cleanup_lbs(self):
        for lb_dict in self.lbs_to_clean:
            self._delete_populated_lb(lb_dict)

    def test_disable_lb(self):
        ctx = context.get_admin_context()
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        opt = {'admin_state_up': False}
        self.plugin.db.update_loadbalancer(ctx, lb_id, opt)
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        n_disabled = self._countDisabledChildren(statuses, 0)
        self.assertEqual(11, n_disabled)

    def _countDisabledChildren(self, obj, count):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "operating_status":
                    count += 1
                    continue
                count = self._countDisabledChildren(value, count)
        if isinstance(obj, list):
            for value in obj:
                count = self._countDisabledChildren(value, count)
        return count

    def test_disable_trickles_down(self):
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        self._update_loadbalancer_api(lb_id,
                                      {'loadbalancer': {
                                          'admin_state_up': False}})
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        self._assertDisabled(self._traverse_statuses(statuses))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTP'))
        self._assertDisabled(self._traverse_statuses(
            statuses, listener='listener_HTTPS'))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTP',
                                                     pool='pool_HTTP'))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTPS',
                                                     pool='pool_HTTPS'))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTP',
                                                     pool='pool_HTTP',
                                                     member='127.0.0.1'))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTPS',
                                                     pool='pool_HTTPS',
                                                     member='127.0.0.4'))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTP',
                                                     pool='pool_HTTP',
                                                     healthmonitor=True))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener='listener_HTTPS',
                                                     pool='pool_HTTPS',
                                                     healthmonitor=True))

    def test_disable_not_calculated_in_degraded(self):
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        listener_id = lb_dict['listeners'][0]['id']
        listener = 'listener_HTTP'
        self._update_listener_api(listener_id,
                                  {'listener': {'admin_state_up': False}})
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        self._assertOnline(self._traverse_statuses(statuses))
        self._update_listener_api(listener_id,
                                  {'listener': {'admin_state_up': True}})
        pool_id = lb_dict['listeners'][0]['pools'][0]['id']
        pool = 'pool_HTTP'
        member_id = lb_dict['listeners'][0]['pools'][0]['members'][0]['id']
        member = '127.0.0.1'
        self._update_member_api(pool_id, member_id,
                                {'member': {'admin_state_up': False}})
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        self._assertOnline(self._traverse_statuses(statuses))
        self._assertOnline(self._traverse_statuses(statuses,
                                                   listener=listener))
        self._assertOnline(self._traverse_statuses(statuses,
                                                   listener=listener,
                                                   pool=pool))
        self._assertDisabled(self._traverse_statuses(statuses,
                                                     listener=listener,
                                                     pool=pool,
                                                     member=member))

    def test_that_failures_trickle_up_on_prov_errors(self):
        ctx = context.get_admin_context()
        ERROR = n_constants.ERROR
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        stat = self._traverse_statuses(statuses, listener="listener_HTTP",
                                       pool="pool_HTTP", member='127.0.0.1')
        member_id = stat['id']
        self.plugin.db.update_status(ctx, models.MemberV2, member_id,
                                     provisioning_status=ERROR)
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        #Assert the parents of the member are degraded
        self._assertDegraded(self._traverse_statuses(statuses,
                                                     listener='listener_HTTP',
                                                     pool='pool_HTTP'))
        self._assertDegraded(self._traverse_statuses(statuses,
                                                    listener='listener_HTTP'))
        self._assertDegraded(self._traverse_statuses(statuses))
        #Verify siblings are not degraded
        self._assertNotDegraded(self._traverse_statuses(statuses,
            listener='listener_HTTPS', pool='pool_HTTPS'))
        self._assertNotDegraded(self._traverse_statuses(statuses,
            listener='listener_HTTPS'))

    def test_that_failures_trickle_up_on_non_ONLINE_prov_status(self):
        ctx = context.get_admin_context()
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        stat = self._traverse_statuses(statuses, listener="listener_HTTP",
                                       pool="pool_HTTP", member='127.0.0.1')
        member_id = stat['id']
        self.plugin.db.update_status(ctx, models.MemberV2, member_id,
                                     operating_status=lb_const.OFFLINE)
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        #Assert the parents of the member are degraded
        self._assertDegraded(self._traverse_statuses(statuses,
                                                    listener='listener_HTTP',
                                                    pool='pool_HTTP'))
        self._assertDegraded(self._traverse_statuses(statuses,
                                                    listener='listener_HTTP'))
        self._assertDegraded(self._traverse_statuses(statuses))
        #Verify siblings are not degraded
        self._assertNotDegraded(self._traverse_statuses(statuses,
            listener='listener_HTTPS', pool='pool_HTTPS'))
        self._assertNotDegraded(self._traverse_statuses(statuses,
            listener='listener_HTTPS'))

    def test_degraded_with_pool_error(self):
        ctx = context.get_admin_context()
        ERROR = n_constants.ERROR
        lb_dict = self._create_new_populated_loadbalancer()
        lb_id = lb_dict['id']
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        stat = self._traverse_statuses(statuses, listener="listener_HTTP",
                                       pool="pool_HTTP")
        pool_id = stat['id']
        self.plugin.db.update_status(ctx, models.PoolV2, pool_id,
                                     provisioning_status=ERROR)
        statuses = self._get_loadbalancer_statuses_api(lb_id)[1]
        #Assert the parents of the pool are degraded
        self._assertDegraded(self._traverse_statuses(statuses,
                                                    listener='listener_HTTP'))
        self._assertDegraded(self._traverse_statuses(statuses))
        #Verify siblings are not degraded
        self._assertNotDegraded(self._traverse_statuses(statuses,
            listener='listener_HTTPS'))

    def _assertOnline(self, obj):
        OS = "operating_status"
        if OS in obj:
            self.assertEqual(lb_const.ONLINE, obj[OS])

    def _assertDegraded(self, obj):
        OS = "operating_status"
        if OS in obj:
            self.assertEqual(lb_const.DEGRADED, obj[OS])

    def _assertNotDegraded(self, obj):
        OS = "operating_status"
        if OS in obj:
            self.assertNotEqual(lb_const.DEGRADED, obj[OS])

    def _assertDisabled(self, obj):
        OS = "operating_status"
        if OS in obj:
            self.assertEqual(lb_const.DISABLED, obj[OS])

    def _delete_populated_lb(self, lb_dict):
        lb_id = lb_dict['id']
        for pool in lb_dict['pools']:
            pool_id = pool['id']
            for member in pool['members']:
                member_id = member['id']
                self._delete_member_api(pool_id, member_id)
            self._delete_pool_api(pool_id)
        for listener in lb_dict['listeners']:
            listener_id = listener['id']
            self._delete_listener_api(listener_id)
        self._delete_loadbalancer_api(lb_id)

    def _traverse_statuses(self, statuses, listener=None, pool=None,
                           member=None, healthmonitor=False):
        lb = statuses['statuses']['loadbalancer']
        if listener is None:
            return copy.copy(lb)
        listener_list = lb['listeners']
        for listener_obj in listener_list:
            if listener_obj['name'] == listener:
                if pool is None:
                    return copy.copy(listener_obj)
                pool_list = listener_obj['pools']
                for pool_obj in pool_list:
                    if pool_obj['name'] == pool:
                        if healthmonitor:
                            return copy.copy(pool_obj['healthmonitor'])
                        if member is None:
                            return copy.copy(pool_obj)
                        member_list = pool_obj['members']
                        for member_obj in member_list:
                            if member_obj['address'] == member:
                                return copy.copy(member_obj)
        pool_list = lb['pools']
        for pool_obj in pool_list:
            if pool_obj['name'] == pool:
                if healthmonitor:
                    return copy.copy(pool_obj['healthmonitor'])
                if member is None:
                    return copy.copy(pool_obj)
                member_list = pool_obj['members']
                for member_obj in member_list:
                    if member_obj['address'] == member:
                        return copy.copy(member_obj)
        raise KeyError

    def _create_new_populated_loadbalancer(self):
        oct4 = 1
        subnet_id = self.test_subnet_id
        HTTP = lb_const.PROTOCOL_HTTP
        HTTPS = lb_const.PROTOCOL_HTTPS
        ROUND_ROBIN = lb_const.LB_METHOD_ROUND_ROBIN
        fmt = self.fmt
        lb_dict = {}
        lb_res = self._create_loadbalancer(
            self.fmt, subnet_id=self.test_subnet_id,
            name='test_loadbalancer')
        lb = self.deserialize(fmt, lb_res)
        lb_id = lb['loadbalancer']['id']
        lb_dict['id'] = lb_id
        lb_dict['listeners'] = []
        lb_dict['pools'] = []
        for prot, port in [(HTTP, 80), (HTTPS, 443)]:
            res = self._create_listener(fmt, prot, port, lb_id,
                                        name="listener_%s" % prot)
            listener = self.deserialize(fmt, res)
            listener_id = listener['listener']['id']
            lb_dict['listeners'].append({'id': listener_id, 'pools': []})
            res = self._create_pool(fmt, prot, ROUND_ROBIN, listener_id,
                                    loadbalancer_id=lb_id,
                                    name="pool_%s" % prot)
            pool = self.deserialize(fmt, res)
            pool_id = pool['pool']['id']
            members = []
            lb_dict['listeners'][-1]['pools'].append({'id': pool['pool']['id'],
                                                      'members': members})
            lb_dict['pools'].append({'id': pool['pool']['id'],
                                    'members': members})
            res = self._create_healthmonitor(fmt, pool_id, type=prot, delay=1,
                                             timeout=1, max_retries=1)
            health_monitor = self.deserialize(fmt, res)
            lb_dict['listeners'][-1]['pools'][-1]['health_monitor'] = {
                'id': health_monitor['healthmonitor']['id']}
            lb_dict['pools'][-1]['health_monitor'] = {
                'id': health_monitor['healthmonitor']['id']}
            for i in six.moves.range(0, 3):
                address = "127.0.0.%i" % oct4
                oct4 += 1
                res = self._create_member(fmt, pool_id, address, port,
                                          subnet_id)
                member = self.deserialize(fmt, res)
                members.append({'id': member['member']['id']})
        self.lbs_to_clean.append(lb_dict)
        return lb_dict
