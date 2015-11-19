# Copyright 2014 Rackspace
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

from barbicanclient import client as barbican_client
import mock

import neutron_lbaas.common.cert_manager.barbican_cert_manager as bbq_common
from neutron_lbaas.common import keystone
import neutron_lbaas.tests.base as base
from oslo_config import cfg


class TestBarbicanAuth(base.BaseTestCase):

    def setUp(self):
        # Reset the client
        bbq_common.BarbicanKeystoneAuth._barbican_client = None
        keystone._SESSION = None

        super(TestBarbicanAuth, self).setUp()

    def test_get_barbican_client(self):
        # There should be no existing client
        self.assertIsNone(keystone._SESSION)

        # Mock out the keystone session and get the client
        keystone._SESSION = mock.MagicMock()
        bc1 = bbq_common.BarbicanKeystoneAuth.get_barbican_client()

        # Our returned client should also be the saved client
        self.assertIsInstance(
            bbq_common.BarbicanKeystoneAuth._barbican_client,
            barbican_client.Client
        )
        self.assertIs(
            bbq_common.BarbicanKeystoneAuth._barbican_client,
            bc1
        )

        # Getting the session again should return the same object
        bc2 = bbq_common.BarbicanKeystoneAuth.get_barbican_client()
        self.assertIs(bc1, bc2)

    def test_get_service_url(self):
        # Format: <servicename>://<region>/<resource>/<object_id>
        cfg.CONF.set_override('service_name',
                              'lbaas',
                              'service_auth')
        cfg.CONF.set_override('region',
                              'RegionOne',
                              'service_auth')
        self.assertEqual(
            'lbaas://RegionOne/LOADBALANCER/LB-ID',
            bbq_common.CertManager._get_service_url('LB-ID'))


class TestBarbicanCert(base.BaseTestCase):

    def setUp(self):
        # Certificate data
        self.certificate = "My Certificate"
        self.intermediates = "My Intermediates"
        self.private_key = "My Private Key"
        self.private_key_passphrase = "My Private Key Passphrase"

        self.certificate_secret = barbican_client.secrets.Secret(
            api=mock.MagicMock(),
            payload=self.certificate
        )
        self.intermediates_secret = barbican_client.secrets.Secret(
            api=mock.MagicMock(),
            payload=self.intermediates
        )
        self.private_key_secret = barbican_client.secrets.Secret(
            api=mock.MagicMock(),
            payload=self.private_key
        )
        self.private_key_passphrase_secret = barbican_client.secrets.Secret(
            api=mock.MagicMock(),
            payload=self.private_key_passphrase
        )

        super(TestBarbicanCert, self).setUp()

    def test_barbican_cert(self):
        container = barbican_client.containers.CertificateContainer(
            api=mock.MagicMock(),
            certificate=self.certificate_secret,
            intermediates=self.intermediates_secret,
            private_key=self.private_key_secret,
            private_key_passphrase=self.private_key_passphrase_secret
        )
        # Create a cert
        cert = bbq_common.Cert(
            cert_container=container
        )

        # Validate the cert functions
        self.assertEqual(self.certificate, cert.get_certificate())
        self.assertEqual(self.intermediates, cert.get_intermediates())
        self.assertEqual(self.private_key, cert.get_private_key())
        self.assertEqual(self.private_key_passphrase,
                         cert.get_private_key_passphrase())
