# Copyright 2015, 2016 Rackspace
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

from tempest.common import utils
from tempest.lib.common.utils import data_utils
from tempest.lib import decorators
from tempest.lib import exceptions as ex

from neutron_lbaas.tests.tempest.v2.api import base


class TestHealthMonitors(base.BaseTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Health Monitors:
        list health monitors
        create health monitor
        get health monitor
        update health monitor
        delete health monitor
    """

    @classmethod
    def resource_setup(cls):
        super(TestHealthMonitors, cls).resource_setup()
        if not utils.is_extension_enabled('lbaasv2', 'network'):
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
            protocol=cls.listener_protocol, protocol_port=80)
        cls.pool = cls._create_pool(
            protocol=cls.pool_protocol, lb_algorithm='ROUND_ROBIN',
            listener_id=cls.listener.get('id'))
        cls.create_basic_hm_kwargs = {'type': cls.hm_protocol, 'delay': 3,
                                      'max_retries': 10, 'timeout': 5,
                                      'pool_id': cls.pool.get('id')}

    def _prep_list_comparison(self, single, obj_list):
        single.pop('operating_status', None)
        for obj in obj_list:
            obj.pop('operating_status', None)
            if not single.get('updated_at') and obj.get('updated_at'):
                obj['updated_at'] = None
            self._test_provisioning_status_if_exists(single, obj)

    def test_list_health_monitors_empty(self):
        hm_list = self.health_monitors_client.list_health_monitors()
        self.assertEmpty(hm_list)

    def test_list_health_monitors_one(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        hm_list = self.health_monitors_client.list_health_monitors()
        self._prep_list_comparison(hm, hm_list)
        self.assertIn(hm, hm_list)

    @decorators.attr(type='smoke')
    def test_list_health_monitors_two(self):
        hm1 = self._create_health_monitor(**self.create_basic_hm_kwargs)
        new_listener = self._create_listener(
            loadbalancer_id=self.load_balancer.get('id'),
            protocol=self.listener_protocol, protocol_port=88)
        self.addCleanup(self._delete_listener, new_listener.get('id'))
        new_pool = self._create_pool(
            protocol=self.pool_protocol, lb_algorithm='ROUND_ROBIN',
            listener_id=new_listener.get('id'))
        self.addCleanup(self._delete_pool, new_pool.get('id'))
        hm2 = self._create_health_monitor(
            type='HTTPS',
            max_retries=3,
            delay=1,
            timeout=2,
            pool_id=new_pool.get('id'))
        hm_list = self.health_monitors_client.list_health_monitors()
        self._prep_list_comparison(hm1, hm_list)
        self._prep_list_comparison(hm2, hm_list)
        self.assertEqual(2, len(hm_list))
        self.assertIn(hm1, hm_list)
        self.assertIn(hm2, hm_list)

    @decorators.attr(type='smoke')
    def test_create_and_get_health_monitor(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self._test_provisioning_status_if_exists(hm, hm_test)
        hm.pop('operating_status', None)
        hm_test.pop('operating_status', None)
        self.assertEqual(hm, hm_test)

    def test_create_health_monitor_missing_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          pool_id=self.pool.get('id'))

    def test_create_health_monitor_missing_required_field_type(self):
        """Test if a non_admin user can create a health monitor with type
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    def test_create_health_monitor_missing_required_field_delay(self):
        """Test if a non_admin user can create a health monitor with delay
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    def test_create_health_monitor_missing_required_field_timeout(self):
        """Test if a non_admin user can create a health monitor with timeout
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          pool_id=self.pool.get('id'))

    def test_create_health_monitor_missing_required_field_max_retries(self):
        """Test if a non_admin user can create a health monitor with max_retries
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, timeout=5,
                          pool_id=self.pool.get('id'))

    def test_create_health_monitor_missing_required_field_pool_id(self):
        """Test if a non_admin user can create a health monitor with pool_id
        missing
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5)

    def test_create_health_monitor_missing_admin_state_up(self):
        """Test if a non_admin user can create a health monitor with
        admin_state_up missing
        """
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self._test_provisioning_status_if_exists(hm, hm_test)
        hm.pop('operating_status', None)
        hm_test.pop('operating_status', None)
        self.assertEqual(hm, hm_test)
        self.assertTrue(hm_test.get('admin_state_up'))

    def test_create_health_monitor_missing_http_method(self):
        """Test if a non_admin user can create a health monitor with
        http_method missing
        """
        if self.hm_protocol != 'HTTP':
            msg = "health monitor protocol must be HTTP for http_method"
            raise self.skipException(msg)
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self._test_provisioning_status_if_exists(hm, hm_test)
        hm.pop('operating_status', None)
        hm_test.pop('operating_status', None)
        self.assertEqual(hm, hm_test)
        self.assertEqual('GET', hm_test.get('http_method'))

    def test_create_health_monitor_missing_url_path(self):
        """Test if a non_admin user can create a health monitor with
        url_path missing
        """
        if self.hm_protocol != 'HTTP':
            msg = "health monitor protocol must be HTTP for url_path"
            raise self.skipException(msg)
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self._test_provisioning_status_if_exists(hm, hm_test)
        hm.pop('operating_status', None)
        hm_test.pop('operating_status', None)
        self.assertEqual(hm, hm_test)
        self.assertEqual('/', hm_test.get('url_path'))

    def test_create_health_monitor_missing_expected_codes(self):
        """Test if a non_admin user can create a health monitor with
        expected_codes missing
        """
        if self.hm_protocol != 'HTTP':
            msg = "health monitor protocol must be HTTP for expected_codes"
            raise self.skipException(msg)
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)

        hm_test = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self._test_provisioning_status_if_exists(hm, hm_test)
        hm.pop('operating_status', None)
        hm_test.pop('operating_status', None)
        self.assertEqual(hm, hm_test)
        self.assertEqual('200', hm_test.get('expected_codes'))

    @decorators.skip_because(bug="1468457")
    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_tenant_id(self):
        """Test create health monitor with invalid tenant_id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          tenant_id='blah',
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_type(self):
        """Test create health monitor with invalid type"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='blah', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_delay(self):
        """Test create health monitor with invalid delay"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay='blah', max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_max_retries(self):
        """Test create health monitor with invalid max_retries"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries='blah',
                          timeout=5, pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_timeout(self):
        """Test create health monitor with invalid timeout"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout='blah', pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_pool_id(self):
        """Test create health monitor with invalid pool id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id='blah')

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_admin_state_up(self):
        """Test if a non_admin user can create a health monitor with invalid
        admin_state_up
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          admin_state_up='blah')

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_expected_codes(self):
        """Test if a non_admin user can create a health monitor with invalid
        expected_codes
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          expected_codes='blah')

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_url_path(self):
        """Test if a non_admin user can create a health monitor with invalid
        url_path
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          url_path='blah')

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_http_method(self):
        """Test if a non_admin user can create a health monitor with invalid
        http_method
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          http_method='blah')

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_type(self):
        """Test create health monitor with empty type"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type='', delay=3, max_retries=10, timeout=5,
                          pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_delay(self):
        """Test create health monitor with empty delay"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay='', max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_timeout(self):
        """Test create health monitor with empty timeout"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout='', pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_max_retries(self):
        """Test create health monitor with empty max_retries"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries='',
                          timeout=5, pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_max_pool_id(self):
        """Test create health monitor with empty pool_id"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id='')

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_max_admin_state_up(self):
        """Test create health monitor with empty admin_state_up"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          admin_state_up='')

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_max_http_method(self):
        """Test create health monitor with empty http_method"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          http_method='')

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_max_url_path(self):
        """Test create health monitor with empty url_path"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'), url_path='')

    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_expected_codes(self):
        """Test create health monitor with empty expected_codes"""
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'),
                          expected_codes='')

    @decorators.attr(type='negative')
    def test_create_health_monitor_invalid_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3,
                          max_retries='twenty one',
                          pool_id=self.pool.get('id'))

    @decorators.attr(type='negative')
    def test_create_health_monitor_extra_attribute(self):
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          pool_id=self.pool.get('id'), subnet_id=10)

    @decorators.attr(type='smoke')
    def test_update_health_monitor(self):
        hm = self._create_health_monitor(type=self.hm_protocol, delay=3,
                                         max_retries=10, timeout=5,
                                         pool_id=self.pool.get('id'))
        max_retries = 1
        self._update_health_monitor(hm.get('id'), max_retries=max_retries)
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(max_retries, new_hm.get('max_retries'))

    def test_update_health_monitor_missing_admin_state_up(self):
        """Test update health monitor with missing admin state field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertTrue(new_hm.get('admin_state_up'))

    def test_update_health_monitor_missing_delay(self):
        """Test update health monitor with missing delay field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('delay'), new_hm.get('delay'))

    def test_update_health_monitor_missing_timeout(self):
        """Test update health monitor with missing timeout field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('timeout'), new_hm.get('timeout'))

    def test_update_health_monitor_missing_max_retries(self):
        """Test update health monitor with missing max retries field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('max_retries'), new_hm.get('max_retries'))

    def test_update_health_monitor_missing_http_method(self):
        """Test update health monitor with missing http_method field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('http_method'), new_hm.get('http_method'))

    def test_update_health_monitor_missing_url_path(self):
        """Test update health monitor with missing url_path field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('url_path'), new_hm.get('url_path'))

    def test_update_health_monitor_missing_expected_codes(self):
        """Test update health monitor with missing expected_codes field"""
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self._update_health_monitor(hm.get('id'))
        new_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        self.assertEqual(hm.get('expected_codes'),
                         new_hm.get('expected_codes'))

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_attribute(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='blue')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_admin_state_up(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), admin_state_up='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_delay(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), delay='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_timeout(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), timeout='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_max_retries(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_http_method(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_url_path(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), url_path='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_invalid_expected_codes(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), expected_codes='blah')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_admin_state_up(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), admin_state_up='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_delay(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), empty_delay='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_timeout(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), timeout='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_max_retries(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), max_retries='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_empty_http_method(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_url_path(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), http_method='')

    @decorators.attr(type='negative')
    def test_update_health_monitor_empty_expected_codes(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), expected_codes='')

    def test_update_health_monitor_extra_attribute(self):
        hm = self._create_health_monitor(**self.create_basic_hm_kwargs)
        self.assertRaises(ex.BadRequest,
                          self._update_health_monitor,
                          hm.get('id'), protocol='UDP')

    @decorators.attr(type='smoke')
    def test_delete_health_monitor(self):
        hm = self._create_health_monitor(cleanup=False, type=self.hm_protocol,
                                         delay=3, max_retries=10, timeout=5,
                                         pool_id=self.pool.get('id'))
        self._delete_health_monitor(hm.get('id'))
        self.assertRaises(ex.NotFound,
                          self.health_monitors_client.get_health_monitor,
                          hm.get('id'))
