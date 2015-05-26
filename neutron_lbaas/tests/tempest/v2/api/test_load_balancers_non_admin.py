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

from netaddr import IPAddress

from neutron_lbaas.tests.tempest.v2.api import base
from oslo_log import log as logging
from tempest.common.utils import data_utils
from tempest import config
from tempest import exceptions
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class LoadBalancersTestJSON(base.BaseTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Load Balancers with default credentials:

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
        self._delete_load_balancer(new_load_balancer_id)

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
        self._delete_load_balancer(new_load_balancer_id)

    @test.attr(type='negative')
    def test_create_load_balancer_missing_vip_subnet_id_field(self):
        """
        Test create load balancer with a missing
        required vip_subnet_id field
        """
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          tenant_id=self.subnet['tenant_id'])

    @test.attr(type='negative')
    def test_create_load_balancer_empty_provider_field(self):
        """Test create load balancer with an empty provider field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          provider="")

    @test.attr(type='smoke')
    def test_create_load_balancer_empty_description_field(self):
        """Test create load balancer with an empty description field"""
        load_balancer = self._create_active_load_balancer(
            vip_subnet_id=self.subnet['id'], description="")
        self.assertEqual(load_balancer.get('description'), "")
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='negative')
    def test_create_load_balancer_empty_vip_address_field(self):
        """Test create load balancer with empty vip_address field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          vip_subnet_id=self.subnet['id'],
                          vip_address="")

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_admin_state_up(self):
        """Test create load balancer with a missing admin_state_up field"""
        load_balancer = self._create_active_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.assertEqual(load_balancer.get('admin_state_up'), True)
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='negative')
    def test_create_load_balancer_empty_admin_state_up_field(self):
        """Test create load balancer with empty admin_state_up field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          vip_subnet_id=self.subnet['id'],
                          admin_state_up="")

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_name(self):
        """Test create load balancer with a missing name field"""
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.assertEqual(load_balancer.get('name'), '')
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_empty_name(self):
        """Test create load balancer with a empty name field"""
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'], name="")
        self.assertEqual(load_balancer.get('name'), "")
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_description(self):
        """Test create load balancer with a missing description field"""
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.assertEqual(load_balancer.get('description'), '')
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_vip_address(self):
        """
        Test create load balancer with a missing vip_address field,checks for
        ipversion and actual ip address
        """
        load_balancer = self._create_active_load_balancer(
            vip_subnet_id=self.subnet['id'])
        load_balancer_ip_initial = load_balancer['vip_address']
        ip = IPAddress(load_balancer_ip_initial)
        self.assertEqual(ip.version, 4)
        load_balancer = self.load_balancers_client.get_load_balancer(
            load_balancer['id'])
        load_balancer_final = load_balancer['vip_address']
        self.assertEqual(load_balancer_ip_initial, load_balancer_final)
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_provider_field(self):
        """Test create load balancer with a missing provider field"""
        load_balancer = self._create_active_load_balancer(
            vip_subnet_id=self.subnet['id'])
        load_balancer_initial = load_balancer['provider']
        load_balancer = self.load_balancers_client.get_load_balancer(
            load_balancer['id'])
        load_balancer_final = load_balancer['provider']
        self.assertEqual(load_balancer_initial, load_balancer_final)
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='negative')
    def test_create_load_balancer_invalid_vip_subnet_id(self):
        """Test create load balancer with an invalid vip subnet id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          vip_subnet_id="abc123")

    @test.attr(type='negative')
    def test_create_load_balancer_empty_vip_subnet_id(self):
        """Test create load balancer with an empty vip subnet id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          vip_subnet_id="")

    @test.attr(type='negative')
    def test_create_load_balancer_invalid_tenant_id(self):
        """Test create load balancer with an invalid tenant id"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          tenant_id="&^%123")

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_create_load_balancer_invalid_name(self):
        """Test create load balancer with an invalid name"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          tenant_id=self.subnet['tenant_id'],
                          vip_subnet_id=self.subnet['id'],
                          name='n' * 256)

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_create_load_balancer_invalid_description(self):
        """Test create load balancer with an invalid description"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          tenant_id=self.subnet['tenant_id'],
                          vip_subnet_id=self.subnet['id'],
                          description='d' * 256)

    @test.attr(type='negative')
    def test_create_load_balancer_incorrect_attribute(self):
        """Test create a load balancer with an extra, incorrect field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          tenant_id=self.subnet['tenant_id'],
                          vip_subnet_id=self.subnet['id'],
                          protocol_port=80)

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_tenant_id_field(self):
        """Test create load balancer with a missing tenant id field"""
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.assertEqual(load_balancer.get('tenant_id'),
                         self.subnet['tenant_id'])
        self._delete_load_balancer(load_balancer['id'])

    @test.attr(type='negative')
    def test_create_load_balancer_empty_tenant_id_field(self):
        """Test create load balancer with empty tenant_id field"""
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          vip_subnet_id=self.subnet['id'],
                          wait=False,
                          tenant_id="")

    @test.attr(type='negative')
    def test_create_load_balancer_other_tenant_id_field(self):
        """Test create load balancer for other tenant"""
        tenant = 'deffb4d7c0584e89a8ec99551565713c'
        self.assertRaises(exceptions.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          wait=False,
                          vip_subnet_id=self.subnet['id'],
                          tenant_id=tenant)

    @test.attr(type='smoke')
    def test_update_load_balancer(self):
        """Test update load balancer"""
        self._update_load_balancer(self.load_balancer_id,
                                   name='new_name')
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        self.assertEqual(load_balancer.get('name'), 'new_name')

    @test.attr(type='smoke')
    def test_update_load_balancer_empty_name(self):
        """Test update load balancer with empty name"""
        self._update_load_balancer(self.load_balancer_id,
                                   name="")
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        self.assertEqual(load_balancer.get('name'), "")

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_update_load_balancer_invalid_name(self):
        """Test update load balancer with invalid name"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          wait=False,
                          name='a' * 256)

    @test.attr(type='smoke')
    def test_update_load_balancer_missing_name(self):
        """Test update load balancer with missing name"""
        self._update_load_balancer(self.load_balancer_id)
        loadbalancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        load_balancer_initial = loadbalancer['name']
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        load_balancer_new = load_balancer['name']
        self.assertEqual(load_balancer_initial, load_balancer_new)

    @test.skip_because(bug="1434717")
    @test.attr(type='negative')
    def test_update_load_balancer_invalid_description(self):
        """Test update load balancer with invalid description"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          wait=False,
                          description='a' * 256)

    @test.attr(type='smoke')
    def test_update_load_balancer_empty_description(self):
        """Test update load balancer with empty description"""
        self._update_load_balancer(self.load_balancer_id,
                                   description="")
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        self.assertEqual(load_balancer.get('description'), "")

    @test.attr(type='smoke')
    def test_update_load_balancer_missing_description(self):
        """Test update load balancer with missing description"""
        self._update_load_balancer(self.load_balancer_id)
        loadbalancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        load_balancer_initial = loadbalancer['description']
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        load_balancer_new = load_balancer['description']
        self.assertEqual(load_balancer_initial, load_balancer_new)

    @test.attr(type='negative')
    def test_update_load_balancer_invalid_admin_state_up_field(self):
        """Test update load balancer with an invalid admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          wait=False,
                          admin_state_up="a&^%$jbc123")

    @test.attr(type='negative')
    def test_update_load_balancer_empty_admin_state_up_field(self):
        """Test update load balancer with an empty admin_state_up"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          wait=False,
                          admin_state_up="")

    @test.attr(type='smoke')
    def test_update_load_balancer_missing_admin_state_up(self):
        """Test update load balancer with missing admin state field"""
        self._update_load_balancer(self.load_balancer_id)
        loadbalancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer_id)
        load_balancer_initial = loadbalancer['admin_state_up']
        self.assertEqual(load_balancer_initial, True)

    @test.attr(type='negative')
    def test_update_load_balancer_incorrect_attribute(self):
        """Test update a load balancer with an extra, invalid attribute"""
        self.assertRaises(exceptions.BadRequest,
                          self._update_load_balancer,
                          load_balancer_id=self.load_balancer_id,
                          wait=False,
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
        self._delete_load_balancer(new_load_balancer_id)
        self.assertRaises(exceptions.NotFound,
                          self.load_balancers_client.get_load_balancer,
                          new_load_balancer_id)
