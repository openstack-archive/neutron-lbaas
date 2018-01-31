# Copyright 2014, 2015 Rackspace US, Inc.
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

import os

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils

from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.common import exceptions

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

TLS_STORAGE_DEFAULT = os.environ.get(
    'OS_LBAAS_TLS_STORAGE', '/var/lib/neutron-lbaas/certificates/'
)

local_cert_manager_opts = [
    cfg.StrOpt('storage_path',
               default=TLS_STORAGE_DEFAULT,
               deprecated_for_removal=True,
               deprecated_since='Queens',
               deprecated_reason='The neutron-lbaas project is now '
                                 'deprecated. See: https://wiki.openstack.org/'
                                 'wiki/Neutron/LBaaS/Deprecation',
               help='Absolute path to the certificate storage directory. '
                    'Defaults to env[OS_LBAAS_TLS_STORAGE].')
]

CONF.register_opts(local_cert_manager_opts, group='certificates')


class Cert(cert_manager.Cert):
    """Representation of a Cert for local storage."""

    def __init__(self, certificate, private_key, intermediates=None,
                 private_key_passphrase=None):
        self.certificate = certificate
        self.intermediates = intermediates
        self.private_key = private_key
        self.private_key_passphrase = private_key_passphrase

    def get_certificate(self):
        return self.certificate

    def get_intermediates(self):
        return self.intermediates

    def get_private_key(self):
        return self.private_key

    def get_private_key_passphrase(self):
        return self.private_key_passphrase


class CertManager(cert_manager.CertManager):
    """Cert Manager Interface that stores data locally."""

    def store_cert(self, project_id, certificate, private_key,
                   intermediates=None, private_key_passphrase=None, **kwargs):
        """Stores (i.e., registers) a cert with the cert manager.

        This method stores the specified cert to the filesystem and returns
        a UUID that can be used to retrieve it.

        :param project_id: Project ID for the owner of the certificate
        :param certificate: PEM encoded TLS certificate
        :param private_key: private key for the supplied certificate
        :param intermediates: ordered and concatenated intermediate certs
        :param private_key_passphrase: optional passphrase for the supplied key

        :returns: the UUID of the stored cert
        :raises CertificateStorageException: if certificate storage fails
        """
        cert_ref = uuidutils.generate_uuid()
        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)

        LOG.info("Storing certificate data on the local filesystem.")
        try:
            filename_certificate = "{0}.crt".format(filename_base)
            with open(filename_certificate, 'w') as cert_file:
                cert_file.write(certificate)

            filename_private_key = "{0}.key".format(filename_base)
            with open(filename_private_key, 'w') as key_file:
                key_file.write(private_key)

            if intermediates:
                filename_intermediates = "{0}.int".format(filename_base)
                with open(filename_intermediates, 'w') as int_file:
                    int_file.write(intermediates)

            if private_key_passphrase:
                filename_pkp = "{0}.pass".format(filename_base)
                with open(filename_pkp, 'w') as pass_file:
                    pass_file.write(private_key_passphrase)
        except IOError as ioe:
            LOG.error("Failed to store certificate.")
            raise exceptions.CertificateStorageException(message=ioe.message)

        return cert_ref

    def get_cert(self, project_id, cert_ref, resource_ref, **kwargs):
        """Retrieves the specified cert.

        :param project_id: Project ID for the owner of the certificate
        :param cert_ref: the UUID of the cert to retrieve
        :param resource_ref: Full HATEOAS reference to the consuming resource

        :returns: neutron_lbaas.common.cert_manager.cert_manager.Cert
                 representation of the certificate data
        :raises CertificateStorageException: if certificate retrieval fails
        """
        LOG.info((
            "Loading certificate {0} from the local filesystem."
        ).format(cert_ref))

        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)

        filename_certificate = "{0}.crt".format(filename_base)
        filename_private_key = "{0}.key".format(filename_base)
        filename_intermediates = "{0}.int".format(filename_base)
        filename_pkp = "{0}.pass".format(filename_base)

        cert_data = dict()

        try:
            with open(filename_certificate, 'r') as cert_file:
                cert_data['certificate'] = cert_file.read()
        except IOError:
            LOG.error((
                "Failed to read certificate for {0}."
            ).format(cert_ref))
            raise exceptions.CertificateStorageException(
                msg="Certificate could not be read."
            )
        try:
            with open(filename_private_key, 'r') as key_file:
                cert_data['private_key'] = key_file.read()
        except IOError:
            LOG.error((
                "Failed to read private key for {0}."
            ).format(cert_ref))
            raise exceptions.CertificateStorageException(
                msg="Private Key could not be read."
            )

        try:
            with open(filename_intermediates, 'r') as int_file:
                cert_data['intermediates'] = int_file.read()
        except IOError:
            pass

        try:
            with open(filename_pkp, 'r') as pass_file:
                cert_data['private_key_passphrase'] = pass_file.read()
        except IOError:
            pass

        return Cert(**cert_data)

    def delete_cert(self, project_id, cert_ref, resource_ref, **kwargs):
        """Deletes the specified cert.

        :param project_id: Project ID for the owner of the certificate
        :param cert_ref: the UUID of the cert to delete
        :param resource_ref: Full HATEOAS reference to the consuming resource

        :raises CertificateStorageException: if certificate deletion fails
        """
        LOG.info((
            "Deleting certificate {0} from the local filesystem."
        ).format(cert_ref))

        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)

        filename_certificate = "{0}.crt".format(filename_base)
        filename_private_key = "{0}.key".format(filename_base)
        filename_intermediates = "{0}.int".format(filename_base)
        filename_pkp = "{0}.pass".format(filename_base)

        try:
            os.remove(filename_certificate)
            os.remove(filename_private_key)
            os.remove(filename_intermediates)
            os.remove(filename_pkp)
        except IOError as ioe:
            LOG.error((
                "Failed to delete certificate {0}."
            ).format(cert_ref))
            raise exceptions.CertificateStorageException(message=ioe.message)
