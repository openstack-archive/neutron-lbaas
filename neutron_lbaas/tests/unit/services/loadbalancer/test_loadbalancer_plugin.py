# Copyright 2012 OpenStack Foundation.
# All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

import copy

import mock
from neutron.tests.unit.api.v2 import test_base
from neutron_lib import constants as n_constants
from neutron_lib.plugins import constants
from oslo_utils import uuidutils
from webob import exc

from neutron_lbaas.extensions import healthmonitor_max_retries_down as hm_down
from neutron_lbaas.extensions import lb_network_vip
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.extensions import sharedpools
from neutron_lbaas.tests import base


_uuid = uuidutils.generate_uuid
_get_path = test_base._get_path


class TestLoadBalancerExtensionV2TestCase(base.ExtensionTestCase):
    fmt = 'json'

    def setUp(self):
        super(TestLoadBalancerExtensionV2TestCase, self).setUp()
        resource_map = loadbalancerv2.RESOURCE_ATTRIBUTE_MAP.copy()
        for k in sharedpools.EXTENDED_ATTRIBUTES_2_0.keys():
            resource_map[k].update(sharedpools.EXTENDED_ATTRIBUTES_2_0[k])
        for k in hm_down.EXTENDED_ATTRIBUTES_2_0.keys():
            resource_map[k].update(hm_down.EXTENDED_ATTRIBUTES_2_0[k])
        for k in lb_network_vip.EXTENDED_ATTRIBUTES_2_0.keys():
            resource_map[k].update(lb_network_vip.EXTENDED_ATTRIBUTES_2_0[k])
        self._setUpExtension(
            'neutron_lbaas.extensions.loadbalancerv2.LoadBalancerPluginBaseV2',
            constants.LOADBALANCERV2, resource_map,
            loadbalancerv2.Loadbalancerv2, 'lbaas', use_quota=True)

    def test_loadbalancer_create(self):
        lb_id = _uuid()
        project_id = _uuid()
        data = {'loadbalancer': {'name': 'lb1',
                                 'description': 'descr_lb1',
                                 'tenant_id': project_id,
                                 'project_id': project_id,
                                 'vip_subnet_id': _uuid(),
                                 'admin_state_up': True,
                                 'vip_address': '127.0.0.1'}}
        return_value = copy.copy(data['loadbalancer'])
        return_value.update({'id': lb_id})

        instance = self.plugin.return_value
        instance.create_loadbalancer.return_value = return_value

        res = self.api.post(_get_path('lbaas/loadbalancers', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt))
        data['loadbalancer'].update({
            'provider': n_constants.ATTR_NOT_SPECIFIED,
            'flavor_id': n_constants.ATTR_NOT_SPECIFIED,
            'vip_network_id': n_constants.ATTR_NOT_SPECIFIED})
        instance.create_loadbalancer.assert_called_with(mock.ANY,
                                                        loadbalancer=data)

        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('loadbalancer', res)
        self.assertEqual(return_value, res['loadbalancer'])

    def test_loadbalancer_create_with_vip_network_id(self):
        lb_id = _uuid()
        project_id = _uuid()
        vip_subnet_id = _uuid()
        data = {'loadbalancer': {'name': 'lb1',
                                 'description': 'descr_lb1',
                                 'tenant_id': project_id,
                                 'project_id': project_id,
                                 'vip_network_id': _uuid(),
                                 'admin_state_up': True,
                                 'vip_address': '127.0.0.1'}}
        return_value = copy.copy(data['loadbalancer'])
        return_value.update({'id': lb_id, 'vip_subnet_id': vip_subnet_id})
        del return_value['vip_network_id']

        instance = self.plugin.return_value
        instance.create_loadbalancer.return_value = return_value

        res = self.api.post(_get_path('lbaas/loadbalancers', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt))
        data['loadbalancer'].update({
            'provider': n_constants.ATTR_NOT_SPECIFIED,
            'flavor_id': n_constants.ATTR_NOT_SPECIFIED,
            'vip_subnet_id': n_constants.ATTR_NOT_SPECIFIED})
        instance.create_loadbalancer.assert_called_with(mock.ANY,
                                                        loadbalancer=data)

        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('loadbalancer', res)
        self.assertEqual(return_value, res['loadbalancer'])

    def test_loadbalancer_create_invalid_flavor(self):
        project_id = _uuid()
        data = {'loadbalancer': {'name': 'lb1',
                                 'description': 'descr_lb1',
                                 'tenant_id': project_id,
                                 'project_id': project_id,
                                 'vip_subnet_id': _uuid(),
                                 'admin_state_up': True,
                                 'flavor_id': 123,
                                 'vip_address': '127.0.0.1'}}
        res = self.api.post(_get_path('lbaas/loadbalancers', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt),
                            expect_errors=True)
        self.assertEqual(400, res.status_int)

    def test_loadbalancer_create_valid_flavor(self):
        project_id = _uuid()
        data = {'loadbalancer': {'name': 'lb1',
                                 'description': 'descr_lb1',
                                 'tenant_id': project_id,
                                 'project_id': project_id,
                                 'vip_subnet_id': _uuid(),
                                 'admin_state_up': True,
                                 'flavor_id': _uuid(),
                                 'vip_address': '127.0.0.1'}}
        res = self.api.post(_get_path('lbaas/loadbalancers', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt),
                            expect_errors=True)
        self.assertEqual(201, res.status_int)

    def test_loadbalancer_list(self):
        lb_id = _uuid()
        return_value = [{'name': 'lb1',
                         'admin_state_up': True,
                         'project_id': _uuid(),
                         'id': lb_id}]

        instance = self.plugin.return_value
        instance.get_loadbalancers.return_value = return_value

        res = self.api.get(_get_path('lbaas/loadbalancers', fmt=self.fmt))

        instance.get_loadbalancers.assert_called_with(mock.ANY,
                                                      fields=mock.ANY,
                                                      filters=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)

    def test_loadbalancer_update(self):
        lb_id = _uuid()
        update_data = {'loadbalancer': {'admin_state_up': False}}
        return_value = {'name': 'lb1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': lb_id}

        instance = self.plugin.return_value
        instance.update_loadbalancer.return_value = return_value

        res = self.api.put(_get_path('lbaas/loadbalancers',
                                     id=lb_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_loadbalancer.assert_called_with(
            mock.ANY, lb_id, loadbalancer=update_data)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('loadbalancer', res)
        self.assertEqual(return_value, res['loadbalancer'])

    def test_loadbalancer_get(self):
        lb_id = _uuid()
        return_value = {'name': 'lb1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': lb_id}

        instance = self.plugin.return_value
        instance.get_loadbalancer.return_value = return_value

        res = self.api.get(_get_path('lbaas/loadbalancers',
                                     id=lb_id,
                                     fmt=self.fmt))

        instance.get_loadbalancer.assert_called_with(mock.ANY, lb_id,
                                                     fields=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('loadbalancer', res)
        self.assertEqual(return_value, res['loadbalancer'])

    def test_loadbalancer_delete(self):
        self._test_entity_delete('loadbalancer')

    def test_listener_create(self):
        listener_id = _uuid()
        project_id = _uuid()
        data = {'listener': {'tenant_id': project_id,
                             'project_id': project_id,
                             'name': 'listen-name-1',
                             'description': 'listen-1-desc',
                             'protocol': 'HTTP',
                             'protocol_port': 80,
                             'default_pool_id': None,
                             'default_tls_container_ref': None,
                             'sni_container_refs': [],
                             'connection_limit': 100,
                             'admin_state_up': True,
                             'loadbalancer_id': _uuid()}}
        return_value = copy.copy(data['listener'])
        return_value.update({'id': listener_id})
        del return_value['loadbalancer_id']

        instance = self.plugin.return_value
        instance.create_listener.return_value = return_value

        res = self.api.post(_get_path('lbaas/listeners', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt))
        instance.create_listener.assert_called_with(mock.ANY,
                                                    listener=data)

        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('listener', res)
        self.assertEqual(return_value, res['listener'])

    def test_listener_create_with_tls(self):
        listener_id = _uuid()
        project_id = _uuid()
        tls_ref = 'http://example.ref/uuid'
        sni_refs = ['http://example.ref/uuid',
                    'http://example.ref/uuid1']
        data = {'listener': {'tenant_id': project_id,
                             'project_id': project_id,
                             'name': 'listen-name-1',
                             'description': 'listen-1-desc',
                             'protocol': 'HTTP',
                             'protocol_port': 80,
                             'default_pool_id': None,
                             'default_tls_container_ref': tls_ref,
                             'sni_container_refs': sni_refs,
                             'connection_limit': 100,
                             'admin_state_up': True,
                             'loadbalancer_id': _uuid()}}
        return_value = copy.copy(data['listener'])
        return_value.update({'id': listener_id})
        del return_value['loadbalancer_id']

        instance = self.plugin.return_value
        instance.create_listener.return_value = return_value

        res = self.api.post(_get_path('lbaas/listeners', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt))
        instance.create_listener.assert_called_with(mock.ANY,
                                                    listener=data)

        self.assertEqual(res.status_int, exc.HTTPCreated.code)
        res = self.deserialize(res)
        self.assertIn('listener', res)
        self.assertEqual(res['listener'], return_value)

    def test_listener_create_with_connection_limit_less_than_min_value(self):
        project_id = _uuid()
        data = {'listener': {'tenant_id': project_id,
                             'project_id': project_id,
                             'name': 'listen-name-1',
                             'description': 'listen-1-desc',
                             'protocol': 'HTTP',
                             'protocol_port': 80,
                             'default_tls_container_ref': None,
                             'sni_container_refs': [],
                             'connection_limit': -4,
                             'admin_state_up': True,
                             'loadbalancer_id': _uuid()}}

        res = self.api.post(_get_path('lbaas/listeners', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/{0}'.format(self.fmt),
                            expect_errors=True)
        self.assertEqual(exc.HTTPBadRequest.code, res.status_int)

    def test_listener_list(self):
        listener_id = _uuid()
        return_value = [{'admin_state_up': True,
                         'project_id': _uuid(),
                         'id': listener_id}]

        instance = self.plugin.return_value
        instance.get_listeners.return_value = return_value

        res = self.api.get(_get_path('lbaas/listeners', fmt=self.fmt))

        instance.get_listeners.assert_called_with(mock.ANY,
                                                  fields=mock.ANY,
                                                  filters=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)

    def test_listener_update(self):
        listener_id = _uuid()
        update_data = {'listener': {'admin_state_up': False}}
        return_value = {'name': 'listener1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': listener_id}

        instance = self.plugin.return_value
        instance.update_listener.return_value = return_value

        res = self.api.put(_get_path('lbaas/listeners',
                                     id=listener_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_listener.assert_called_with(
            mock.ANY, listener_id, listener=update_data)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('listener', res)
        self.assertEqual(return_value, res['listener'])

    def test_listener_update_with_tls(self):
        listener_id = _uuid()
        tls_ref = 'http://example.ref/uuid'
        sni_refs = ['http://example.ref/uuid',
                    'http://example.ref/uuid1']
        update_data = {'listener': {'admin_state_up': False}}
        return_value = {'name': 'listener1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': listener_id,
                        'default_tls_container_ref': tls_ref,
                        'sni_container_refs': sni_refs}

        instance = self.plugin.return_value
        instance.update_listener.return_value = return_value

        res = self.api.put(_get_path('lbaas/listeners',
                                     id=listener_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_listener.assert_called_with(
            mock.ANY, listener_id, listener=update_data)
        self.assertEqual(res.status_int, exc.HTTPOk.code)
        res = self.deserialize(res)
        self.assertIn('listener', res)
        self.assertEqual(res['listener'], return_value)

    def test_listener_update_with_connection_limit_less_than_min_value(self):
        listener_id = _uuid()
        update_data = {'listener': {'connection_limit': -4}}
        res = self.api.put(_get_path('lbaas/listeners',
                                     id=listener_id,
                                     fmt=self.fmt),
                           self.serialize(update_data),
                           expect_errors=True)
        self.assertEqual(exc.HTTPBadRequest.code, res.status_int)

    def test_listener_get(self):
        listener_id = _uuid()
        return_value = {'name': 'listener1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': listener_id}

        instance = self.plugin.return_value
        instance.get_listener.return_value = return_value

        res = self.api.get(_get_path('lbaas/listeners',
                                     id=listener_id,
                                     fmt=self.fmt))

        instance.get_listener.assert_called_with(mock.ANY, listener_id,
                                                 fields=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('listener', res)
        self.assertEqual(return_value, res['listener'])

    def test_listener_delete(self):
        self._test_entity_delete('listener')

    def test_pool_create(self):
        pool_id = _uuid()
        project_id = _uuid()
        data = {'pool': {'name': 'pool1',
                         'description': 'descr_pool1',
                         'protocol': 'HTTP',
                         'lb_algorithm': 'ROUND_ROBIN',
                         'admin_state_up': True,
                         'loadbalancer_id': _uuid(),
                         'listener_id': None,
                         'tenant_id': project_id,
                         'project_id': project_id,
                         'session_persistence': {}}}
        return_value = copy.copy(data['pool'])
        return_value.update({'id': pool_id})
        return_value.pop('listener_id')

        instance = self.plugin.return_value
        instance.create_pool.return_value = return_value
        res = self.api.post(_get_path('lbaas/pools', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt)
        instance.create_pool.assert_called_with(mock.ANY, pool=data)
        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('pool', res)
        self.assertEqual(return_value, res['pool'])

    def test_pool_list(self):
        pool_id = _uuid()
        return_value = [{'name': 'pool1',
                         'admin_state_up': True,
                         'project_id': _uuid(),
                         'id': pool_id}]

        instance = self.plugin.return_value
        instance.get_pools.return_value = return_value

        res = self.api.get(_get_path('lbaas/pools', fmt=self.fmt))

        instance.get_pools.assert_called_with(mock.ANY, fields=mock.ANY,
                                              filters=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)

    def test_pool_update(self):
        pool_id = _uuid()
        update_data = {'pool': {'admin_state_up': False}}
        return_value = {'name': 'pool1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': pool_id}

        instance = self.plugin.return_value
        instance.update_pool.return_value = return_value

        res = self.api.put(_get_path('lbaas/pools', id=pool_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_pool.assert_called_with(mock.ANY, pool_id,
                                                pool=update_data)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('pool', res)
        self.assertEqual(return_value, res['pool'])

    def test_pool_get(self):
        pool_id = _uuid()
        return_value = {'name': 'pool1',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': pool_id}

        instance = self.plugin.return_value
        instance.get_pool.return_value = return_value

        res = self.api.get(_get_path('lbaas/pools', id=pool_id,
                                     fmt=self.fmt))

        instance.get_pool.assert_called_with(mock.ANY, pool_id,
                                             fields=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('pool', res)
        self.assertEqual(return_value, res['pool'])

    def test_pool_delete(self):
        self._test_entity_delete('pool')

    def test_pool_member_create(self):
        subnet_id = _uuid()
        member_id = _uuid()
        project_id = _uuid()
        data = {'member': {'address': '10.0.0.1',
                           'protocol_port': 80,
                           'weight': 1,
                           'subnet_id': subnet_id,
                           'admin_state_up': True,
                           'tenant_id': project_id,
                           'project_id': project_id,
                           'name': 'member1'}}
        return_value = copy.copy(data['member'])
        return_value.update({'id': member_id})

        instance = self.plugin.return_value
        instance.create_pool_member.return_value = return_value
        res = self.api.post(_get_path('lbaas/pools/pid1/members',
                                      fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s'
                                         % self.fmt)
        instance.create_pool_member.assert_called_with(mock.ANY,
                                                       pool_id='pid1',
                                                       member=data)
        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('member', res)
        self.assertEqual(return_value, res['member'])

    def test_pool_member_list(self):
        member_id = _uuid()
        return_value = [{'name': 'member1',
                         'admin_state_up': True,
                         'project_id': _uuid(),
                         'id': member_id,
                         'name': 'member1'}]

        instance = self.plugin.return_value
        instance.get_pools.return_value = return_value

        res = self.api.get(_get_path('lbaas/pools/pid1/members',
                                     fmt=self.fmt))

        instance.get_pool_members.assert_called_with(mock.ANY,
                                                     fields=mock.ANY,
                                                     filters=mock.ANY,
                                                     pool_id='pid1')
        self.assertEqual(exc.HTTPOk.code, res.status_int)

    def test_pool_member_update(self):
        member_id = _uuid()
        update_data = {'member': {'admin_state_up': False}}
        return_value = {'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': member_id,
                        'name': 'member1'}

        instance = self.plugin.return_value
        instance.update_pool_member.return_value = return_value

        res = self.api.put(_get_path('lbaas/pools/pid1/members',
                                     id=member_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_pool_member.assert_called_with(
            mock.ANY, member_id, pool_id='pid1',
            member=update_data)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('member', res)
        self.assertEqual(return_value, res['member'])

    def test_pool_member_get(self):
        member_id = _uuid()
        return_value = {'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': member_id,
                        'name': 'member1'}

        instance = self.plugin.return_value
        instance.get_pool_member.return_value = return_value

        res = self.api.get(_get_path('lbaas/pools/pid1/members',
                                     id=member_id, fmt=self.fmt))

        instance.get_pool_member.assert_called_with(mock.ANY,
                                                    member_id,
                                                    fields=mock.ANY,
                                                    pool_id='pid1')
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('member', res)
        self.assertEqual(return_value, res['member'])

    def test_pool_member_delete(self):
        entity_id = _uuid()
        res = self.api.delete(
            test_base._get_path('lbaas/pools/pid1/members',
                                id=entity_id, fmt=self.fmt))
        delete_entity = getattr(self.plugin.return_value,
                                "delete_pool_member")
        delete_entity.assert_called_with(mock.ANY, entity_id,
                                         pool_id='pid1')
        self.assertEqual(exc.HTTPNoContent.code, res.status_int)

    def test_health_monitor_create(self):
        health_monitor_id = _uuid()
        project_id = _uuid()
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 2,
                                  'timeout': 1,
                                  'max_retries': 3,
                                  'max_retries_down': 3,
                                  'http_method': 'GET',
                                  'url_path': '/path',
                                  'expected_codes': '200-300',
                                  'admin_state_up': True,
                                  'tenant_id': project_id,
                                  'project_id': project_id,
                                  'pool_id': _uuid(),
                                  'name': 'monitor1'}}
        return_value = copy.copy(data['healthmonitor'])
        return_value.update({'id': health_monitor_id})
        del return_value['pool_id']

        instance = self.plugin.return_value
        instance.create_healthmonitor.return_value = return_value
        res = self.api.post(_get_path('lbaas/healthmonitors',
                                      fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt)
        instance.create_healthmonitor.assert_called_with(
            mock.ANY, healthmonitor=data)
        self.assertEqual(exc.HTTPCreated.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('healthmonitor', res)
        self.assertEqual(return_value, res['healthmonitor'])

    def test_health_monitor_create_with_db_limit_more_than_max_value(self):
        project_id = _uuid()
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 3000000000000,
                                  'timeout': 1,
                                  'max_retries': 3,
                                  'http_method': 'GET',
                                  'url_path': '/path',
                                  'expected_codes': '200-300',
                                  'admin_state_up': True,
                                  'tenant_id': project_id,
                                  'project_id': project_id,
                                  'pool_id': _uuid(),
                                  'name': 'monitor1'}}
        res = self.api.post(_get_path('lbaas/healthmonitors', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt,
                            expect_errors=True)
        self.assertEqual(exc.HTTPBadRequest.code, res.status_int)

    def test_health_monitor_create_with_timeout_negative(self):
        project_id = _uuid()
        data = {'healthmonitor': {'type': 'HTTP',
                                  'delay': 2,
                                  'timeout': -1,
                                  'max_retries': 3,
                                  'http_method': 'GET',
                                  'url_path': '/path',
                                  'expected_codes': '200-300',
                                  'admin_state_up': True,
                                  'tenant_id': project_id,
                                  'project_id': project_id,
                                  'pool_id': _uuid(),
                                  'name': 'monitor1'}}
        res = self.api.post(_get_path('lbaas/healthmonitors',
                                      fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt,
                            expect_errors=True)
        self.assertEqual(400, res.status_int)

    def test_health_monitor_list(self):
        health_monitor_id = _uuid()
        return_value = [{'type': 'HTTP',
                         'admin_state_up': True,
                         'project_id': _uuid(),
                         'id': health_monitor_id,
                         'name': 'monitor1'}]

        instance = self.plugin.return_value
        instance.get_healthmonitors.return_value = return_value

        res = self.api.get(_get_path('lbaas/healthmonitors', fmt=self.fmt))

        instance.get_healthmonitors.assert_called_with(
            mock.ANY, fields=mock.ANY, filters=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)

    def test_health_monitor_update(self):
        health_monitor_id = _uuid()
        update_data = {'healthmonitor': {'admin_state_up': False}}
        return_value = {'type': 'HTTP',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': health_monitor_id,
                        'name': 'monitor1'}

        instance = self.plugin.return_value
        instance.update_healthmonitor.return_value = return_value

        res = self.api.put(_get_path('lbaas/healthmonitors',
                                     id=health_monitor_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.update_healthmonitor.assert_called_with(
            mock.ANY, health_monitor_id, healthmonitor=update_data)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('healthmonitor', res)
        self.assertEqual(return_value, res['healthmonitor'])

    def test_health_monitor_update_with_db_limit_more_than_max_value(self):
        health_monitor_id = _uuid()
        update_data = {'healthmonitor': {'delay': 3000000000000}}
        res = self.api.put(_get_path('lbaas/healthmonitors',
                                     id=health_monitor_id,
                                     fmt=self.fmt),
                           self.serialize(update_data),
                           expect_errors=True)
        self.assertEqual(exc.HTTPBadRequest.code, res.status_int)

    def test_health_monitor_get(self):
        health_monitor_id = _uuid()
        return_value = {'type': 'HTTP',
                        'admin_state_up': False,
                        'project_id': _uuid(),
                        'id': health_monitor_id,
                        'name': 'monitor1'}

        instance = self.plugin.return_value
        instance.get_healthmonitor.return_value = return_value

        res = self.api.get(_get_path('lbaas/healthmonitors',
                                     id=health_monitor_id,
                                     fmt=self.fmt))

        instance.get_healthmonitor.assert_called_with(
            mock.ANY, health_monitor_id, fields=mock.ANY)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('healthmonitor', res)
        self.assertEqual(return_value, res['healthmonitor'])

    def test_health_monitor_delete(self):
        entity_id = _uuid()
        res = self.api.delete(
            test_base._get_path('lbaas/healthmonitors',
                                id=entity_id, fmt=self.fmt))
        delete_entity = getattr(self.plugin.return_value,
                                "delete_healthmonitor")
        delete_entity.assert_called_with(mock.ANY, entity_id)
        self.assertEqual(exc.HTTPNoContent.code, res.status_int)

    def test_load_balancer_stats(self):
        load_balancer_id = _uuid()

        stats = {'stats': 'dummy'}
        instance = self.plugin.return_value
        instance.stats.return_value = stats

        path = _get_path('lbaas/loadbalancers', id=load_balancer_id,
                         action="stats", fmt=self.fmt)
        res = self.api.get(path)

        instance.stats.assert_called_with(mock.ANY, load_balancer_id)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('stats', res)
        self.assertEqual(stats['stats'], res['stats'])

    def test_load_balancer_statuses(self):
        load_balancer_id = _uuid()

        statuses = {'statuses': {'loadbalancer': {}}}
        instance = self.plugin.return_value
        instance.statuses.return_value = statuses
        path = _get_path('lbaas/loadbalancers', id=load_balancer_id,
                         action="statuses", fmt=self.fmt)
        res = self.api.get(path)
        instance.statuses.assert_called_with(mock.ANY, load_balancer_id)
        self.assertEqual(exc.HTTPOk.code, res.status_int)
        res = self.deserialize(res)
        self.assertIn('statuses', res)
        self.assertEqual(statuses['statuses'], res['statuses'])
