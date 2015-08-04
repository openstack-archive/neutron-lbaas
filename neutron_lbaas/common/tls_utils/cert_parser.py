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
import neutron_lbaas.common.exceptions as exceptions
from OpenSSL import crypto
from OpenSSL import SSL
import pyasn1.codec.der.decoder as decoder
import pyasn1_modules.rfc2459 as rfc2459
import six

X509_BEG = "-----BEGIN CERTIFICATE-----"
X509_END = "-----END CERTIFICATE-----"


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
    x509 = _get_x509_from_pem_bytes(certificate)
    if intermediates:
        for x509Pem in _split_x509s(intermediates):
            _get_x509_from_pem_bytes(x509Pem)
    if private_key:
        pkey = _read_privatekey(private_key, passphrase=private_key_passphrase)
        ctx = SSL.Context(SSL.TLSv1_METHOD)
        ctx.use_certificate(x509)
        try:
            ctx.use_privatekey(pkey)
            ctx.check_privatekey()
        except Exception:
            raise exceptions.MisMatchedKey
    return True


def _read_privatekey(privatekey_pem, passphrase=None):
    def cb(*args):
        if passphrase:
            if six.PY2:
                return passphrase.encode("utf-8")
            elif six.PY3:
                return six.b(passphrase)
        else:
            raise exceptions.NeedsPassphrase
    return crypto.load_privatekey(crypto.FILETYPE_PEM, privatekey_pem, cb)


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
        kw["password"] = private_key_passphrase.encode("utf-8")
    else:
        kw["password"] = None
    try:
        pk = serialization.load_pem_private_key(private_key.encode('ascii'),
                                                **kw)
        return pk
    except TypeError as ex:
        if len(ex.args) > 0 and ex.args[0].startswith("Password"):
            raise exceptions.NeedsPassphrase


def dump_private_key(private_key, private_key_passphrase=None):
    """
    Parses encrypted key to provide an unencrypted version in PKCS8

    :param private_key: private key
    :param private_key_passphrase: private key passphrase
    :return: Unencrypted private key in PKCS8
    """

    # re encode the key as unencrypted PKCS8
    pk = _read_pyca_private_key(private_key,
                                private_key_passphrase=private_key_passphrase)
    key = pk.private_bytes(encoding=serialization.Encoding.PEM,
                           format=serialization.PrivateFormat.PKCS8,
                           encryption_algorithm=serialization.NoEncryption())
    return key


def get_host_names(certificate):
    """
    Extract the host names from the Pem encoded X509 certificate

    :param certificate: A PEM encoded certificate
    :returns: A dictionary containing the following keys:
    ['cn', 'dns_names']
    where 'cn' is the CN from the SubjectName of the certificate, and
    'dns_names' is a list of dNSNames (possibly empty) from
    the SubjectAltNames of the certificate.
    """

    x509 = _get_x509_from_pem_bytes(certificate)
    hostNames = {}
    if hasattr(x509.get_subject(), 'CN'):
        hostNames['cn'] = x509.get_subject().CN
    hostNames['dns_names'] = []
    num_exts = x509.get_extension_count()
    for i in range(0, num_exts):
        ext = x509.get_extension(i)
        short_name = ext.get_short_name()
        if short_name == six.b('subjectAltName'):
            data = ext.get_data()
            general_names_container = decoder.decode(
                data, asn1Spec=rfc2459.GeneralNames())
            for general_names in general_names_container[0]:
                currName = general_names.getName()
                if currName == 'dNSName':
                    octets = general_names.getComponent().asOctets()
                    decoded = octets.decode("utf-8")
                    hostNames['dns_names'].append(decoded)
    return hostNames


def _get_x509_from_pem_bytes(certificate_pem):
    """
    Parse X509 data from a PEM encoded certificate

    :param certificate_pem: Certificate in PEM format
    :returns: pyOpenSSL high-level x509 data from the PEM string
    """
    try:
        x509 = crypto.load_certificate(crypto.FILETYPE_PEM,
                                       certificate_pem)
    except Exception:
        raise exceptions.UnreadableCert
    return x509
