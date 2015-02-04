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


class LoadBalancersTestJSON(base.BaseTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Load Balancers:

        list load balancers
        create load balancer
        get load balancer
        update load balancer
        delete load balancer
    """

    @classmethod
    def resource_setup(cls):
        super(LoadBalancersTestJSON, cls).resource_setup()
        if not test.is_extension_enabled('lbaas', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.create_lb_kwargs = {'tenant_id': cls.subnet['tenant_id'],
                                'vip_subnet_id': cls.subnet['id']}
        cls.load_balancer = \
            cls._create_active_load_balancer(**cls.create_lb_kwargs)
        cls.load_balancer_id = cls.load_balancer['id']

    @test.attr(type='smoke')
    def test_list_load_balancers(self):
        """Test list load balancers with one load balancer"""
        load_balancers = self.load_balancers_client.list_load_balancers()
        self.assertEqual(len(load_balancers), 1)
        self.assertIn(self.load_balancer, load_balancers)

    @test.attr(type='smoke')
    def test_list_load_balancers_two(self):
        """Test list load balancers with two load balancers"""
        new_load_balancer = self._create_active_load_balancer(
            **self.create_lb_kwargs)
        new_load_balancer_id = new_load_balancer['id']
        load_balancers = self.load_balancers_client.list_load_balancers()
        self.assertEqual(len(load_balancers), 2)
        self.assertIn(self.load_balancer, load_balancers)
        self.assertIn(new_load_balancer, load_balancers)
        self.assertNotEqual(self.load_balancer, new_load_balancer)
        self.load_balancers_client.delete_load_balancer(new_load_balancer_id)

    @test.attr(type='smoke')
    def test_get_load_balancer(self):
        """Test get load balancer"""
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        self.assertEqual(self.load_balancer, load_balancer)

    @test.attr(type='smoke')
    def test_create_load_balancer(self):
        """Test create load balancer"""
        new_load_balancer = self._create_active_load_balancer(
            **self.create_lb_kwargs)
        new_load_balancer_id = new_load_balancer['id']
        load_balancer = self.load_balancers_client.get_load_balancer(
            new_load_balancer_id)
        self.assertEqual(new_load_balancer, load_balancer)
        self.assertNotEqual(self.load_balancer, new_load_balancer)
        self.load_balancers_client.delete_load_balancer(new_load_balancer_id)

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_field(self):
        """Test create load balancer with a missing required field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          tenant_id=self.subnet['tenant_id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_invalid_vip_subnet_id(self):
        """Test create load balancer with an invalid vip subnet id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          vip_subnet_id="abc123")

    @test.attr(type='smoke')
    def test_create_load_balancer_invalid_tenant_id(self):
        """Test create load balancer with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          tenant_id="&^%123")

    @test.attr(type='smoke')
    def test_create_load_balancer_incorrect_attribute(self):
        """Test create a load balancer with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          tenant_id=self.subnet['tenant_id'],
                          vip_subnet_id=self.subnet['id'],
                          protocol_port=80)

    @test.attr(type='smoke')
    def test_update_load_balancer(self):
        """Test update load balancer"""
        self.load_balancers_client.update_load_balancer(self.load_balancer_id,
                                                        name='new_name')
        self._wait_for_load_balancer_status(self.load_balancer_id)
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        self.assertEqual(load_balancer.get('name'), 'new_name')
        self.load_balancers_client.delete_load_balancer(self.load_balancer_id)

    @test.attr(type='smoke')
    def test_update_load_balancer_invalid_admin_state_up(self):
        """Test update load balancer with an invalid admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          admin_state_up="abc123")

    @test.attr(type='smoke')
    def test_update_load_balancer_invalid_tenant_id(self):
        """Test update load balancer with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          tenant_id="&^%123")

    @test.attr(type='smoke')
    def test_update_load_balancer_incorrect_attribute(self):
        """Test update a load balancer with an extra, invalid attribute"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          name="lb_name",
                          description="lb_name_description",
                          admin_state_up=True,
                          port=80)

    @test.attr(type='smoke')
    def test_get_load_balancer_status_tree(self):
        """Test get load balancer status tree"""
        statuses = self.load_balancers_client.get_load_balancer_status_tree(
            self.load_balancer_id)
        load_balancer = statuses['loadbalancer']
        self.assertEqual("ONLINE", load_balancer['operating_status'])
        self.assertEqual("ACTIVE", load_balancer['provisioning_status'])
        self.assertEqual([], load_balancer['listeners'])

    @test.attr(type='smoke')
    def test_get_load_balancer_stats(self):
        """Test get load balancer stats"""
        stats = self.load_balancers_client.get_load_balancer_stats(
            self.load_balancer_id)
        self.assertEqual(0, stats['bytes_in'])
        self.assertEqual(0, stats['bytes_out'])
        self.assertEqual(0, stats['total_connections'])
        self.assertEqual(0, stats['active_connections'])

    @test.attr(type='smoke')
    def test_delete_load_balancer(self):
        """Test delete load balancer"""
        new_load_balancer = self._create_active_load_balancer(
            **self.create_lb_kwargs)
        new_load_balancer_id = new_load_balancer['id']
        load_balancer = self.load_balancers_client.get_load_balancer(
            new_load_balancer_id)
        self.assertEqual(new_load_balancer, load_balancer)
        self.assertNotEqual(self.load_balancer, new_load_balancer)
        self.load_balancers_client.delete_load_balancer(new_load_balancer_id)
        self.assertRaises(exceptions.NotFound,
                          self.load_balancers_client.get_load_balancer,
                          new_load_balancer_id)
