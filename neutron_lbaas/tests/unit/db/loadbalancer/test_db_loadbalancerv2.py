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

import contextlib
import copy
import exceptions as ex
import mock
import six

from neutron.api import extensions
from neutron.api.v2 import attributes
from neutron.common import config
from neutron.common import constants as n_constants
from neutron.common import exceptions as n_exc
from neutron import context
import neutron.db.l3_db  # noqa
from neutron.plugins.common import constants
from neutron.tests.unit.db import test_db_base_plugin_v2
from oslo_config import cfg
from oslo_utils import uuidutils
import testtools
import webob.exc

from neutron import manager
from neutron_lbaas._i18n import _
from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.common import exceptions
from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.drivers.logging_noop import driver as noop_driver
import neutron_lbaas.extensions
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import plugin as loadbalancer_plugin
from neutron_lbaas.tests import base


DB_CORE_PLUGIN_CLASS = 'neutron.db.db_base_plugin_v2.NeutronDbPluginV2'
DB_LB_PLUGIN_CLASS = (
    "neutron_lbaas.services.loadbalancer."
    "plugin.LoadBalancerPluginv2"
)
NOOP_DRIVER_CLASS = ('neutron_lbaas.drivers.logging_noop.driver.'
                     'LoggingNoopLoadBalancerDriver')

extensions_path = ':'.join(neutron_lbaas.extensions.__path__)

_subnet_id = "0c798ed8-33ba-11e2-8b28-000c291c4d14"


