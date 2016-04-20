# Copyright 2013 OpenStack Foundation
# Copyright 2016 Rackspace Inc.
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

from tempest.lib.common.utils import data_utils
from tempest.lib import exceptions
from tempest import test

from neutron_lbaas.tests.tempest.v1.api import base


class QuotasTest(base.BaseAdminNetworkTest):
    _interface = 'json'

    """
    Tests the following operations in the Neutron API using the REST client for
    Neutron:

        list quotas for tenants who have non-default quota values
        show quotas for a specified tenant
        update quotas for a specified tenant
        reset quotas to default values for a specified tenant

    v2.0 of the API is assumed.
    It is also assumed that the per-tenant quota extension API is configured
    in /etc/neutron/neutron.conf as follows:

        quota_driver = neutron.db.quota_db.DbQuotaDriver
    """

    @classmethod
    def skip_checks(cls):
        super(QuotasTest, cls).skip_checks()
        if not test.is_extension_enabled('quotas', 'network'):
            msg = "quotas extension not enabled."
            raise cls.skipException(msg)

    def _check_quotas(self, new_quotas):
        # Add a tenant to conduct the test
        test_tenant = data_utils.rand_name('test_tenant_')
        test_description = data_utils.rand_name('desc_')
        tenant = self.identity_admin_client.create_tenant(
            name=test_tenant,
            description=test_description)
        tenant_id = tenant['tenant']['id']
        self.addCleanup(self.identity_admin_client.delete_tenant, tenant_id)

        # Change quotas for tenant
        quota_set = self.admin_client.update_quotas(tenant_id,
                                                    **new_quotas)

        def safe_reset_quotas(tenant_id):
            try:
                self.admin_client.reset_quotas(tenant_id)
            except exceptions.NotFound:
                pass

        self.addCleanup(safe_reset_quotas, tenant_id)
        for key, value in new_quotas.items():
            self.assertEqual(value, quota_set[key])

        # Confirm our tenant is listed among tenants with non default quotas
        non_default_quotas = self.admin_client.list_quotas()
        found = False
        for qs in non_default_quotas['quotas']:
            if qs['tenant_id'] == tenant_id:
                found = True
        self.assertTrue(found)

        # Confirm from API quotas were changed as requested for tenant
        quota_set = self.admin_client.show_quotas(tenant_id)
        quota_set = quota_set['quota']
        for key, value in new_quotas.items():
            self.assertEqual(value, quota_set[key])

        # Reset quotas to default and confirm
        self.admin_client.reset_quotas(tenant_id)
        non_default_quotas = self.admin_client.list_quotas()
        for q in non_default_quotas['quotas']:
            self.assertNotEqual(tenant_id, q['tenant_id'])

    @test.attr(type='gate')
    def test_quotas(self):
        new_quotas = {'network': 0, 'security_group': 0}
        self._check_quotas(new_quotas)

    @test.requires_ext(extension='lbaas', service='network')
    @test.attr(type='gate')
    def test_lbaas_quotas(self):
        new_quotas = {'vip': 1, 'pool': 2,
                      'member': 3, 'health_monitor': 4}
        self._check_quotas(new_quotas)
