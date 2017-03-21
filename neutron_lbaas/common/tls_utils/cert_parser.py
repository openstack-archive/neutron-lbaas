#
# Copyright 2014 OpenStack Foundation.  All rights reserved
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

from cryptography.hazmat import backends
from cryptography.hazmat.primitives import serialization
from cryptography import x509
from oslo_log import log as logging
from oslo_utils import encodeutils

import neutron_lbaas.common.exceptions as exceptions

X509_BEG = "-----BEGIN CERTIFICATE-----"
X509_END = "-----END CERTIFICATE-----"

LOG = logging.getLogger(__name__)


def validate_cert(certificate, private_key=None,
                  private_key_passphrase=None, intermediates=None):
    """
    Validate that the certificate is a valid PEM encoded X509 object

    Optionally verify that the private key matches the certificate.
    Optionally verify that the intermediates are valid X509 objects.

    :param certificate: A PEM encoded certificate
    :param private_key: The private key for the certificate
    :param private_key_passphrase: Passphrase for accessing the private key
    :param intermediates: PEM encoded intermediate certificates
    :returns: boolean
    """

    cert = _get_x509_from_pem_bytes(certificate)
    if intermediates:
        for x509Pem in _split_x509s(intermediates):
            _get_x509_from_pem_bytes(x509Pem)
    if private_key:
        pkey = _read_privatekey(private_key, passphrase=private_key_passphrase)
        pknum = pkey.public_key().public_numbers()
        certnum = cert.public_key().public_numbers()
        if pknum != certnum:
            raise exceptions.MisMatchedKey
    return True


def _read_privatekey(privatekey_pem, passphrase=None):
    if passphrase is not None:
        passphrase = encodeutils.to_utf8(passphrase)
    privatekey_pem = privatekey_pem.encode('ascii')

    try:
        return serialization.load_pem_private_key(privatekey_pem, passphrase,
                                                  backends.default_backend())
    except Exception:
        raise exceptions.NeedsPassphrase


def _split_x509s(x509Str):
    """
    Split the input string into individb(ual x509 text blocks

    :param x509Str: A large multi x509 certificate blcok
    :returns: A list of strings where each string represents an
    X509 pem block surrounded by BEGIN CERTIFICATE,
    END CERTIFICATE block tags
    """
    curr_pem_block = []
    inside_x509 = False
    for line in x509Str.replace("\r", "").split("\n"):
        if inside_x509:
            curr_pem_block.append(line)
            if line == X509_END:
                yield "\n".join(curr_pem_block)
                curr_pem_block = []
                inside_x509 = False
            continue
        else:
            if line == X509_BEG:
                curr_pem_block.append(line)
                inside_x509 = True


def _read_pyca_private_key(private_key, private_key_passphrase=None):
    kw = {"password": None,
          "backend": backends.default_backend()}
    if private_key_passphrase is not None:
        kw["password"] = encodeutils.to_utf8(private_key_passphrase)
    else:
        kw["password"] = None
    private_key = encodeutils.to_utf8(private_key)
    try:
        pk = serialization.load_pem_private_key(private_key, **kw)
        return pk
    except TypeError as ex:
        if len(ex.args) > 0 and ex.args[0].startswith("Password"):
            raise exceptions.NeedsPassphrase


def dump_private_key(private_key, private_key_passphrase=None):
    """
    Parses encrypted key to provide an unencrypted version in PKCS8

    :param private_key: private key
    :param private_key_passphrase: private key passphrase
    :returns: Unencrypted private key in PKCS8
    """

    # re encode the key as unencrypted PKCS8
    pk = _read_pyca_private_key(private_key,
                                private_key_passphrase=private_key_passphrase)
    key = pk.private_bytes(encoding=serialization.Encoding.PEM,
                           format=serialization.PrivateFormat.PKCS8,
                           encryption_algorithm=serialization.NoEncryption())
    return key


def get_host_names(certificate):
    """Extract the host names from the Pem encoded X509 certificate

    :param certificate: A PEM encoded certificate
    :returns: A dictionary containing the following keys:
    ['cn', 'dns_names']
    where 'cn' is the CN from the SubjectName of the certificate, and
    'dns_names' is a list of dNSNames (possibly empty) from
    the SubjectAltNames of the certificate.
    """
    try:
        certificate = certificate.encode('ascii')

        cert = _get_x509_from_pem_bytes(certificate)
        cn = cert.subject.get_attributes_for_oid(x509.OID_COMMON_NAME)[0]
        host_names = {
            'cn': cn.value.lower(),
            'dns_names': []
        }
        try:
            ext = cert.extensions.get_extension_for_oid(
                x509.OID_SUBJECT_ALTERNATIVE_NAME
            )
            host_names['dns_names'] = ext.value.get_values_for_type(
                x509.DNSName)
        except x509.ExtensionNotFound:
            LOG.debug("%s extension not found",
                      x509.OID_SUBJECT_ALTERNATIVE_NAME)

        return host_names
    except Exception:
        LOG.exception("Unreadable certificate.")
        raise exceptions.UnreadableCert


def _get_x509_from_pem_bytes(certificate_pem):
    """
    Parse X509 data from a PEM encoded certificate

    :param certificate_pem: Certificate in PEM format
    :returns: crypto high-level x509 data from the PEM string
    """
    certificate = encodeutils.to_utf8(certificate_pem)
    try:
        x509cert = x509.load_pem_x509_certificate(certificate,
                                                  backends.default_backend())
    except Exception:
        raise exceptions.UnreadableCert
    return x509cert
