# Copyright 2016 A10 Networks
# All rights reserved.
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

from neutron_lib.api import extensions
from neutron_lib import constants as n_constants
from neutron_lib import exceptions as nexception

from neutron_lbaas._i18n import _

EXTENDED_ATTRIBUTES_2_0 = {
    'loadbalancers': {
        'vip_subnet_id': {'allow_post': True, 'allow_put': False,
                          'validate': {'type:uuid': None},
                          'is_visible': True,
                          'default': n_constants.ATTR_NOT_SPECIFIED},
        'vip_network_id': {'allow_post': True, 'allow_put': False,
                           'validate': {'type:uuid': None},
                           'is_visible': False,
                           'default': n_constants.ATTR_NOT_SPECIFIED}
    }
}


class VipNetworkInvalid(nexception.BadRequest):
    message = _("VIP network %(network)s is invalid. "
                "There is no subnet in VIP network specified.")


class Lb_network_vip(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Create loadbalancer with network_id"

    @classmethod
    def get_alias(cls):
        return "lb_network_vip"

    @classmethod
    def get_description(cls):
        return "Create loadbalancer with network_id"

    @classmethod
    def get_updated(cls):
        return "2016-09-09T22:00:00-00:00"

    def get_required_extensions(self):
        return ["lbaasv2"]

    def get_extended_resources(self, version):
        if version == "2.0":
            return EXTENDED_ATTRIBUTES_2_0
        else:
            return {}
