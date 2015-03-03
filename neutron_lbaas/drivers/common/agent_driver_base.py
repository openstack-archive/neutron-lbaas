# Copyright 2015 Rackspace.
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

from neutron.common import exceptions as n_exc
from neutron.common import rpc as n_rpc
from neutron.db import agents_db
from neutron.openstack.common import log as logging
from neutron.services import provider_configuration as provconf
from oslo_config import cfg
import oslo_messaging as messaging
from oslo_utils import importutils

from neutron_lbaas.drivers import driver_base
from neutron_lbaas.extensions import lbaas_agentschedulerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models

LOG = logging.getLogger(__name__)

LB_SCHEDULERS = 'loadbalancer_schedulers'

AGENT_SCHEDULER_OPTS = [
    cfg.StrOpt('loadbalancer_scheduler_driver',
               default='neutron_lbaas.agent_scheduler.ChanceScheduler',
               help=_('Driver to use for scheduling '
                      'to a default loadbalancer agent')),
]

cfg.CONF.register_opts(AGENT_SCHEDULER_OPTS)


class DriverNotSpecified(n_exc.NeutronException):
    message = _("Device driver for agent should be specified "
                "in plugin driver.")


class DataModelSerializer(object):

    def serialize_entity(self, ctx, entity):
        if isinstance(entity, data_models.BaseDataModel):
            return entity.to_dict(stats=False)
        else:
            return entity


class LoadBalancerAgentApi(object):
    """Plugin side of plugin to agent RPC API."""

    # history
    #   1.0 Initial version
    #

    def __init__(self, topic):
        target = messaging.Target(topic=topic, version='1.0')
        self.client = n_rpc.get_client(target,
                                       serializer=DataModelSerializer())

    def agent_updated(self, context, admin_state_up, host):
        cctxt = self.client.prepare(server=host)
        cctxt.cast(context, 'agent_updated',
                   payload={'admin_state_up': admin_state_up})

    def create_loadbalancer(self, context, loadbalancer, host, driver_name):
        cctxt = self.client.prepare(server=host)
        cctxt.cast(context, 'create_loadbalancer',
                   loadbalancer=loadbalancer, driver_name=driver_name)

    def update_loadbalancer(self, context, old_loadbalancer,
                            loadbalancer, host):
        cctxt = self.client.prepare(server=host)
        cctxt.cast(context, 'update_loadbalancer',
                   old_loadbalancer=old_loadbalancer,
                   loadbalancer=loadbalancer)

    def delete_loadbalancer(self, context, loadbalancer, host):
        cctxt = self.client.prepare(server=host)
        cctxt.cast(context, 'delete_loadbalancer', loadbalancer=loadbalancer)


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    def update(self, context, old_loadbalancer, loadbalancer):
        super(LoadBalancerManager, self).update(context, old_loadbalancer,
                                                loadbalancer)
        agent = self.driver.get_loadbalancer_agent(context, loadbalancer.id)
        self.driver.agent_rpc.update_loadbalancer(
            context, old_loadbalancer, loadbalancer, agent['host'])

    def create(self, context, loadbalancer):
        super(LoadBalancerManager, self).create(context, loadbalancer)
        agent = self.driver.loadbalancer_scheduler.schedule(
            self.driver.plugin, context, loadbalancer,
            self.driver.device_driver)
        if not agent:
            raise lbaas_agentschedulerv2.NoEligibleLbaasAgent(
                loadbalancer_id=loadbalancer.id)
        self.driver.agent_rpc.create_loadbalancer(
            context, loadbalancer, agent['host'], self.driver.device_driver)

    def delete(self, context, loadbalancer):
        super(LoadBalancerManager, self).delete(context, loadbalancer)
        agent = self.driver.get_loadbalancer_agent(context, loadbalancer.id)
        # TODO(blogan): Rethink deleting from the database here. May want to
        # wait until the agent actually deletes it.  Doing this now to keep
        # what v1 had.
        self.driver.plugin.db.delete_loadbalancer(context, loadbalancer.id)
        if agent:
            self.driver.agent_rpc.delete_loadbalancer(context, loadbalancer,
                                                      agent['host'])

    def stats(self, context, loadbalancer):
        pass

    def refresh(self, context, loadbalancer):
        pass


class AgentDriverBase(driver_base.LoadBalancerBaseDriver):

    # name of device driver that should be used by the agent;
    # vendor specific plugin drivers must override it;
    device_driver = None

    def __init__(self, plugin):
        super(AgentDriverBase, self).__init__(plugin)
        if not self.device_driver:
            raise DriverNotSpecified()

        self.load_balancer = LoadBalancerManager(self)

        self.agent_rpc = LoadBalancerAgentApi(lb_const.LOADBALANCER_AGENTV2)

        self._set_callbacks_on_plugin()
        # Setting this on the db because the plugin no longer inherts from
        # database classes, the db does.
        self.plugin.db.agent_notifiers.update(
            {lb_const.AGENT_TYPE_LOADBALANCERV2: self.agent_rpc})

        lb_sched_driver = provconf.get_provider_driver_class(
            cfg.CONF.loadbalancer_scheduler_driver, LB_SCHEDULERS)
        self.loadbalancer_scheduler = importutils.import_object(
            lb_sched_driver)

    def _set_callbacks_on_plugin(self):
        # other agent based plugin driver might already set callbacks on plugin
        if hasattr(self.plugin, 'agent_callbacks'):
            return

        self.plugin.agent_endpoints = [
            agents_db.AgentExtRpcCallback(self.plugin.db)
        ]
        self.plugin.conn = n_rpc.create_connection(new=True)
        self.plugin.conn.create_consumer(
            lb_const.LOADBALANCER_PLUGINV2,
            self.plugin.agent_endpoints,
            fanout=False)
        self.plugin.conn.consume_in_threads()

    def get_loadbalancer_agent(self, context, loadbalancer_id):
        agent = self.plugin.db.get_agent_hosting_loadbalancer(
            context, loadbalancer_id)
        if not agent:
            raise lbaas_agentschedulerv2.NoActiveLbaasAgent(
                loadbalancer_id=loadbalancer_id)
        return agent['agent']
