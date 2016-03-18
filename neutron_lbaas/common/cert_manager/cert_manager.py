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

"""
Certificate manager API
"""
import abc

from oslo_config import cfg
import six

cfg.CONF.import_group('service_auth', 'neutron_lbaas.common.keystone')


@six.add_metaclass(abc.ABCMeta)
class Cert(object):
    """Base class to represent all certificates."""

    @abc.abstractmethod
    def get_certificate(self):
        """Returns the certificate."""
        pass

    @abc.abstractmethod
    def get_intermediates(self):
        """Returns the intermediate certificates."""
        pass

    @abc.abstractmethod
    def get_private_key(self):
        """Returns the private key for the certificate."""
        pass

    @abc.abstractmethod
    def get_private_key_passphrase(self):
        """Returns the passphrase for the private key."""
        pass


@six.add_metaclass(abc.ABCMeta)
class CertManager(object):
    """Base Cert Manager Interface

    A Cert Manager is responsible for managing certificates for TLS.
    """

    @abc.abstractmethod
    def store_cert(self, project_id, certificate, private_key,
                   intermediates=None, private_key_passphrase=None,
                   expiration=None, name=None):
        """Stores (i.e., registers) a cert with the cert manager.

        This method stores the specified cert and returns its UUID that
        identifies it within the cert manager.
        If storage of the certificate data fails, a CertificateStorageException
        should be raised.
        """
        pass

    @abc.abstractmethod
    def get_cert(self, project_id, cert_ref, resource_ref,
                 check_only=False, service_name=None):
        """Retrieves the specified cert.

        If check_only is True, don't perform any sort of registration.
        If the specified cert does not exist, a CertificateStorageException
        should be raised.
        """
        pass

    @abc.abstractmethod
    def delete_cert(self, project_id, cert_ref, resource_ref,
                    service_name=None):
        """Deletes the specified cert.

        If the specified cert does not exist, a CertificateStorageException
        should be raised.
        """
        pass

    @classmethod
    def get_service_url(cls, loadbalancer_id):
        # Format: <servicename>://<region>/<resource>/<object_id>
        return "{0}://{1}/{2}/{3}".format(
            cfg.CONF.service_auth.service_name,
            cfg.CONF.service_auth.region,
            "loadbalancer",
            loadbalancer_id
        )
