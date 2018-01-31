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

from tempest.common import utils
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators
from tempest.lib import exceptions as ex

from neutron_lbaas.tests.tempest.v2.api import base


class LoadBalancersTestAdmin(base.BaseAdminTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Load Balancers with admin credentials:

        list load balancers
        create load balancer
        get load balancer
        update load balancer
        delete load balancer
    """

    @classmethod
    def resource_setup(cls):
        super(LoadBalancersTestAdmin, cls).resource_setup()
        if not utils.is_extension_enabled('lbaasv2', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.load_balancer = cls.load_balancers_client.create_load_balancer(
            vip_subnet_id=cls.subnet['id'])
        cls._wait_for_load_balancer_status(cls.load_balancer['id'])

        cls.tenant = 'deffb4d7c0584e89a8ec99551565713c'
        cls.tenant_load_balancer = (
            cls.load_balancers_client.create_load_balancer(
                vip_subnet_id=cls.subnet['id'],
                tenant_id=cls.tenant))
        cls._wait_for_load_balancer_status(cls.tenant_load_balancer['id'])

    @classmethod
    def resource_cleanup(cls):
        test_utils.call_and_ignore_notfound_exc(
            cls._delete_load_balancer,
            cls.load_balancer['id'])
        cls._wait_for_load_balancer_status(
            load_balancer_id=cls.load_balancer['id'], delete=True)
        cls._wait_for_neutron_port_delete(cls.load_balancer['vip_port_id'])
        test_utils.call_and_ignore_notfound_exc(
            cls._delete_load_balancer,
            cls.tenant_load_balancer['id'])
        cls._wait_for_load_balancer_status(
            load_balancer_id=cls.tenant_load_balancer['id'], delete=True)
        cls._wait_for_neutron_port_delete(
            cls.tenant_load_balancer['vip_port_id'])
        super(LoadBalancersTestAdmin, cls).resource_cleanup()

    def test_create_load_balancer_missing_tenant_id_field_for_admin(self):
        """
        Test create load balancer with a missing tenant id field.
        Verify tenant_id matches when creating loadbalancer vs.
        load balancer(admin tenant)
        """
        admin_lb = self.load_balancers_client.get_load_balancer(
            self.load_balancer.get('id'))
        self.assertEqual(self.load_balancer.get('tenant_id'),
                         admin_lb.get('tenant_id'))

    def test_create_load_balancer_missing_tenant_id_for_tenant(self):
        """
        Test create load balancer with a missing tenant id field. Verify
        tenant_id does not match of subnet(non-admin tenant) vs.
        load balancer(admin tenant)
        """
        self.assertNotEqual(self.load_balancer.get('tenant_id'),
                            self.subnet['tenant_id'])

    @decorators.attr(type='negative')
    def test_create_load_balancer_empty_tenant_id_field(self):
        """Test create load balancer with empty tenant_id field should fail"""
        self.assertRaises(ex.BadRequest,
                          self.load_balancers_client.create_load_balancer,
                          vip_subnet_id=self.subnet['id'],
                          wait=False,
                          tenant_id="")

    @decorators.attr(type='smoke')
    def test_create_load_balancer_for_another_tenant(self):
        """Test create load balancer for other tenant"""
        self.assertEqual(self.tenant,
                         self.tenant_load_balancer.get('tenant_id'))

    def test_update_load_balancer_description(self):
        """Test update admin load balancer description"""
        new_description = "Updated Description"
        self._update_load_balancer(self.load_balancer['id'],
                                   description=new_description)
        load_balancer = self.load_balancers_client.get_load_balancer(
            self.load_balancer['id'])
        self.assertEqual(new_description, load_balancer.get('description'))

    @decorators.attr(type='smoke')
    def test_delete_load_balancer_for_tenant(self):
        """Test delete another tenant's load balancer as admin"""
        self.assertEqual(self.tenant,
                         self.tenant_load_balancer.get('tenant_id'))
        self._delete_load_balancer(self.tenant_load_balancer['id'])
        self.assertRaises(ex.NotFound,
                          self.load_balancers_client.get_load_balancer,
                          self.tenant_load_balancer['id'])
