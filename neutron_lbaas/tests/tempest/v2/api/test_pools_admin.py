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

from tempest.lib.common.utils import data_utils
from tempest.lib import decorators
from tempest.lib import exceptions as ex
from tempest import test

from neutron_lbaas.tests.tempest.v2.api import base


PROTOCOL_PORT = 80


class TestPools(base.BaseAdminTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Pools:

        list pools
        create pool
        get pool
        update pool
        delete pool
    """

    @classmethod
    def resource_setup(cls):
        super(TestPools, cls).resource_setup()
        if not test.is_extension_enabled('lbaas', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.load_balancer = cls._create_load_balancer(
            tenant_id=cls.subnet.get('tenant_id'),
            vip_subnet_id=cls.subnet.get('id'))

    def increment_protocol_port(self):
        global PROTOCOL_PORT
        PROTOCOL_PORT += 1

    def _prepare_and_create_pool(self, protocol=None, lb_algorithm=None,
                                 listener_id=None, **kwargs):
        self.increment_protocol_port()
        if not protocol:
            protocol = 'HTTP'
        if not lb_algorithm:
            lb_algorithm = 'ROUND_ROBIN'
        if not listener_id:
            listener = self._create_listener(
                loadbalancer_id=self.load_balancer.get('id'),
                protocol='HTTP', protocol_port=PROTOCOL_PORT, **kwargs)
            listener_id = listener.get('id')
        response = self._create_pool(protocol=protocol,
                                     lb_algorithm=lb_algorithm,
                                     listener_id=listener_id,
                                     **kwargs)
        self.addCleanup(self._delete_pool, response['id'])
        return response

    @test.attr(type='negative')
    def test_create_pool_using_empty_tenant_field(self):
        """Test create pool with empty tenant field should fail"""
        self.assertRaises(ex.BadRequest, self._create_pool,
                          protocol='HTTP',
                          tenant_id="",
                          lb_algorithm='ROUND_ROBIN')

    @decorators.skip_because(bug="1468457")
    @test.attr(type='smoke')
    def test_create_pool_missing_tenant_id_for_other_tenant(self):
        """
        Test create pool with a missing tenant id field. Verify
        tenant_id does not match when creating pool vs.
        pool (admin client)
        """
        new_pool = self._prepare_and_create_pool(
            protocol='HTTP',
            lb_algorithm='ROUND_ROBIN')
        pool = self.pools_client.get_pool(new_pool.get('id'))
        pool_tenant = pool['tenant_id']
        self.assertNotEqual(pool_tenant, self.subnet['tenant_id'])

    @decorators.skip_because(bug="1468457")
    @test.attr(type='smoke')
    def test_create_pool_missing_tenant_id_for_admin(self):
        """
        Test create pool with a missing tenant id field. Verify
        tenant_id matches when creating pool vs. pool (admin client)
        """
        new_pool = self._prepare_and_create_pool(
            protocol='HTTP',
            lb_algorithm='ROUND_ROBIN')
        pool = self.pools_client.get_pool(new_pool.get('id'))
        pool_tenant = pool['tenant_id']
        self.assertEqual(pool_tenant, pool.get('tenant_id'))

    @decorators.skip_because(bug="1468457")
    @test.attr(type='smoke')
    def test_create_pool_for_another_tenant(self):
        """Test create pool for other tenant field"""
        tenant = 'deffb4d7c0584e89a8ec99551565713c'
        new_pool = self._prepare_and_create_pool(
            tenant_id=tenant)
        pool = self.pools_client.get_pool(new_pool.get('id'))
        pool_tenant = pool.get('tenant_id')
        self.assertEqual(pool_tenant, tenant)
