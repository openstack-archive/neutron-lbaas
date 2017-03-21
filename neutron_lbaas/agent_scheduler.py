# Copyright (c) 2013 OpenStack Foundation.
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

import random

from neutron.db import agentschedulers_db
from neutron.db.models import agent as agents_db
from neutron_lib.db import model_base
from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import joinedload

from neutron_lbaas.extensions import lbaas_agentschedulerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const

LOG = logging.getLogger(__name__)


class LoadbalancerAgentBinding(model_base.BASEV2):
    """Represents binding between neutron loadbalancer and agents."""

    __tablename__ = "lbaas_loadbalanceragentbindings"

    loadbalancer_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("lbaas_loadbalancers.id", ondelete='CASCADE'),
        primary_key=True)
    agent = orm.relation(agents_db.Agent)
    agent_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("agents.id", ondelete='CASCADE'),
        nullable=False)


class LbaasAgentSchedulerDbMixin(agentschedulers_db.AgentSchedulerDbMixin,
                                 lbaas_agentschedulerv2
                                 .LbaasAgentSchedulerPluginBase):

    agent_notifiers = {}

    def get_agent_hosting_loadbalancer(self, context,
                                       loadbalancer_id, active=None):
        query = context.session.query(LoadbalancerAgentBinding)
        query = query.options(joinedload('agent'))
        binding = query.get(loadbalancer_id)

        if (binding and self.is_eligible_agent(
                active, binding.agent)):
            return {'agent': self._make_agent_dict(binding.agent)}

    def get_lbaas_agents(self, context, active=None, filters=None):
        query = context.session.query(agents_db.Agent)
        query = query.filter_by(agent_type=lb_const.AGENT_TYPE_LOADBALANCERV2)
        if active is not None:
            query = query.filter_by(admin_state_up=active)
        if filters:
            for key, value in filters.items():
                column = getattr(agents_db.Agent, key, None)
                if column:
                    query = query.filter(column.in_(value))

        return [agent
                for agent in query
                if self.is_eligible_agent(active, agent)]

    def list_loadbalancers_on_lbaas_agent(self, context, id):
        query = context.session.query(
            LoadbalancerAgentBinding.loadbalancer_id)
        query = query.filter_by(agent_id=id)
        loadbalancer_ids = [item[0] for item in query]
        if loadbalancer_ids:
            lbs = self.get_loadbalancers(context,
                                         filters={'id': loadbalancer_ids})
            return lbs
        return []

    def get_lbaas_agent_candidates(self, device_driver, active_agents):
        candidates = []
        for agent in active_agents:
            agent_conf = self.get_configuration_dict(agent)
            if device_driver in agent_conf['device_drivers']:
                candidates.append(agent)
        return candidates

    def get_down_loadbalancer_bindings(self, context, agent_dead_limit):
            cutoff = self.get_cutoff_time(agent_dead_limit)
            return (context.session.query(LoadbalancerAgentBinding).join(
                agents_db.Agent).filter(
                    agents_db.Agent.heartbeat_timestamp < cutoff,
                    agents_db.Agent.admin_state_up))

    def _unschedule_loadbalancer(self, context, loadbalancer_id, agent_id):
        with context.session.begin(subtransactions=True):
            query = context.session.query(LoadbalancerAgentBinding)
            query = query.filter(
                LoadbalancerAgentBinding.loadbalancer_id == loadbalancer_id,
                LoadbalancerAgentBinding.agent_id == agent_id)
            query.delete()


class ChanceScheduler(object):
    """Allocate a loadbalancer agent for a vip in a random way."""

    def schedule(self, plugin, context, loadbalancer, device_driver):
        """Schedule the load balancer to an active loadbalancer agent if there
        is no enabled agent hosting it.
        """
        with context.session.begin(subtransactions=True):
            lbaas_agent = plugin.db.get_agent_hosting_loadbalancer(
                context, loadbalancer.id)
            if lbaas_agent:
                LOG.debug('Load balancer %(loadbalancer_id)s '
                          'has already been hosted'
                          ' by lbaas agent %(agent_id)s',
                          {'loadbalancer_id': loadbalancer.id,
                           'agent_id': lbaas_agent['agent']['id']})
                return

            active_agents = plugin.db.get_lbaas_agents(context, active=True)
            if not active_agents:
                LOG.warning(
                    'No active lbaas agents for load balancer %s',
                    loadbalancer.id)
                return

            candidates = plugin.db.get_lbaas_agent_candidates(device_driver,
                                                              active_agents)
            if not candidates:
                LOG.warning('No lbaas agent supporting device driver %s',
                            device_driver)
                return

            chosen_agent = random.choice(candidates)
            binding = LoadbalancerAgentBinding()
            binding.agent = chosen_agent
            binding.loadbalancer_id = loadbalancer.id
            context.session.add(binding)
            LOG.debug(
                'Load balancer %(loadbalancer_id)s is scheduled '
                'to lbaas agent %(agent_id)s', {
                    'loadbalancer_id': loadbalancer.id,
                    'agent_id': chosen_agent['id']}
            )
            return chosen_agent
