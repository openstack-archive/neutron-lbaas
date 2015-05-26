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

from oslo_log import log as logging
from tempest.common.utils import data_utils
from tempest import config
from tempest import exceptions
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
        cls.listener = cls._create_listener(
            **cls.create_listener_kwargs)
        cls.listener_id = cls.listener['id']

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
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listeners = self.listeners_client.list_listeners()
        self.assertEqual(len(listeners), 2)
        self.assertIn(self.listener, listeners)
        self.assertIn(new_listener, listeners)
        self.assertNotEqual(self.listener, new_listener)
        self._delete_listener(new_listener_id)

    @test.attr(type='smoke')
    def test_create_listener(self):
        """Test create listener"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self.assertNotEqual(self.listener, new_listener)
        self._delete_listener(new_listener_id)

    @test.attr(type='negative')
    def test_create_listener_missing_field_loadbalancer(self):
        """Test create listener with a missing required field loadbalancer"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          protocol_port=self.port,
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_missing_field_protocol(self):
        """Test create listener with a missing required field protocol"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_missing_field_protocol_port(self):
        """Test create listener with a missing required field protocol_port"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_missing_admin_state_up(self):
        """Test create listener with a missing admin_state_up field"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self.assertTrue(new_listener['admin_state_up'])
        self._delete_listener(new_listener_id)

    @test.attr(type='negative')
    def test_create_listener_invalid_load_balancer_id(self):
        """Test create listener with an invalid load_balancer_id"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id="234*",
                          protocol_port=self.port,
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_invalid_protocol(self):
        """Test create listener with an invalid protocol"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol="UDP")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_invalid_protocol_port(self):
        """Test create listener with an invalid protocol_port"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port="9999999",
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_invalid_admin_state_up(self):
        """Test update listener with an invalid admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          admin_state_up="abc123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_invalid_tenant_id(self):
        """Test create listener with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          tenant_id="&^%123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_create_listener_invalid_name(self):
        """Test create listener with an invalid name"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          name='a' * 256)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_create_listener_invalid_description(self):
        """Test create listener with an invalid description"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          description='a' * 256)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_invalid_connection_limit(self):
        """Test create listener with an invalid value for connection
        _limit field
        """
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          connection_limit="&^%123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_empty_load_balancer_id(self):
        """Test create listener with an empty load_balancer_id"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id="",
                          protocol_port=self.port,
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_empty_protocol(self):
        """Test create listener with an empty protocol"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_empty_protocol_port(self):
        """Test create listener with an empty protocol_port"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port="",
                          protocol=self.protocol)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_empty_admin_state_up(self):
        """Test update listener with an empty  admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          admin_state_up="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_empty_tenant_id(self):
        """Test create listener with an empty tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          tenant_id="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_create_listener_empty_name(self):
        """Test create listener with an empty name"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        create_new_listener_kwargs['name'] = ""
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self._delete_listener(new_listener_id)

    @test.attr(type='smoke')
    def test_create_listener_empty_description(self):
        """Test create listener with an empty description"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8081
        create_new_listener_kwargs['description'] = ""
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self._delete_listener(new_listener_id)

    @test.attr(type='negative')
    def test_create_listener_empty_connection_limit(self):
        """Test create listener with an empty connection
        _limit field
        """
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          loadbalancer_id=self.load_balancer_id,
                          protocol_port=self.port,
                          protocol=self.protocol,
                          connection_limit="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_create_listener_incorrect_attribute(self):
        """Test create a listener with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self._create_listener,
                          incorrect_attribute="incorrect_attribute",
                          **self.create_listener_kwargs)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener(self):
        """Test update listener"""
        self._update_listener(self.listener_id,
                              name='new_name')
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('name'), 'new_name')

    @test.attr(type='negative')
    def test_update_listener_invalid_tenant_id(self):
        """Test update listener with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          tenant_id="&^%123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_update_listener_invalid_admin_state_up(self):
        """Test update a listener with an invalid admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          admin_state_up="$23")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_update_listener_invalid_name(self):
        """Test update a listener with an invalid name"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          name='a' * 256)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_update_listener_invalid_description(self):
        """Test update a listener with an invalid description"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          description='a' * 256)
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_update_listener_invalid_connection_limit(self):
        """Test update a listener with an invalid connection_limit"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          connection_limit="$23")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_update_listener_incorrect_attribute(self):
        """Test update a listener with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          name="listener_name123",
                          description="listener_description123",
                          admin_state_up=True,
                          connection_limit=10,
                          vip_subnet_id="123321123")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener_missing_name(self):
        """Test update listener with a missing name"""
        old_listener = self.listeners_client.get_listener(
            self.listener_id)
        old_name = old_listener['name']
        self._update_listener(self.listener_id,
                              description='updated')
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('name'), old_name)

    @test.attr(type='smoke')
    def test_update_listener_missing_description(self):
        """Test update listener with a missing description"""
        old_listener = self.listeners_client.get_listener(
            self.listener_id)
        old_description = old_listener['description']
        self._update_listener(self.listener_id,
                              name='updated_name')
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('description'), old_description)

    @test.attr(type='smoke')
    def test_update_listener_missing_admin_state_up(self):
        """Test update listener with a missing admin_state_up"""
        old_listener = self.listeners_client.get_listener(
            self.listener_id)
        old_admin_state_up = old_listener['admin_state_up']
        self._update_listener(self.listener_id,
                              name='updated_name')
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('admin_state_up'), old_admin_state_up)

    @test.attr(type='smoke')
    def test_update_listener_missing_connection_limit(self):
        """Test update listener with a missing connection_limit"""
        old_listener = self.listeners_client.get_listener(
            self.listener_id)
        old_connection_limit = old_listener['connection_limit']
        self._update_listener(self.listener_id,
                              name='updated_name')
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('connection_limit'),
                         old_connection_limit)

    @test.attr(type='negative')
    def test_update_listener_empty_tenant_id(self):
        """Test update listener with an empty tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          tenant_id="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='negative')
    def test_update_listener_empty_admin_state_up(self):
        """Test update a listener with an empty admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          admin_state_up="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_update_listener_empty_name(self):
        """Test update a listener with an empty name"""
        self._update_listener(self.listener_id,
                              name="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('name'), "")

    @test.attr(type='smoke')
    def test_update_listener_empty_description(self):
        """Test update a listener with an empty description"""
        self._update_listener(self.listener_id,
                              description="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])
        listener = self.listeners_client.get_listener(
            self.listener_id)
        self.assertEqual(listener.get('description'), "")

    @test.attr(type='negative')
    def test_update_listener_empty_connection_limit(self):
        """Test update a listener with an empty connection_limit"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_listener,
                          listener_id=self.listener_id,
                          connection_limit="")
        self._check_status_tree(load_balancer_id=self.load_balancer_id,
                                listener_ids=[self.listener_id])

    @test.attr(type='smoke')
    def test_delete_listener(self):
        """Test delete listener"""
        create_new_listener_kwargs = self.create_listener_kwargs
        create_new_listener_kwargs['protocol_port'] = 8083
        new_listener = self._create_listener(
            **create_new_listener_kwargs)
        new_listener_id = new_listener['id']
        self._check_status_tree(
            load_balancer_id=self.load_balancer_id,
            listener_ids=[self.listener_id, new_listener_id])
        listener = self.listeners_client.get_listener(
            new_listener_id)
        self.assertEqual(new_listener, listener)
        self.assertNotEqual(self.listener, new_listener)
        self._delete_listener(new_listener_id)
        self.assertRaises(exceptions.NotFound,
                          self.listeners_client.get_listener,
                          new_listener_id)
