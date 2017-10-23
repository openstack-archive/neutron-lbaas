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

from neutron_lib import exceptions

from neutron_lbaas._i18n import _


class ModelMapException(exceptions.NeutronException):
    message = _("Unable to map model class %(target_name)s")


class LbaasException(exceptions.NeutronException):
    pass


class TLSException(LbaasException):
    pass


class NeedsPassphrase(TLSException):
    message = _("Passphrase needed to decrypt key but client "
               "did not provide one.")


class UnreadableCert(TLSException):
    message = _("Could not read X509 from PEM")


class MisMatchedKey(TLSException):
    message = _("Key and x509 certificate do not match")


class CertificateStorageException(TLSException):
    message = _('Could not store certificate: %(msg)s')


class LoadbalancerReschedulingFailed(exceptions.Conflict):
    message = _("Failed rescheduling loadbalancer %(loadbalancer_id)s: "
                "no eligible lbaas agent found.")


class BadRequestException(exceptions.BadRequest):
    message = "%(fault_string)s"


class ConflictException(exceptions.Conflict):
    message = "%(fault_string)s"


class NotAuthorizedException(exceptions.NotAuthorized):
    message = "%(fault_string)s"


class NotFoundException(exceptions.NotFound):
    message = "%(fault_string)s"


class ServiceUnavailableException(exceptions.ServiceUnavailable):
    message = "%(fault_string)s"


class UnknownException(exceptions.NeutronException):
    message = "%(fault_string)s"
