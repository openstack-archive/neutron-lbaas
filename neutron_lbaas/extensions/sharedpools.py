# Copyright 2016 Blue Box, an IBM Company
#
# All Rights Reserved
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
from neutron_lib import exceptions as nexception

from neutron_lbaas._i18n import _


class ListenerPoolLoadbalancerMismatch(nexception.BadRequest):
    message = _("Pool %(pool_id)s is on loadbalancer %(lb_id)s.")


class ListenerDefaultPoolAlreadySet(nexception.InUse):
    message = _("Listener %(listener_id)s "
                "is already using default pool %(pool_id)s.")


class PoolMustHaveLoadbalancer(nexception.BadRequest):
    message = _("Pool must be created with a loadbalancer or listener.")


class ListenerMustHaveLoadbalancer(nexception.BadRequest):
    message = _("Listener must be created with a loadbalancer or pool.")


class ListenerAndPoolMustBeOnSameLoadbalancer(nexception.BadRequest):
    message = _("Listener and pool must be on the same loadbalancer.")


EXTENDED_ATTRIBUTES_2_0 = {
    'loadbalancers': {
        'pools': {'allow_post': False, 'allow_put': False,
                  'is_visible': True}},
    'listeners': {
        'loadbalancer_id': {'allow_post': True, 'allow_put': False,
                            'validate': {'type:uuid_or_none': None},
                            'default': None,
                            'is_visible': False},
        'default_pool_id': {'allow_post': True, 'allow_put': True,
                            'default': None,
                            'validate': {'type:uuid_or_none': None},
                            'is_visible': True}},
    'pools': {
        'listener_id': {'allow_post': True, 'allow_put': False,
                        'validate': {'type:uuid_or_none': None},
                        'default': None,
                        'is_visible': False},
        'loadbalancer_id': {'allow_post': True, 'allow_put': False,
                            'validate': {'type:uuid_or_none': None},
                            'default': None,
                            'is_visible': True},
        'loadbalancers': {'allow_post': False, 'allow_put': False,
                         'is_visible': True}}}


class Sharedpools(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Shared pools for LBaaSv2"

    @classmethod
    def get_alias(cls):
        return "shared_pools"

    @classmethod
    def get_description(cls):
        return "Allow pools to be shared among listeners for LBaaSv2"

    @classmethod
    def get_updated(cls):
        return "2016-01-20T10:00:00-00:00"

    def get_required_extensions(self):
        return ["lbaasv2"]

    def get_extended_resources(self, version):
        if version == "2.0":
            return dict(EXTENDED_ATTRIBUTES_2_0.items())
        else:
            return {}
