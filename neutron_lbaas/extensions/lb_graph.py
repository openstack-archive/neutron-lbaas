# Copyright 2014 OpenStack Foundation.
# All Rights Reserved.
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

from neutron.api.v2 import resource_helper
from neutron_lib.plugins import constants

from neutron_lbaas._i18n import _
from neutron_lbaas.extensions import loadbalancerv2


class ProviderCannotCreateLoadBalancerGraph(nexception.BadRequest):
    message = _("The provider does not have the ability to create a load "
                "balancer graph.")

# NOTE(blogan): this dictionary is to be used only for importing from the
# plugin to validate against.  It is only put here for consistency with
# all other extensions and an easy place to look what changes this extension
# allows.
RESOURCE_ATTRIBUTE_MAP = {
    'graphs': {
        'loadbalancer': {'allow_post': True, 'allow_put': False,
                         'is_visible': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'is_visible': True}
    }
}

EXISTING_ATTR_GRAPH_ATTR_MAP = {
    'loadbalancers': {
        'listeners': {
            'allow_post': True, 'allow_put': False,
            'is_visible': True, 'default': []
        }
    },
    'listeners': {
        'default_pool': {
            'allow_post': True, 'allow_put': False, 'is_visible': True,
            'default': n_constants.ATTR_NOT_SPECIFIED
        },
        'l7policies': {
            'allow_post': True, 'allow_put': False,
            'is_visible': True, 'default': []
        }
    },
    'pools': {
        'healthmonitor': {
            'allow_post': True, 'allow_put': False, 'is_visible': True,
            'default': n_constants.ATTR_NOT_SPECIFIED
        },
        'members': {
            'allow_post': True, 'allow_put': False,
            'is_visible': True, 'default': []
        }
    },
    'l7policies': {
        'rules': {
            'allow_post': True, 'allow_put': False,
            'is_visible': True, 'default': []
        },
        'redirect_pool': {
            'allow_post': True, 'allow_put': False, 'is_visible': True,
            'default': n_constants.ATTR_NOT_SPECIFIED
        },
        'listener_id': {
            'allow_post': False, 'allow_put': False, 'is_visible': True
        }
    }
}


class Lb_graph(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Load Balancer Graph"

    @classmethod
    def get_alias(cls):
        return "lb-graph"

    @classmethod
    def get_description(cls):
        return "Extension for allowing the creation of load balancers with a" \
               " full graph in one API request."

    @classmethod
    def get_updated(cls):
        return "2016-02-09T10:00:00-00:00"

    def get_required_extensions(self):
        return ["lbaasv2"]

    @classmethod
    def get_resources(cls):
        plural_mappings = resource_helper.build_plural_mappings(
            {}, RESOURCE_ATTRIBUTE_MAP)
        resources = resource_helper.build_resource_info(
            plural_mappings,
            RESOURCE_ATTRIBUTE_MAP,
            constants.LOADBALANCERV2,
            register_quota=False)
        return resources

    @classmethod
    def get_plugin_interface(cls):
        return loadbalancerv2.LoadBalancerPluginBaseV2
