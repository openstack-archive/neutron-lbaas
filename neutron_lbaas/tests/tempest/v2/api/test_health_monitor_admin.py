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

from oslo_utils import uuidutils
from tempest.common import utils
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib import decorators
from tempest.lib import exceptions as ex

from neutron_lbaas.tests.tempest.v2.api import base

CONF = config.CONF


class TestHealthMonitors(base.BaseAdminTestCase):

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Health Monitors with ADMIN role:

    create health monitor with missing tenant_id
    create health monitor with empty tenant id
    create health monitor with another tenant_id
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

    @classmethod
    def resource_cleanup(cls):
        super(TestHealthMonitors, cls).resource_cleanup()

    def test_create_health_monitor_missing_tenant_id_field(self):
        """
        Test if admin user can create health monitor with a missing tenant id
        field.
        """
        hm = self._create_health_monitor(type=self.hm_protocol, delay=3,
                                         max_retries=10, timeout=5,
                                         pool_id=self.pool.get('id'))

        admin_hm = self.health_monitors_client.get_health_monitor(hm.get('id'))
        admin_tenant_id = admin_hm.get('tenant_id')
        hm_tenant_id = hm.get('tenant_id')
        self.assertEqual(admin_tenant_id, hm_tenant_id)

    @decorators.skip_because(bug="1468457")
    @decorators.attr(type='negative')
    def test_create_health_monitor_empty_tenant_id_field(self):
        """
        Test with admin user creating health monitor with an empty tenant id
        field should fail.
        """
        self.assertRaises(ex.BadRequest, self._create_health_monitor,
                          type=self.hm_protocol, delay=3, max_retries=10,
                          timeout=5, pool_id=self.pool.get('id'), tenant_id="")

    @decorators.skip_because(bug="1468457")
    @decorators.attr(type='smoke')
    def test_create_health_monitor_for_another_tenant_id_field(self):
        """Test with admin user create health monitor for another tenant id.
        """

        tenantid = uuidutils.generate_uuid()
        hm = self._create_health_monitor(type=self.hm_protocol, delay=3,
                                         max_retries=10, timeout=5,
                                         pool_id=self.pool.get('id'),
                                         tenant_id=tenantid)

        self.assertEqual(hm.get('tenant_id'), tenantid)
        self.assertNotEqual(hm.get('tenant_id'),
                            self.subnet.get('tenant_id'))
