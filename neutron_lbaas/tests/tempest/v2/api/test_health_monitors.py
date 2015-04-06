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
from neutron_lbaas.tests.tempest.v2.api import base

from tempest.common.utils import data_utils
from tempest import exceptions as ex
from tempest import test


class TestHealthMonitors(base.BaseTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Health Monitors:

        list pools
        create pool
        get pool
        update pool
        delete pool
    """

    @classmethod
    def resource_setup(cls):
        super(TestHealthMonitors, cls).resource_setup()
        if not test.is_extension_enabled('lbaas', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.load_balancer = cls._create_load_balancer(
            tenant_id=cls.subnet.get('tenant_id'),
            vip_subnet_id=cls.subnet.get('id'))
        cls.listener = cls._create_listener(
            loadbalancer_id=cls.load_balancer.get('id'),
            protocol='HTTP', protocol_port=80)
        cls.pool = cls._create_pool(
            protocol='HTTP', lb_algorithm='ROUND_ROBIN',
            listener_id=cls.listener.get('id'))

    @test.attr(type='smoke')
    def test_list_health_monitors_empty(self):
        hm_list = self.health_monitors_client.list_health_monitors()
        self.assertEmpty(hm_list)

    @test.attr(type='smoke')
    def test_list_health_monitors_one(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        hm_list = self.health_monitors_client.list_health_monitors()
        self.assertIn(hm, hm_list)
        # cleanup test
        self._delete_health_monitor(hm.get('id'))

    @test.attr(type='smoke')
    def test_list_health_monitors_two(self):
        hm1 = self._create_health_monitor(
            type='HTTP', delay=3, max_retries=10, timeout=5,
            pool_id=self.pool.get('id'))
        new_listener = self._create_listener(
            loadbalancer_id=self.load_balancer.get('id'),
            protocol='HTTP', protocol_port=88)
        new_pool = self._create_pool(
            protocol='HTTP', lb_algorithm='ROUND_ROBIN',
            listener_id=new_listener.get('id'))
        hm2 = self._create_health_monitor(
            type='HTTP', max_retries=10, delay=3, timeout=5,
            pool_id=new_pool.get('id'))
        hm_list = self.health_monitors_client.list_health_monitors()
        self.assertEqual(2, len(hm_list))
        self.assertIn(hm1, hm_list)
        self.assertIn(hm2, hm_list)
        # cleanup test
        self._delete_health_monitor(hm1.get('id'))
        self._delete_health_monitor(hm2.get('id'))
        self._delete_pool(new_pool.get('id'))
        self._delete_listener(new_listener.get('id'))

    @test.attr(type='smoke')
    def test_get_health_monitor(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)
        # cleanup test
        self._delete_health_monitor(hm.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor(self):
        new_hm = self._create_health_monitor(
            type='HTTP', delay=3, max_retries=10, timeout=5,
            pool_id=self.pool.get('id'))
        hm = self.health_monitors_client.get_health_monitor(new_hm.get('id'))
        self.assertEqual(new_hm, hm)
        # cleanup test
        self._delete_health_monitor(new_hm.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_invalid_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries='twenty one',
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_extra_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10,
                          pool_id=self.pool.get('id'), subnet_id=10)

    @test.attr(type='smoke')
    def test_update_health_monitor(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        max_retries = 1
        new_hm = self._update_health_monitor(
            hm.get('id'), max_retries=max_retries)
        self.assertEqual(max_retries, new_hm.get('max_retries'))
        # cleanup test
        self._delete_health_monitor(new_hm.get('id'))

    @test.attr(type='smoke')
    def test_udpate_health_monitor_invalid_attribute(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='blue')
        # cleanup test
        self._delete_health_monitor(hm.get('id'))

    @test.attr(type='smoke')
    def test_update_health_monitor_extra_attribute(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), protocol='UDP')
        # cleanup test
        self._delete_health_monitor(hm.get('id'))

    @test.attr(type='smoke')
    def test_delete_health_monitor(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        self._delete_health_monitor(hm.get('id'))
        self.assertRaises(ex.NotFound,
                          self.health_monitors_client.get_health_monitor,
                          hm.get('id'))
