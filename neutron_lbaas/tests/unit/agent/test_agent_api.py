# Copyright 2013 New Dream Network, LLC (DreamHost)
# Copyright 2015 Rackspace
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

import copy

import mock

from neutron_lbaas.agent import agent_api as api
from neutron_lbaas.tests import base


class TestApiCache(base.BaseTestCase):
    def setUp(self):
        super(TestApiCache, self).setUp()

        self.api = api.LbaasAgentApi('topic', mock.sentinel.context, 'host')

    def test_init(self):
        self.assertEqual('host', self.api.host)
        self.assertEqual(mock.sentinel.context, self.api.context)

    def _test_method(self, method, **kwargs):
        add_host = ('get_ready_devices', 'plug_vip_port', 'unplug_vip_port')
        expected_kwargs = copy.copy(kwargs)
        if method in add_host:
            expected_kwargs['host'] = self.api.host

        with mock.patch.object(self.api.client, 'call') as rpc_mock, \
                mock.patch.object(self.api.client, 'prepare') as prepare_mock:
            prepare_mock.return_value = self.api.client
            rpc_mock.return_value = 'foo'
            rv = getattr(self.api, method)(**kwargs)

        self.assertEqual('foo', rv)

        prepare_args = {}
        prepare_mock.assert_called_once_with(**prepare_args)

        rpc_mock.assert_called_once_with(mock.sentinel.context, method,
                                         **expected_kwargs)

    def test_get_ready_devices(self):
        self._test_method('get_ready_devices')

    def test_get_loadbalancer(self):
        self._test_method('get_loadbalancer',
                          loadbalancer_id='loadbalancer_id')

    def test_loadbalancer_destroyed(self):
        self._test_method('loadbalancer_destroyed',
                          loadbalancer_id='loadbalancer_id')

    def test_loadbalancer_deployed(self):
        self._test_method('loadbalancer_deployed',
                          loadbalancer_id='loadbalancer_id')

    def test_update_status(self):
        self._test_method('update_status', obj_type='type', obj_id='id',
                          provisioning_status='p_status',
                          operating_status='o_status')

    def test_plug_vip_port(self):
        self._test_method('plug_vip_port', port_id='port_id')

    def test_unplug_vip_port(self):
        self._test_method('unplug_vip_port', port_id='port_id')

    def test_update_loadbalancer_stats(self):
        self._test_method('update_loadbalancer_stats', loadbalancer_id='id',
                          stats='stats')
