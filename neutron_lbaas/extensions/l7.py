# Copyright 2016 Radware LTD
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

from neutron_lib.api import converters
from neutron_lib.api import extensions as api_extensions
from neutron_lib import constants as n_constants
from neutron_lib.db import constants as db_const
from neutron_lib import exceptions as nexception
from neutron_lib.plugins import constants
from neutron_lib.plugins import directory

from neutron.api import extensions
from neutron.api.v2 import base
from neutron.api.v2 import resource_helper

from neutron_lbaas._i18n import _
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const

LOADBALANCERV2_PREFIX = "/lbaas"


class L7PolicyRedirectPoolIdMissing(nexception.Conflict):
    message = _("Redirect pool id is missing for L7 Policy with"
                " pool redirect action.")


class L7PolicyRedirectUrlMissing(nexception.Conflict):
    message = _("Redirect URL is missing for L7 Policy with"
                " URL redirect action.")


class RuleNotFoundForL7Policy(nexception.NotFound):
    message = _("Rule %(rule_id)s could not be found in"
                " l7 policy %(l7policy_id)s.")


class L7RuleKeyMissing(nexception.NotFound):
    message = _("Rule key is missing."
                " Key should be specified for rules of "
                "HEADER and COOKIE types.")


class L7RuleInvalidKey(nexception.BadRequest):
    message = _("Invalid characters in key. See RFCs 2616, 2965, 6265, 7230.")


class L7RuleInvalidHeaderValue(nexception.BadRequest):
    message = _("Invalid characters in value. See RFC 7230.")


class L7RuleInvalidCookieValue(nexception.BadRequest):
    message = _("Invalid characters in value. See RFCs 2616, 2965, 6265.")


class L7RuleInvalidRegex(nexception.BadRequest):
    message = _("Unable to parse regular expression: %(e)s.")


class L7RuleUnsupportedCompareType(nexception.BadRequest):
    message = _("Unsupported compare type for rule of %(type)s type.")


RESOURCE_ATTRIBUTE_MAP = {
    'l7policies': {
        'id': {'allow_post': False, 'allow_put': False,
               'validate': {'type:uuid': None},
               'is_visible': True,
               'primary_key': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:string': db_const.NAME_FIELD_SIZE},
                      'required_by_policy': True,
                      'is_visible': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'validate': {'type:string': None},
                 'default': '',
                 'is_visible': True},
        'description': {'allow_post': True, 'allow_put': True,
                        'validate': {
                            'type:string': db_const.DESCRIPTION_FIELD_SIZE},
                        'is_visible': True, 'default': ''},
        'listener_id': {'allow_post': True, 'allow_put': False,
                        'validate': {'type:uuid': None},
                        'is_visible': True},
        'action': {'allow_post': True, 'allow_put': True,
                   'validate': {
                       'type:values': lb_const.SUPPORTED_L7_POLICY_ACTIONS},
                   'is_visible': True},
        'redirect_pool_id': {'allow_post': True, 'allow_put': True,
                             'validate': {'type:uuid_or_none': None},
                             'default': n_constants.ATTR_NOT_SPECIFIED,
                             'is_visible': True},
        'redirect_url': {'allow_post': True, 'allow_put': True,
                         'validate': {
                             'type:regex_or_none': lb_const.URL_REGEX},
                         'default': None,
                         'is_visible': True},
        # range max is (2^31 - 1) to get around MySQL quirk
        'position': {'allow_post': True, 'allow_put': True,
                     'convert_to': converters.convert_to_int,
                     'validate': {'type:range': [1, 2147483647]},
                     'default': 2147483647,
                     'is_visible': True},
        'rules': {'allow_post': False, 'allow_put': False,
                 'is_visible': True},
        'admin_state_up': {'allow_post': True, 'allow_put': True,
                           'default': True,
                           'convert_to': converters.convert_to_boolean,
                           'is_visible': True},
        'status': {'allow_post': False, 'allow_put': False,
                   'is_visible': True}
    }
}

