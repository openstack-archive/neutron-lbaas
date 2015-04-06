#    Copyright 2015 Rackspace
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

from tempest.common.utils import data_utils
from tempest import exceptions as ex
from tempest import test

from neutron_lbaas.tests.tempest.v2.api import base


PROTOCOL_PORT = 80


class TestPools(base.BaseTestCase):

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
                protocol='HTTP', protocol_port=PROTOCOL_PORT)
            listener_id = listener.get('id')
        response = self._create_pool(protocol=protocol,
                                     lb_algorithm=lb_algorithm,
                                     listener_id=listener_id,
                                     **kwargs)
        return response

    @test.attr(type='smoke')
    def test_list_pools_empty(self):
        """Test get pools when empty"""
        pools = self.pools_client.list_pools()
        self.assertEqual([], pools)

    @test.attr(type='smoke')
    def test_list_pools_one(self):
        """Test get pools with one pool"""
        new_pool = self._prepare_and_create_pool()
        new_pool = self.pools_client.get_pool(new_pool['id'])
        pools = self.pools_client.list_pools()
        self.assertEqual(1, len(pools))
        self.assertIn(new_pool, pools)
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_list_pools_two(self):
        """Test get pools with two pools"""
        new_pool1 = self._prepare_and_create_pool()
        new_pool2 = self._prepare_and_create_pool()
        pools = self.pools_client.list_pools()
        self.assertEqual(2, len(pools))
        self.assertIn(new_pool1, pools)
        self.assertIn(new_pool2, pools)
        self._delete_pool(new_pool1.get('id'))
        self._delete_pool(new_pool2.get('id'))

    @test.attr(type='smoke')
    def test_get_pool(self):
        """Test get pool"""
        new_pool = self._prepare_and_create_pool()
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_create_pool(self):
        """Test create pool"""
        new_pool = self._prepare_and_create_pool()
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_create_pool_missing_field(self):
        """Test create pool with a missing required field"""
        self.assertRaises(ex.BadRequest, self._create_pool,
                          protocol='HTTP',
                          lb_algorithm='ROUND_ROBIN')

    @test.attr(type='smoke')
    def test_create_pool_invalid_protocol(self):
        """Test create pool with an invalid protocol"""
        self.assertRaises(ex.BadRequest, self._create_pool,
                          protocol='UDP',
                          lb_algorithm='ROUND_ROBIN')

    @test.attr(type='smoke')
    def test_create_pool_incorrect_attribute(self):
        """Test create a pool with an extra, incorrect field"""
        self.assertRaises(ex.BadRequest, self._create_pool,
                          protocol='HTTP',
                          lb_algorithm='ROUND_ROBIN',
                          protocol_port=80)

    @test.attr(type='smoke')
    def test_create_pool_with_session_persistence_unsupported_type(self):
        """Test create a pool with an incorrect type value
        for session persistence
        """
        self.assertRaises(ex.BadRequest, self._create_pool,
                          session_persistence={'type': 'UNSUPPORTED'},
                          protocol='HTTP',
                          lb_algorithm='ROUND_ROBIN')

    @test.attr(type='smoke')
    def test_create_pool_with_session_persistence_http_cookie(self):
        """Test create a pool with session_persistence type=HTTP_COOKIE"""
        new_pool = self._prepare_and_create_pool(
            session_persistence={'type': 'HTTP_COOKIE'})
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_create_pool_with_session_persistence_app_cookie(self):
        """Test create a pool with session_persistence type=APP_COOKIE"""
        new_pool = self._prepare_and_create_pool(
            session_persistence={'type': 'APP_COOKIE',
                                 'cookie_name': 'sessionId'})
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_create_pool_with_session_persistence_redundant_cookie_name(self):
        """Test create a pool with session_persistence with cookie_name
        for type=HTTP_COOKIE
        """
        self.assertRaises(ex.BadRequest, self._create_pool,
                          session_persistence={'type': 'HTTP_COOKIE',
                                               'cookie_name': 'sessionId'},
                          protocol='HTTP',
                          lb_algorithm='ROUND_ROBIN')

    @test.attr(type='smoke')
    def test_create_pool_with_session_persistence_without_cookie_name(self):
        """Test create a pool with session_persistence without
        cookie_name for type=APP_COOKIE
        """
        self.assertRaises(ex.BadRequest, self._create_pool,
                          session_persistence={'type': 'APP_COOKIE'},
                          protocol='HTTP',
                          lb_algorithm='ROUND_ROBIN')

    @test.attr(type='smoke')
    def test_update_pool(self):
        """Test update pool"""
        new_pool = self._prepare_and_create_pool()
        desc = 'testing update with new description'
        pool = self._update_pool(new_pool.get('id'),
                                 description=desc)
        self.assertEqual(desc, pool.get('description'))
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_update_pool_invalid_attribute(self):
        """Test update pool with an invalid attribute"""
        new_pool = self._prepare_and_create_pool()
        self.assertRaises(ex.BadRequest, self._update_pool,
                          new_pool.get('id'), lb_algorithm='ROUNDED')
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_update_pool_incorrect_attribute(self):
        """Test update a pool with an extra, incorrect field"""
        new_pool = self._prepare_and_create_pool()
        self.assertRaises(ex.BadRequest, self._update_pool,
                          new_pool.get('id'), protocol='HTTPS')
        self._delete_pool(new_pool.get('id'))

    @test.attr(type='smoke')
    def test_delete_pool(self):
        """Test delete pool"""
        new_pool = self._prepare_and_create_pool()
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))
        self.assertRaises(ex.NotFound, self.pools_client.get_pool,
                          new_pool.get('id'))

    @test.attr(type='smoke')
    def test_delete_invalid_pool(self):
        """Test delete pool that doesn't exist"""
        new_pool = self._prepare_and_create_pool()
        pool = self.pools_client.get_pool(new_pool.get('id'))
        self.assertEqual(new_pool, pool)
        self._delete_pool(new_pool.get('id'))
        self.assertRaises(ex.NotFound, self._delete_pool,
                          new_pool.get('id'))
