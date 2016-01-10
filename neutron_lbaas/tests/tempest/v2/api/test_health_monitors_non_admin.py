# Copyright 2015 Rackspace
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
from tempest_lib.common.utils import data_utils
from tempest_lib import exceptions as ex

from neutron_lbaas.tests.tempest.lib import test
from neutron_lbaas.tests.tempest.v2.api import base


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

    @test.attr(type='smoke')
    def test_list_health_monitors_two(self):
        hm1 = self._create_health_monitor(
            type='HTTP', delay=3, max_retries=10, timeout=5,
            pool_id=self.pool.get('id'))
        new_listener = self._create_listener(
            loadbalancer_id=self.load_balancer.get('id'),
            protocol='HTTP', protocol_port=88)
        self.addCleanup(self._delete_listener, new_listener.get('id'))
        new_pool = self._create_pool(
            protocol='HTTP', lb_algorithm='ROUND_ROBIN',
            listener_id=new_listener.get('id'))
        self.addCleanup(self._delete_pool, new_pool.get('id'))
        hm2 = self._create_health_monitor(
            type='HTTP', max_retries=10, delay=3, timeout=5,
            pool_id=new_pool.get('id'))
        hm_list = self.health_monitors_client.list_health_monitors()
        self.assertEqual(2, len(hm_list))
        self.assertIn(hm1, hm_list)
        self.assertIn(hm2, hm_list)

    @test.attr(type='smoke')
    def test_get_health_monitor(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)

    @test.attr(type='smoke')
    def test_create_health_monitor(self):
        new_hm = self._create_health_monitor(
            type='HTTP', delay=3, max_retries=10, timeout=5,
            pool_id=self.pool.get('id'))
        hm = self.health_monitors_client.get_health_monitor(new_hm.get('id'))
        self.assertEqual(new_hm, hm)

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_required_field_type(self):
        """Test if a non_admin user can create a health monitor with type
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_required_field_delay(self):
        """Test if a non_admin user can create a health monitor with delay
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_required_field_timeout(self):
        """Test if a non_admin user can create a health monitor with timeout
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_required_field_max_retries(self):
        """Test if a non_admin user can create a health monitor with max_retries
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_required_field_pool_id(self):
        """Test if a non_admin user can create a health monitor with pool_id
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5)

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_admin_state_up(self):
        """Test if a non_admin user can create a health monitor with
        admin_state_up missing
        """
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)
        self.assertTrue(hm_test.get('admin_state_up'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_http_method(self):
        """Test if a non_admin user can create a health monitor with
        http_method missing
        """
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)
        self.assertEqual('GET', hm_test.get('http_method'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_url_path(self):
        """Test if a non_admin user can create a health monitor with
        url_path missing
        """
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)
        self.assertEqual('/', hm_test.get('url_path'))

    @test.attr(type='smoke')
    def test_create_health_monitor_missing_expected_codes(self):
        """Test if a non_admin user can create a health monitor with
        expected_codes missing
        """
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm, hm_test)
        self.assertEqual('200', hm_test.get('expected_codes'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_tenant_id(self):
        """Test create health monitor with invalid tenant_id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          tenant_id='blah',
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_type(self):
        """Test create health monitor with invalid type"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='blah', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_delay(self):
        """Test create health monitor with invalid delay"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay='blah', max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_max_retries(self):
        """Test create health monitor with invalid max_retries"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries='blah', timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_timeout(self):
        """Test create health monitor with invalid timeout"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout='blah',
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_pool_id(self):
        """Test create health monitor with invalid pool id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id='blah')

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_admin_state_up(self):
        """Test if a non_admin user can create a health monitor with invalid
        admin_state_up
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), admin_state_up='blah'
                          )

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_expected_codes(self):
        """Test if a non_admin user can create a health monitor with invalid
        expected_codes
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), expected_codes='blah'
                          )

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_url_path(self):
        """Test if a non_admin user can create a health monitor with invalid
        url_path
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), url_path='blah'
                          )

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_http_method(self):
        """Test if a non_admin user can create a health monitor with invalid
        http_method
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), http_method='blah')

    @test.attr(type='negative')
    def test_create_health_monitor_empty_type(self):
        """Test create health monitor with empty type"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_empty_delay(self):
        """Test create health monitor with empty delay"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay='', max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_empty_timeout(self):
        """Test create health monitor with empty timeout"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout='',
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_empty_max_retries(self):
        """Test create health monitor with empty max_retries"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries='', timeout=5,
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
    def test_create_health_monitor_empty_max_pool_id(self):
        """Test create health monitor with empty pool_id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id='')

    @test.attr(type='negative')
    def test_create_health_monitor_empty_max_admin_state_up(self):
        """Test create health monitor with empty admin_state_up"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), admin_state_up='')

    @test.attr(type='negative')
    def test_create_health_monitor_empty_max_http_method(self):
        """Test create health monitor with empty http_method"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), http_method='')

    @test.attr(type='negative')
    def test_create_health_monitor_empty_max_url_path(self):
        """Test create health monitor with empty url_path"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), url_path='')

    @test.attr(type='negative')
    def test_create_health_monitor_empty_expected_codes(self):
        """Test create health monitor with empty expected_codes"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'), expected_codes='')

    @test.attr(type='negative')
    def test_create_health_monitor_invalid_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='HTTP', delay=3, max_retries='twenty one',
                          pool_id=self.pool.get('id'))

    @test.attr(type='negative')
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

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_admin_state_up(self):
        """Test update health monitor with missing admin state field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertTrue(new_hm.get('admin_state_up'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_delay(self):
        """Test update health monitor with missing delay field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('delay'), new_hm.get('delay'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_timeout(self):
        """Test update health monitor with missing timeout field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('timeout'), new_hm.get('timeout'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_max_retries(self):
        """Test update health monitor with missing max retries field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('max_retries'), new_hm.get('max_retries'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_http_method(self):
        """Test update health monitor with missing http_method field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('http_method'), new_hm.get('http_method'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_url_path(self):
        """Test update health monitor with missing url_path field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('url_path'), new_hm.get('url_path'))

    @test.attr(type='smoke')
    def test_update_health_monitor_missing_expected_codes(self):
        """Test update health monitor with missing expected_codes field"""
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        new_hm = self._update_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('expected_codes'),
                         new_hm.get('expected_codes'))

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_attribute(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='blue')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_admin_state_up(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), admin_state_up='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_delay(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), delay='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_timeout(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), timeout='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_max_retries(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_http_method(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_url_path(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), url_path='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_invalid_expected_codes(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), expected_codes='blah')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_admin_state_up(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), admin_state_up='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_delay(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), empty_delay='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_timeout(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), timeout='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_max_retries(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_empty_http_method(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_url_path(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='')

    @test.attr(type='negative')
    def test_update_health_monitor_empty_expected_codes(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                        timeout=5, pool_id=self.pool.get('id'))

        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), expected_codes='')

    @test.attr(type='smoke')
    def test_update_health_monitor_extra_attribute(self):
        hm = self._create_health_monitor(type='HTTP', delay=3, max_retries=10,
                                         timeout=5,
                                         pool_id=self.pool.get('id'))
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), protocol='UDP')

    @test.attr(type='smoke')
    def test_delete_health_monitor(self):
        hm = self._create_health_monitor(cleanup=False, type='HTTP', delay=3,
                                         max_retries=10, timeout=5,
                                         pool_id=self.pool.get('id'))
        self._delete_health_monitor(hm.get('id'))
        self.assertRaises(ex.NotFound,
                          self.health_monitors_client.get_health_monitor,
                          hm.get('id'))
