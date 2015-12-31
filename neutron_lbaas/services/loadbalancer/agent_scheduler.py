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
import sys

from neutron.common import constants
from neutron.db import agents_db
from neutron.db import agentschedulers_db
from neutron.db import model_base
from oslo_log import log as logging
import six
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import joinedload

from abc import abstractmethod
from neutron_lbaas._i18n import _LW
from neutron_lbaas.extensions import lbaas_agentscheduler

LOG = logging.getLogger(__name__)


class PoolLoadbalancerAgentBinding(model_base.BASEV2):
    """Represents binding between neutron loadbalancer pools and agents."""

    pool_id = sa.Column(sa.String(36),
                        sa.ForeignKey("pools.id", ondelete='CASCADE'),
                        primary_key=True)
    agent = orm.relation(agents_db.Agent)
    agent_id = sa.Column(sa.String(36), sa.ForeignKey("agents.id",
                                                      ondelete='CASCADE'),
                         nullable=False)


class LbaasAgentSchedulerDbMixin(agentschedulers_db.AgentSchedulerDbMixin,
                                 lbaas_agentscheduler
                                 .LbaasAgentSchedulerPluginBase):

    def get_lbaas_agent_hosting_pool(self, context, pool_id, active=None):
        query = context.session.query(PoolLoadbalancerAgentBinding)
        query = query.options(joinedload('agent'))
        binding = query.get(pool_id)

        if (binding and self.is_eligible_agent(
                active, binding.agent)):
            return {'agent': self._make_agent_dict(binding.agent)}

    def get_lbaas_agents(self, context, active=None, filters=None):
        query = context.session.query(agents_db.Agent)
        query = query.filter_by(agent_type=constants.AGENT_TYPE_LOADBALANCER)
        if active is not None:
            query = query.filter_by(admin_state_up=active)
        if filters:
            for key, value in six.iteritems(filters):
                column = getattr(agents_db.Agent, key, None)
                if column:
                    query = query.filter(column.in_(value))

        return [agent
                for agent in query
                if self.is_eligible_agent(active, agent)]

    def list_pools_on_lbaas_agent(self, context, id):
        query = context.session.query(PoolLoadbalancerAgentBinding.pool_id)
        query = query.filter_by(agent_id=id)
        pool_ids = [item[0] for item in query]
        if pool_ids:
            return {'pools': self.get_pools(context, filters={'id': pool_ids})}
        else:
            return {'pools': []}

    def num_of_pools_on_lbaas_agent(self, context, id):
        query = context.session.query(PoolLoadbalancerAgentBinding.pool_id)
        query = query.filter_by(agent_id=id)
        return query.count()

    def get_lbaas_agent_candidates(self, device_driver, active_agents):
        candidates = []
        for agent in active_agents:
            agent_conf = self.get_configuration_dict(agent)
            if device_driver in agent_conf['device_drivers']:
                candidates.append(agent)
        return candidates


class SchedulerBase(object):

    def schedule(self, plugin, context, pool, device_driver):
        """Schedule the pool to an active loadbalancer agent if there
        is no enabled agent hosting it.
        """
        with context.session.begin(subtransactions=True):
            lbaas_agent = plugin.get_lbaas_agent_hosting_pool(
                context, pool['id'])
            if lbaas_agent:
                LOG.debug('Pool %(pool_id)s has already been hosted'
                          ' by lbaas agent %(agent_id)s',
                          {'pool_id': pool['id'],
                           'agent_id': lbaas_agent['id']})
                return

            active_agents = plugin.get_lbaas_agents(context, active=True)
            if not active_agents:
                LOG.warning(_LW('No active lbaas agents for pool %s'),
                            pool['id'])
                return

            candidates = plugin.get_lbaas_agent_candidates(device_driver,
                                                           active_agents)
            if not candidates:
                LOG.warning(_LW('No lbaas agent supporting device driver %s'),
                            device_driver)
                return

            chosen_agent = self._schedule(candidates, plugin, context)

            binding = PoolLoadbalancerAgentBinding()
            binding.agent = chosen_agent
            binding.pool_id = pool['id']
            context.session.add(binding)
            LOG.debug('Pool %(pool_id)s is scheduled to lbaas agent '
                      '%(agent_id)s',
                      {'pool_id': pool['id'],
                       'agent_id': chosen_agent['id']})
            return chosen_agent

    @abstractmethod
    def _schedule(self, candidates, plugin, context):
        pass


class ChanceScheduler(SchedulerBase):

    def _schedule(self, candidates, plugin, context):
        """Allocate a loadbalancer agent for a vip in a random way."""
        return random.choice(candidates)


class LeastPoolAgentScheduler(SchedulerBase):

    def _schedule(self, candidates, plugin, context):
        """Pick an agent with least number of pools from candidates"""
        current_min_pool_num = sys.maxint
        # SchedulerBase.schedule() already checks for empty candidates
        for tmp_agent in candidates:
            tmp_pool_num = plugin.num_of_pools_on_lbaas_agent(
                context, tmp_agent['id'])
            if current_min_pool_num > tmp_pool_num:
                current_min_pool_num = tmp_pool_num
                chosen_agent = tmp_agent
        return chosen_agent