SUB_RESOURCE_ATTRIBUTE_MAP = {
    'rules': {
        'parent': {'collection_name': 'l7policies',
                   'member_name': 'l7policy'},
        'parameters': {
            'id': {'allow_post': False, 'allow_put': False,
                   'validate': {'type:uuid': None},
                   'is_visible': True,
                   'primary_key': True},
            'tenant_id': {'allow_post': True, 'allow_put': False,
                          'validate': {'type:string': None},
                          'required_by_policy': True,
                          'is_visible': True},
            'type': {'allow_post': True, 'allow_put': True,
                     'validate': {
                         'type:values': lb_const.SUPPORTED_L7_RULE_TYPES},
                     'is_visible': True},
            'compare_type': {'allow_post': True, 'allow_put': True,
                             'validate': {
                                 'type:values':
                                 lb_const.SUPPORTED_L7_RULE_COMPARE_TYPES},
                             'is_visible': True},
            'invert': {'allow_post': True, 'allow_put': True,
                       'default': False,
                       'convert_to': converters.convert_to_boolean,
                       'is_visible': True},
            'key': {'allow_post': True, 'allow_put': True,
                    'validate': {'type:string_or_none': None},
                    'default': None,
                    'is_visible': True},
            'value': {'allow_post': True, 'allow_put': True,
                      'validate': {'type:string': None},
                      'is_visible': True},
            'admin_state_up': {'allow_post': True, 'allow_put': True,
                               'default': True,
                               'convert_to': converters.convert_to_boolean,
                               'is_visible': True},
            'status': {'allow_post': False, 'allow_put': False,
                       'is_visible': True}
        }
    }
}


class L7(api_extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "L7 capabilities for LBaaSv2"

    @classmethod
    def get_alias(cls):
        return "l7"

    @classmethod
    def get_description(cls):
        return "Adding L7 policies and rules support for LBaaSv2"

    @classmethod
    def get_updated(cls):
        return "2016-01-24T10:00:00-00:00"

    def get_required_extensions(self):
        return ["lbaasv2"]

    @classmethod
    def get_resources(cls):
        l7_plurals = {'l7policies': 'l7policy', 'rules': 'rule'}

        plural_mappings = resource_helper.build_plural_mappings(
            l7_plurals, RESOURCE_ATTRIBUTE_MAP)

        resources = resource_helper.build_resource_info(
            plural_mappings,
            RESOURCE_ATTRIBUTE_MAP,
            constants.LOADBALANCERV2,
            register_quota=True)

        plugin = directory.get_plugin(constants.LOADBALANCERV2)

        for collection_name in SUB_RESOURCE_ATTRIBUTE_MAP:
            # Special handling needed for sub-resources with 'y' ending
            # (e.g. proxies -> proxy)
            resource_name = plural_mappings.get(collection_name,
                                                collection_name[:-1])
            parent = SUB_RESOURCE_ATTRIBUTE_MAP[collection_name].get('parent')
            params = SUB_RESOURCE_ATTRIBUTE_MAP[collection_name].get(
                'parameters')

            controller = base.create_resource(collection_name, resource_name,
                                              plugin, params,
                                              allow_bulk=True,
                                              parent=parent,
                                              allow_pagination=True,
                                              allow_sorting=True)

            resource = extensions.ResourceExtension(
                collection_name,
                controller, parent,
                path_prefix=LOADBALANCERV2_PREFIX,
                attr_map=params)
            resources.append(resource)

        return resources

    @classmethod
    def get_plugin_interface(cls):
        return loadbalancerv2.LoadBalancerPluginBaseV2

    def update_attributes_map(self, attributes, extension_attrs_map=None):
        super(L7, self).update_attributes_map(
            attributes, extension_attrs_map=RESOURCE_ATTRIBUTE_MAP)

    def get_extended_resources(self, version):
        if version == "2.0":
            return RESOURCE_ATTRIBUTE_MAP
        else:
            return {}
