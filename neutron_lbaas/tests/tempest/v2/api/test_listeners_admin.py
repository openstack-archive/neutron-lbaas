# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Rackspace Inc.
# All Rights Reserved.
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

from tempest.common import utils
from tempest.lib.common.utils import data_utils
from tempest.lib import decorators
from tempest.lib import exceptions as ex

from neutron_lbaas.tests.tempest.v2.api import base


class ListenersTestJSON(base.BaseAdminTestCase):

    """
    Tests the listener creation operation in admin scope in the
    Neutron-LBaaS API using the REST client for Listeners:

    """

    @classmethod
    def resource_setup(cls):
        super(ListenersTestJSON, cls).resource_setup()
        if not utils.is_extension_enabled('lbaasv2', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.create_lb_kwargs = {'tenant_id': cls.subnet['tenant_id'],
                                'vip_subnet_id': cls.subnet['id']}
        cls.load_balancer = cls._create_active_load_balancer(
            **cls.create_lb_kwargs)
        cls.port = 80
        cls.load_balancer_id = cls.load_balancer['id']
        cls.create_listener_kwargs = {'loadbalancer_id': cls.load_balancer_id,
                                      'protocol': cls.listener_protocol,
                                      'protocol_port': cls.port}
        cls.listener = cls._create_listener(
            **cls.create_listener_kwargs)
        cls.listener_id = cls.listener['id']

    @classmethod
    def resource_cleanup(cls):
        super(ListenersTestJSON, cls).resource_cleanup()

    @decorators.skip_because(bug="1468457")
    @decorators.attr(type='negative')
    def test_create_listener_empty_tenant_id(self):
        """Test create listener with an empty tenant id should fail"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        create_new_listener_kwargs['tenant_id'] = ""
        self.assertRaises(ex.BadRequest,
                          self._create_listener,
                          **create_new_listener_kwargs)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id])

    @decorators.skip_because(bug="1468457")
    def test_create_listener_invalid_tenant_id(self):
        """Test create listener with an invalid tenant id"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        create_new_listener_kwargs['tenant_id'] = "&^%123"
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self.addCleanup(self._delete_listener, new_listener_id)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)

    @decorators.skip_because(bug="1468457")
    @decorators.attr(type='smoke')
    def test_create_listener_missing_tenant_id(self):
        """Test create listener with an missing tenant id.

        Verify that creating a listener in admin scope with
        a missing tenant_id creates the listener with admin
        tenant_id.
        """
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        admin_listener = self._create_listener(
            **create_new_listener_kwargs)
        admin_listener_id = admin_listener['id']
        self.addCleanup(self._delete_listener, admin_listener_id)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, admin_listener_id])
        listener = self.listeners_client.get_listener(
            admin_listener_id)
        self.assertEqual(admin_listener, listener)
        self.assertEqual(admin_listener.get('tenant_id'),
                         listener.get('tenant_id'))
