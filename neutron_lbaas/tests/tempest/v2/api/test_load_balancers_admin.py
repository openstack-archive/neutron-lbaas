# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Rackspace Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib import exceptions as ex
from tempest import test

from neutron_lbaas.tests.tempest.v2.api import base

CONF = config.CONF


class LoadBalancersTestJSON(base.BaseAdminTestCase):

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
    def test_create_load_balancer_missing_tenant_id_field_for_admin(self):
        """
        Test create load balancer with a missing tenant id field.
        Verify tenant_id matches when creating loadbalancer vs.
        load balancer(admin tenant)
        """
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.addCleanup(self._delete_load_balancer, load_balancer['id'])
        admin_lb = self.load_balancers_client.get_load_balancer(
            load_balancer.get('id'))
        self.assertEqual(load_balancer.get('tenant_id'),
                         admin_lb.get('tenant_id'))
        self._wait_for_load_balancer_status(load_balancer['id'])

    @test.attr(type='smoke')
    def test_create_load_balancer_missing_tenant_id_for_other_tenant(self):
        """
        Test create load balancer with a missing tenant id field. Verify
        tenant_id does not match of subnet(non-admin tenant) vs.
        load balancer(admin tenant)
        """
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'])
        self.addCleanup(self._delete_load_balancer, load_balancer['id'])
        self.assertNotEqual(load_balancer.get('tenant_id'),
                            self.subnet['tenant_id'])
        self._wait_for_load_balancer_status(load_balancer['id'])

    @test.attr(type='negative')
    def test_create_load_balancer_empty_tenant_id_field(self):
        """Test create load balancer with empty tenant_id field should fail"""
        self.assertRaises(ex.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          vip_subnet_id=self.subnet['id'],
                          wait=False,
                          tenant_id="")

    @test.attr(type='smoke')
    def test_create_load_balancer_for_another_tenant(self):
        """Test create load balancer for other tenant"""
        tenant = 'deffb4d7c0584e89a8ec99551565713c'
        load_balancer = self.load_balancers_client.create_load_balancer(
            vip_subnet_id=self.subnet['id'],
            tenant_id=tenant)
        self.addCleanup(self._delete_load_balancer, load_balancer['id'])
        self.assertEqual(load_balancer.get('tenant_id'), tenant)
        self._wait_for_load_balancer_status(load_balancer['id'])
