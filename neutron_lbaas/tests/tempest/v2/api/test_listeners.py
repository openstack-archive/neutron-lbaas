# Copyright 2015 Rackspace US Inc.
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

from neutron_lbaas.tests.tempest.v2.api import base

from tempest.common.utils import data_utils
from tempest import config
from tempest import exceptions
from tempest.openstack.common import log as logging
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class ListenersTestJSON(base.BaseTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Listeners:

        list listeners
        create listener
        get listener
        update listener
        delete listener
    """

    @classmethod
    def resource_setup(cls):
        super(ListenersTestJSON, cls).resource_setup()
        if not test.is_extension_enabled('lbaas', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.create_lb_kwargs = {'tenant_id': cls.subnet['tenant_id'],
                                'vip_subnet_id': cls.subnet['id']}
        cls.load_balancer = cls._create_active_load_balancer(
            **cls.create_lb_kwargs)
        cls.protocol = 'HTTP'
        cls.port = 80
        cls.load_balancer_id = cls.load_balancer['id']
        cls.create_listener_kwargs = {'loadbalancer_id': cls.load_balancer_id,
                                      'protocol': cls.protocol,
                                      'protocol_port': cls.port}
        cls.listener = cls.listeners_client.create_listener(
            **cls.create_listener_kwargs)
        cls.listener_id = cls.listener['id']
        cls._wait_for_load_balancer_status(cls.load_balancer_id)

    @test.attr(type='smoke')
    def test_get_listener(self):
        """Test get listener"""
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(self.listener, listener)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_list_listeners(self):
        """Test get listeners with one listener"""
        listeners = self.listeners_client.list_listeners()
        self.assertEqual(len(listeners), 1)
        self.assertIn(self.listener, listeners)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_list_listeners_two(self):
        """Test get listeners with two listeners"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8080
        new_listener = self.listeners_client.create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._wait_for_load_balancer_status(self.load_balancer_id)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listeners = self.listeners_client.list_listeners()
        self.assertEqual(len(listeners), 2)
        self.assertIn(self.listener, listeners)
        self.assertIn(new_listener, listeners)
        self.assertNotEqual(self.listener, new_listener)
        self.listeners_client.delete_listener(new_listener_id)

    @test.attr(type='smoke')
    def test_create_listener(self):
        """Test create listener"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        new_listener = self.listeners_client.create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._wait_for_load_balancer_status(self.load_balancer_id)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self.assertNotEqual(self.listener, new_listener)
        self.listeners_client.delete_listener(new_listener_id)

    @test.attr(type='smoke')
    def test_create_listener_missing_field(self):
        """Test create listener with a missing required field"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_invalid_protocol(self):
        """Test create listener with an invalid protocol"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol="UDP")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_invalid_port(self):
        """Test create listener with an invalid port"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port="9999999",
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_invalid_tenant_id(self):
        """Test create listener with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.create_listener,
                          tenant_id="&^%123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_incorrect_attribute(self):
        """Test create a listener with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.create_listener,
                          incorrect_attribute="incorrect_attribute",
                          **self.create_listener_kwargs)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener(self):
        """Test update listener"""
        self.listeners_client.update_listener(self.listener_id,
                                              name='new_name')
        self._wait_for_load_balancer_status(self.load_balancer_id)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('name'), 'new_name')

    @test.attr(type='smoke')
    def test_update_listener_invalid_admin_state_up(self):
        """Test update listener with an invalid admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.update_listener,
                          listener_id=self.listener_id,
                          admin_state_up="abc123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener_invalid_tenant_id(self):
        """Test update listener with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.update_listener,
                          listener_id=self.listener_id,
                          tenant_id="&^%123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener_incorrect_attribute(self):
        """Test update a listener with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self.listeners_client.update_listener,
                          listener_id=self.listener_id,
                          name="listener_name123",
                          description="listener_description123",
                          admin_state_up=True,
                          connection_limit=10,
                          vip_subnet_id="123321123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_delete_listener(self):
        """Test delete listener"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8083
        new_listener = self.listeners_client.create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._wait_for_load_balancer_status(self.load_balancer_id)
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self.assertNotEqual(self.listener, new_listener)
        self.listeners_client.delete_listener(new_listener_id)
        self.assertRaises(exceptions.NotFound,
                          self.listeners_client.get_listener,
                          new_listener_id)
