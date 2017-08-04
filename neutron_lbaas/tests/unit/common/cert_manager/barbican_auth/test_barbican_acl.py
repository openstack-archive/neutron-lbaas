# Copyright 2014-2016 Rackspace
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

import mock

from neutron_lbaas.common.cert_manager.barbican_auth import barbican_acl
from neutron_lbaas.common.cert_manager import barbican_cert_manager
from neutron_lbaas.common import keystone
import neutron_lbaas.tests.base as base


class TestBarbicanACLAuth(base.BaseTestCase):
    def setUp(self):
        # Reset the client
        keystone._SESSION = None

        super(TestBarbicanACLAuth, self).setUp()

    def test_get_barbican_client(self):
        # There should be no existing client
        self.assertIsNone(keystone._SESSION)

        # Mock out the keystone session and get the client
        keystone._SESSION = mock.MagicMock()
        acl_auth_object = barbican_acl.BarbicanACLAuth()
        bc1 = acl_auth_object.get_barbican_client()

        # Our returned object should have elements that proves it is a real
        # Barbican client object. We shouldn't use `isinstance` because that's
        # an evil pattern, instead we can check for very unique things in the
        # stable client API like "register_consumer", since this should fairly
        # reliably prove we're dealing with a Barbican client.
        self.assertTrue(hasattr(bc1, 'containers') and
                        hasattr(bc1.containers, 'register_consumer'))

        # Getting the session again with new class should get the same object
        acl_auth_object2 = barbican_acl.BarbicanACLAuth()
        bc2 = acl_auth_object2.get_barbican_client()
        self.assertIs(bc1, bc2)

    def test_load_auth_driver(self):
        bcm = barbican_cert_manager.CertManager()
        self.assertIsInstance(bcm.auth, barbican_acl.BarbicanACLAuth)
