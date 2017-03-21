# Copyright 2015 Radware LTD.
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


from neutron_lbaas._i18n import _
from neutron_lbaas.common import exceptions


class RadwareLBaasV2Exception(exceptions.LbaasException):
    message = _('An unknown exception occurred in '
               'Radware LBaaS v2 provider.')


class AuthenticationMissing(RadwareLBaasV2Exception):
    message = _('vDirect user/password missing. '
               'Specify in configuration file, under [radwarev2] section')


class WorkflowTemplateMissing(RadwareLBaasV2Exception):
    message = _('Workflow template %(workflow_template)s is missing '
               'on vDirect server. Upload missing workflow')


class RESTRequestFailure(RadwareLBaasV2Exception):
    message = _('REST request failed with status %(status)s. '
               'Reason: %(reason)s, Description: %(description)s. '
               'Success status codes are %(success_codes)s')


class UnsupportedEntityOperation(RadwareLBaasV2Exception):
    message = _('%(operation)s operation is not supported for %(entity)s.')
