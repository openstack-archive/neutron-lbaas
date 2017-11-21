# Copyright (c) 2013 OpenStack Foundation.
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

import abc

from neutron_lib.api import extensions as api_extensions
from neutron_lib.api import faults
from neutron_lib import exceptions as nexception
from neutron_lib.exceptions import agent as agent_exc
from neutron_lib.plugins import constants as plugin_const
from neutron_lib.plugins import directory

from neutron.api import extensions
from neutron.api.v2 import resource
from neutron import policy
from neutron import wsgi

from neutron_lbaas._i18n import _
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const

LOADBALANCER = 'agent-loadbalancer'
LOADBALANCERS = LOADBALANCER + 's'
LOADBALANCER_AGENT = 'loadbalancer-hosting-agent'


class LoadBalancerSchedulerController(wsgi.Controller):
    def index(self, request, **kwargs):
        lbaas_plugin = directory.get_plugin(plugin_const.LOADBALANCERV2)
        if not lbaas_plugin:
            return {'load_balancers': []}

        policy.enforce(request.context,
                       "get_%s" % LOADBALANCERS,
                       {},
                       plugin=lbaas_plugin)
        lbs = lbaas_plugin.db.list_loadbalancers_on_lbaas_agent(
            request.context, kwargs['agent_id'])
        return {'loadbalancers': [lb.to_api_dict() for lb in lbs]}


class LbaasAgentHostingLoadBalancerController(wsgi.Controller):
    def index(self, request, **kwargs):
        lbaas_plugin = directory.get_plugin(plugin_const.LOADBALANCERV2)
        if not lbaas_plugin:
            return

        policy.enforce(request.context,
                       "get_%s" % LOADBALANCER_AGENT,
                       {},
                       plugin=lbaas_plugin)
        return lbaas_plugin.db.get_agent_hosting_loadbalancer(
            request.context, kwargs['loadbalancer_id'])


class Lbaas_agentschedulerv2(api_extensions.ExtensionDescriptor):
    """Extension class supporting LBaaS agent scheduler.
    """

    @classmethod
    def get_name(cls):
        return "Loadbalancer Agent Scheduler V2"

    @classmethod
    def get_alias(cls):
        return lb_const.LBAAS_AGENT_SCHEDULER_V2_EXT_ALIAS

    @classmethod
    def get_description(cls):
        return "Schedule load balancers among lbaas agents"

    @classmethod
    def get_updated(cls):
        return "2013-02-07T10:00:00-00:00"

    @classmethod
    def get_resources(cls):
        """Returns Ext Resources."""
        exts = []
        parent = dict(member_name="agent",
                      collection_name="agents")

        controller = resource.Resource(LoadBalancerSchedulerController(),
                                       faults.FAULT_MAP)
        exts.append(extensions.ResourceExtension(
            LOADBALANCERS, controller, parent))

        parent = dict(member_name="loadbalancer",
                      collection_name="loadbalancers")

        controller = resource.Resource(
            LbaasAgentHostingLoadBalancerController(), faults.FAULT_MAP)
        exts.append(extensions.ResourceExtension(
            LOADBALANCER_AGENT, controller, parent,
            path_prefix=loadbalancerv2.LOADBALANCERV2_PREFIX))
        return exts

    def get_extended_resources(self, version):
        return {}


class NoEligibleBackend(nexception.NotFound):
    message = _("No eligible backend for pool %(pool_id)s")


class NoEligibleLbaasAgent(NoEligibleBackend):
    message = _("No eligible agent found "
                "for loadbalancer %(loadbalancer_id)s.")


class NoActiveLbaasAgent(agent_exc.AgentNotFound):
    message = _("No active agent found "
                "for loadbalancer %(loadbalancer_id)s.")


class LbaasAgentSchedulerPluginBase(object):
    """REST API to operate the lbaas agent scheduler.

    All of method must be in an admin context.
    """

    @abc.abstractmethod
    def list_loadbalancers_on_lbaas_agent(self, context, id):
        pass

    @abc.abstractmethod
    def get_agent_hosting_loadbalancer(self, context, loadbalancer_id,
                                       active=None):
        pass
