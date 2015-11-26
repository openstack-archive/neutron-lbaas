# Copyright 2013 OpenStack Foundation.  All rights reserved
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
#

"""
Neutron Lbaas base exception handling.
"""

from neutron.common import exceptions

from neutron_lbaas._i18n import _LE


class LbaasException(exceptions.NeutronException):
    pass


class TLSException(LbaasException):
    pass


class NeedsPassphrase(TLSException):
    message = _LE("Passphrase needed to decrypt key but client "
                  "did not provide one.")


class UnreadableCert(TLSException):
    message = _LE("Could not read X509 from PEM")


class MisMatchedKey(TLSException):
    message = _LE("Key and x509 certificate do not match")


class CertificateStorageException(TLSException):
    message = _LE('Could not store certificate: %(msg)s')