class LbaasTestMixin(object):
    resource_prefix_map = dict(
        (k, loadbalancerv2.LOADBALANCERV2_PREFIX)
        for k in loadbalancerv2.RESOURCE_ATTRIBUTE_MAP.keys()
    )

    def _get_loadbalancer_optional_args(self):
        return 'description', 'vip_address', 'admin_state_up', 'name'

    def _create_loadbalancer(self, fmt, subnet_id,
                             expected_res_status=None, **kwargs):
        data = {'loadbalancer': {'vip_subnet_id': subnet_id,
                                 'tenant_id': self._tenant_id}}
        args = self._get_loadbalancer_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['loadbalancer'][arg] = kwargs[arg]

        lb_req = self.new_create_request('loadbalancers', data, fmt)
        lb_res = lb_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, lb_res.status_int)

        return lb_res

    def _get_listener_optional_args(self):
        return ('name', 'description', 'default_pool_id', 'loadbalancer_id',
                'connection_limit', 'admin_state_up',
                'default_tls_container_ref', 'sni_container_refs')

    def _create_listener(self, fmt, protocol, protocol_port, loadbalancer_id,
                         expected_res_status=None, **kwargs):
        data = {'listener': {'protocol': protocol,
                             'protocol_port': protocol_port,
                             'loadbalancer_id': loadbalancer_id,
                             'tenant_id': self._tenant_id}}
        args = self._get_listener_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['listener'][arg] = kwargs[arg]

        listener_req = self.new_create_request('listeners', data, fmt)
        listener_res = listener_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, listener_res.status_int)

        return listener_res

    def _get_pool_optional_args(self):
        return 'name', 'description', 'admin_state_up', 'session_persistence'

    def _create_pool(self, fmt, protocol, lb_algorithm, listener_id,
                     expected_res_status=None, **kwargs):
        data = {'pool': {'protocol': protocol,
                         'lb_algorithm': lb_algorithm,
                         'listener_id': listener_id,
                         'tenant_id': self._tenant_id}}

        args = self._get_pool_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['pool'][arg] = kwargs[arg]

        pool_req = self.new_create_request('pools', data, fmt)
        pool_res = pool_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, pool_res.status_int)

        return pool_res

    def _get_member_optional_args(self):
        return 'weight', 'admin_state_up', 'name'

    def _create_member(self, fmt, pool_id, address, protocol_port, subnet_id,
                       expected_res_status=None, **kwargs):
        data = {'member': {'address': address,
                           'protocol_port': protocol_port,
                           'subnet_id': subnet_id,
                           'tenant_id': self._tenant_id}}

        args = self._get_member_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['member'][arg] = kwargs[arg]
        member_req = self.new_create_request('pools',
                                             data,
                                             fmt=fmt,
                                             id=pool_id,
                                             subresource='members')
        member_res = member_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, member_res.status_int)

        return member_res

    def _get_healthmonitor_optional_args(self):
        return ('weight', 'admin_state_up', 'expected_codes', 'url_path',
                'http_method', 'name')

    def _create_healthmonitor(self, fmt, pool_id, type, delay, timeout,
                              max_retries, expected_res_status=None, **kwargs):
        data = {'healthmonitor': {'type': type,
                                  'delay': delay,
                                  'timeout': timeout,
                                  'max_retries': max_retries,
                                  'pool_id': pool_id,
                                  'tenant_id': self._tenant_id}}

        args = self._get_healthmonitor_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['healthmonitor'][arg] = kwargs[arg]

        hm_req = self.new_create_request('healthmonitors', data, fmt=fmt)
        hm_res = hm_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, hm_res.status_int)

        return hm_res

    @contextlib.contextmanager
    def loadbalancer(self, fmt=None, subnet=None, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        with test_db_base_plugin_v2.optional_ctx(
            subnet, self.subnet) as tmp_subnet:

            res = self._create_loadbalancer(fmt,
                                            tmp_subnet['subnet']['id'],
                                            **kwargs)
            if res.status_int >= webob.exc.HTTPClientError.code:
                raise webob.exc.HTTPClientError(
                    explanation=_("Unexpected error code: %s") %
                    res.status_int
                )
            lb = self.deserialize(fmt or self.fmt, res)
            yield lb
            if not no_delete:
                self._delete('loadbalancers', lb['loadbalancer']['id'])

    @contextlib.contextmanager
    def listener(self, fmt=None, protocol='HTTP', loadbalancer_id=None,
                 protocol_port=80, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        res = self._create_listener(fmt, protocol, protocol_port,
                                    loadbalancer_id, **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        listener = self.deserialize(fmt or self.fmt, res)
        yield listener
        if not no_delete:
            self._delete('listeners', listener['listener']['id'])

    @contextlib.contextmanager
    def pool(self, fmt=None, protocol='HTTP', lb_algorithm='ROUND_ROBIN',
             no_delete=False, listener_id='listenerID1', **kwargs):
        if not fmt:
            fmt = self.fmt

        res = self._create_pool(fmt,
                                protocol=protocol,
                                lb_algorithm=lb_algorithm,
                                listener_id=listener_id,
                                **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        pool = self.deserialize(fmt or self.fmt, res)
        yield pool
        if not no_delete:
            self._delete('pools', pool['pool']['id'])

    @contextlib.contextmanager
    def member(self, fmt=None, pool_id='pool1id', address='127.0.0.1',
               protocol_port=80, subnet=None, no_delete=False,
               **kwargs):
        if not fmt:
            fmt = self.fmt
        subnet = subnet or self.test_subnet
        with test_db_base_plugin_v2.optional_ctx(
            subnet, self.subnet) as tmp_subnet:

            res = self._create_member(fmt,
                                      pool_id=pool_id,
                                      address=address,
                                      protocol_port=protocol_port,
                                      subnet_id=tmp_subnet['subnet']['id'],
                                      **kwargs)
            if res.status_int >= webob.exc.HTTPClientError.code:
                raise webob.exc.HTTPClientError(
                    explanation=_("Unexpected error code: %s") % res.status_int
                )

            member = self.deserialize(fmt or self.fmt, res)
        yield member
        if not no_delete:
            del_req = self.new_delete_request(
                'pools',
                fmt=fmt,
                id=pool_id,
                subresource='members',
                sub_id=member['member']['id'])
            del_res = del_req.get_response(self.ext_api)
            self.assertEqual(webob.exc.HTTPNoContent.code, del_res.status_int)

    @contextlib.contextmanager
    def healthmonitor(self, fmt=None, pool_id='pool1id', type='TCP', delay=1,
                      timeout=1, max_retries=1, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        res = self._create_healthmonitor(fmt,
                                         pool_id=pool_id,
                                         type=type,
                                         delay=delay,
                                         timeout=timeout,
                                         max_retries=max_retries,
                                         **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        healthmonitor = self.deserialize(fmt or self.fmt, res)
        yield healthmonitor
        if not no_delete:
            del_req = self.new_delete_request(
                'healthmonitors', fmt=fmt,
                id=healthmonitor['healthmonitor']['id'])
            del_res = del_req.get_response(self.ext_api)
            self.assertEqual(webob.exc.HTTPNoContent.code, del_res.status_int)


class LbaasPluginDbTestCase(LbaasTestMixin, base.NeutronDbPluginV2TestCase):
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
            ext_mgr = extensions.PluginAwareExtensionManager(
                extensions_path,
                {constants.LOADBALANCERV2: self.plugin}
            )
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

    def _validate_statuses(self, lb_id, listener_id=None, pool_id=None,
                           member_id=None, hm_id=None,
                           member_disabled=False, listener_disabled=False,
                           loadbalancer_disabled=False):
        resp, body = self._get_loadbalancer_statuses_api(lb_id)
        lb_statuses = body['statuses']['loadbalancer']
        self.assertEqual(constants.ACTIVE,
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
            self.assertEqual(constants.ACTIVE,
                             listener_statuses['provisioning_status'])
            if listener_disabled:
                self.assertEqual(lb_const.DISABLED,
                                 listener_statuses['operating_status'])
            else:
                self.assertEqual(lb_const.ONLINE,
                                 listener_statuses['operating_status'])
            if pool_id:
                pool_statuses = None
                for pool in listener_statuses['pools']:
                    if pool['id'] == pool_id:
                        pool_statuses = pool
                self.assertIsNotNone(pool_statuses)
                self.assertEqual(constants.ACTIVE,
                                 pool_statuses['provisioning_status'])
                self.assertEqual(lb_const.ONLINE,
                                 pool_statuses['operating_status'])
                if member_id:
                    member_statuses = None
                    for member in pool_statuses['members']:
                        if member['id'] == member_id:
                            member_statuses = member
                    self.assertIsNotNone(member_statuses)
                    self.assertEqual(constants.ACTIVE,
                                     member_statuses['provisioning_status'])
                    if member_disabled:
                        self.assertEqual(lb_const.DISABLED,
                                         member_statuses["operating_status"])
                    else:
                        self.assertEqual(lb_const.ONLINE,
                                     member_statuses['operating_status'])
                if hm_id:
                    hm_status = pool_statuses['healthmonitor']
                    self.assertEqual(constants.ACTIVE,
                                     hm_status['provisioning_status'])


class LbaasLoadBalancerTests(LbaasPluginDbTestCase):

    def test_create_loadbalancer(self, **extras):
        expected = {
            'name': 'vip1',
            'description': '',
            'admin_state_up': True,
            'provisioning_status': constants.ACTIVE,
            'operating_status': lb_const.ONLINE,
            'tenant_id': self._tenant_id,
            'listeners': [],
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

    def test_update_loadbalancer(self):
        name = 'new_loadbalancer'
        description = 'a crazy loadbalancer'
        expected_values = {'name': name,
                           'description': description,
                           'admin_state_up': False,
                           'provisioning_status': constants.ACTIVE,
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
                           'provisioning_status': constants.ACTIVE,
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
                           'provisioning_status': constants.ACTIVE,
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
                           'provisioning_status': constants.ACTIVE,
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
        myloadbalancers = [{'name': 'lb1'}]
        with mock.patch.object(manager.NeutronManager, 'get_plugin') as gp:
            self.plugin.db.get_loadbalancers = mock.Mock(
                                               return_value=myloadbalancers)
            plugin = mock.Mock()
            gp.return_value = plugin
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
            'provisioning_status': constants.ACTIVE,
            'operating_status': lb_const.ONLINE,
            'tenant_id': self._tenant_id,
            'listeners': [],
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


class ListenerTestBase(LbaasPluginDbTestCase):
    def setUp(self):
        super(ListenerTestBase, self).setUp()
        network = self._make_network(self.fmt, 'test-net', True)
        self.test_subnet = self._make_subnet(
            self.fmt, network, gateway=attributes.ATTR_NOT_SPECIFIED,
            cidr='10.0.0.0/24')
        self.test_subnet_id = self.test_subnet['subnet']['id']
        lb_res = self._create_loadbalancer(
            self.fmt, subnet_id=self.test_subnet_id)
        self.lb = self.deserialize(self.fmt, lb_res)
        self.lb_id = self.lb['loadbalancer']['id']

    def tearDown(self):
        self._delete_loadbalancer_api(self.lb_id)
        super(ListenerTestBase, self).tearDown()

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

        class ReplaceClass(ex.Exception):
            def __init__(self, status_code, message):
                self.status_code = status_code
                self.message = message
                pass

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

        with contextlib.nested(
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.get_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.delete_cert')
        ) as (get_cert_mock, rm_consumer_mock):
            ex.Exception = ReplaceClass(status_code=404,
                                        message='Cert Not Found')
            get_cert_mock.side_effect = ex.Exception

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

        with contextlib.nested(
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.get_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.delete_cert')
        ) as (get_cert_mock, rm_consumer_mock):
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

        with contextlib.nested(
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'cert_parser.validate_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.get_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.delete_cert')
        ) as (validate_cert_mock, get_cert_mock, rm_consumer_mock):
            get_cert_mock.start().return_value = CertMock(
                'mock_cert')
            validate_cert_mock.side_effect = exceptions.MisMatchedKey

            self.assertRaises(loadbalancerv2.TLSContainerInvalid,
                              self.plugin.create_listener,
                              context.get_admin_context(),
                              {'listener': listener_data})
            rm_consumer_mock.assert_called_once_with(
                listener_data['default_tls_container_ref'],
                self.lb_id)

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

        with contextlib.nested(
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'cert_parser.validate_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.get_cert')
        ) as (validate_cert_mock, get_cert_mock):
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

        with contextlib.nested(
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'cert_parser.validate_cert'),
            mock.patch('neutron_lbaas.services.loadbalancer.plugin.'
                       'CERT_MANAGER_PLUGIN.CertManager.get_cert')
        ) as (validate_cert_mock, get_cert_mock):
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

    def test_delete_listener(self):
        with self.listener(no_delete=True,
                           loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            resp = self._delete_listener_api(listener_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)
            resp, body = self._get_loadbalancer_api(self.lb_id)
            self.assertEqual(0, len(body['loadbalancer']['listeners']))

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

    def test_cannot_delete_listener_with_pool(self):
        with self.listener(loadbalancer_id=self.lb_id) as listener:
            listener_id = listener['listener']['id']
            ctx = context.get_admin_context()
            with self.pool(listener_id=listener_id):
                self.assertRaises(
                    loadbalancerv2.EntityInUse,
                    self.plugin.delete_listener,
                    ctx,
                    listener_id)
            self._validate_statuses(self.lb_id, listener_id)

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


class PoolTestBase(ListenerTestBase):

    def setUp(self):
        super(PoolTestBase, self).setUp()
        listener_res = self._create_listener(self.fmt, lb_const.PROTOCOL_HTTP,
                                             80, self.lb_id)
        self.def_listener = self.deserialize(self.fmt, listener_res)
        self.listener_id = self.def_listener['listener']['id']

    def tearDown(self):
        self._delete_listener_api(self.listener_id)
        super(PoolTestBase, self).tearDown()

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

    def test_create_pool(self, **extras):
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

        with self.pool(listener_id=self.listener_id, **extras) as pool:
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
            self._validate_statuses(self.lb_id, self.listener_id, pool_id)
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
            self._validate_statuses(self.lb_id, self.listener_id, pool_id)

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

    def test_create_pool_with_session_persistence(self):
        self.test_create_pool(session_persistence={'type': 'HTTP_COOKIE'})

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
                           'listeners': [{'id': self.listener_id}],
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
        with contextlib.nested(self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=81,
                                             protocol=lb_const.PROTOCOL_HTTPS),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=82,
                                             protocol=lb_const.PROTOCOL_TCP),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=83,
                                             protocol=lb_const.PROTOCOL_HTTP)
                               ) as (l1, l2, l3):
            with contextlib.nested(self.pool(listener_id=l1['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTPS),
                                   self.pool(listener_id=l2['listener']['id'],
                                             protocol=lb_const.PROTOCOL_TCP),
                                   self.pool(listener_id=l3['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTP)
                                   ) as (p1, p2, p3):
                self._test_list_with_sort('pool', (p2, p1, p3),
                                          [('protocol', 'desc')])

    def test_list_pools_with_pagination_emulated(self):
        with contextlib.nested(self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=81,
                                             protocol=lb_const.PROTOCOL_HTTPS),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=82,
                                             protocol=lb_const.PROTOCOL_TCP),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=83,
                                             protocol=lb_const.PROTOCOL_HTTP)
                               ) as (l1, l2, l3):
            with contextlib.nested(self.pool(listener_id=l1['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTPS),
                                   self.pool(listener_id=l2['listener']['id'],
                                             protocol=lb_const.PROTOCOL_TCP),
                                   self.pool(listener_id=l3['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTP)
                                   ) as (p1, p2, p3):
                self._test_list_with_pagination('pool',
                                                (p3, p1, p2),
                                                ('protocol', 'asc'), 2, 2)

    def test_list_pools_with_pagination_reverse_emulated(self):
        with contextlib.nested(self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=81,
                                             protocol=lb_const.PROTOCOL_HTTPS),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=82,
                                             protocol=lb_const.PROTOCOL_TCP),
                               self.listener(loadbalancer_id=self.lb_id,
                                             protocol_port=83,
                                             protocol=lb_const.PROTOCOL_HTTP)
                               ) as (l1, l2, l3):
            with contextlib.nested(self.pool(listener_id=l1['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTPS),
                                   self.pool(listener_id=l2['listener']['id'],
                                             protocol=lb_const.PROTOCOL_TCP),
                                   self.pool(listener_id=l3['listener']['id'],
                                             protocol=lb_const.PROTOCOL_HTTP)
                                   ) as (p1, p2, p3):
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
            self._validate_statuses(self.lb_id, self.listener_id, self.pool_id,
                                    member_id)
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
            self._validate_statuses(self.lb_id, self.listener_id, self.pool_id,
                                    member_id, member_disabled=True)

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


class LbaasHealthMonitorTests(HealthMonitorTestBase):

    def test_create_healthmonitor(self, **extras):
        expected = {
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 1,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'
        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id,
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor'].get('id')
            self.assertTrue(hm_id)

            actual = {}
            for k, v in healthmonitor['healthmonitor'].items():
                if k in expected:
                    actual[k] = v
            self.assertEqual(expected, actual)
            self._validate_statuses(self.lb_id, self.listener_id, self.pool_id,
                                    hm_id=hm_id)
            _, pool = self._get_pool_api(self.pool_id)
            self.assertEqual(
                {'type': lb_const.SESSION_PERSISTENCE_HTTP_COOKIE,
                 'cookie_name': None},
                pool['pool'].get('session_persistence'))
        return healthmonitor

    def test_show_healthmonitor(self, **extras):
        expected = {
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 1,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'

        }

        expected.update(extras)

        with self.healthmonitor(pool_id=self.pool_id,
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
            'type': 'TCP',
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

        with self.healthmonitor(pool_id=self.pool_id,
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
            self._validate_statuses(self.lb_id, self.listener_id, self.pool_id,
                                    hm_id=hm_id)

        return healthmonitor

    def test_delete_healthmonitor(self):
        with self.healthmonitor(pool_id=self.pool_id,
                                no_delete=True) as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            resp = self._delete_healthmonitor_api(hm_id)
            self.assertEqual(webob.exc.HTTPNoContent.code, resp.status_int)

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
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 1,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': 'monitor1'
        }

        with self.healthmonitor(pool_id=self.pool_id,
                                name='monitor1') as healthmonitor:
            hm_id = healthmonitor['healthmonitor']['id']
            expected['id'] = hm_id
            resp, body = self._get_healthmonitor_api(hm_id)
            self.assertEqual(expected, body['healthmonitor'])

    def test_list_healthmonitors(self):
        expected = {
            'type': 'TCP',
            'delay': 1,
            'timeout': 1,
            'max_retries': 1,
            'http_method': 'GET',
            'url_path': '/',
            'expected_codes': '200',
            'admin_state_up': True,
            'tenant_id': self._tenant_id,
            'pools': [{'id': self.pool_id}],
            'name': '',
        }

        with self.healthmonitor(pool_id=self.pool_id) as healthmonitor:
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
            self.plugin.db.update_status(ctx,
                                         models.HealthMonitorV2, hm_id,
                                         provisioning_status=constants.ACTIVE,
                                         operating_status=lb_const.DEGRADED)
            db_hm = self.plugin.db.get_healthmonitor(ctx, hm_id)
            self.assertEqual(constants.ACTIVE, db_hm.provisioning_status)
            self.assertFalse(hasattr(db_hm, 'operating_status'))


class LbaasStatusesTest(MemberTestBase):
    def setUp(self):
        super(LbaasStatusesTest, self).setUp()
        self.lbs_to_clean = []

    def tearDown(self):
        for lb_dict in self.lbs_to_clean:
            self._delete_populated_lb(lb_dict)
        super(LbaasStatusesTest, self).tearDown()

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
            for key, value in six.iteritems(obj):
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
        ERROR = constants.ERROR
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
        for listener in lb_dict['listeners']:
            listener_id = listener['id']
            for pool in listener['pools']:
                pool_id = pool['id']
                for member in pool['members']:
                    member_id = member['id']
                    self._delete_member_api(pool_id, member_id)
                self._delete_pool_api(pool_id)
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
        for prot, port in [(HTTP, 80), (HTTPS, 443)]:
            res = self._create_listener(fmt, prot, port, lb_id,
                                        name="listener_%s" % prot)
            listener = self.deserialize(fmt, res)
            listener_id = listener['listener']['id']
            lb_dict['listeners'].append({'id': listener_id, 'pools': []})
            res = self._create_pool(fmt, prot, ROUND_ROBIN, listener_id,
                                    name="pool_%s" % prot)
            pool = self.deserialize(fmt, res)
            pool_id = pool['pool']['id']
            members = []
            lb_dict['listeners'][-1]['pools'].append({'id': pool['pool']['id'],
                                                      'members': members})
            res = self._create_healthmonitor(fmt, pool_id, type=prot, delay=1,
                                             timeout=1, max_retries=1)
            health_monitor = self.deserialize(fmt, res)
            lb_dict['listeners'][-1]['pools'][-1]['health_monitor'] = {
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
