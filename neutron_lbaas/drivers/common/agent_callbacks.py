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

from neutron_lib.api.definitions import portbindings
from neutron_lib import constants
from neutron_lib import exceptions as n_exc
from oslo_log import log as logging
import oslo_messaging as messaging

from neutron_lbaas._i18n import _
from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2
from neutron_lbaas.db.loadbalancer import models as db_models
from neutron_lbaas.services.loadbalancer import data_models

LOG = logging.getLogger(__name__)


class LoadBalancerCallbacks(object):

    # history
    #   1.0 Initial version
    target = messaging.Target(version='1.0')

    def __init__(self, plugin):
        super(LoadBalancerCallbacks, self).__init__()
        self.plugin = plugin

    def get_ready_devices(self, context, host=None):
        with context.session.begin(subtransactions=True):
            agents = self.plugin.db.get_lbaas_agents(
                context, filters={'host': [host]})
            if not agents:
                return []
            elif len(agents) > 1:
                LOG.warning('Multiple lbaas agents found on host %s', host)
            loadbalancers = self.plugin.db.list_loadbalancers_on_lbaas_agent(
                context, agents[0].id)
            loadbalancer_ids = [
                l.id for l in loadbalancers]

            qry = context.session.query(
                loadbalancer_dbv2.models.LoadBalancer.id)
            qry = qry.filter(
                loadbalancer_dbv2.models.LoadBalancer.id.in_(
                    loadbalancer_ids))
            qry = qry.filter(
                loadbalancer_dbv2.models.LoadBalancer.provisioning_status.in_(
                    constants.ACTIVE_PENDING_STATUSES))
            up = True  # makes pep8 and sqlalchemy happy
            qry = qry.filter(
                loadbalancer_dbv2.models.LoadBalancer.admin_state_up == up)
            return [id for id, in qry]

    def get_loadbalancer(self, context, loadbalancer_id=None):
        lb_model = self.plugin.db.get_loadbalancer(context, loadbalancer_id)
        if lb_model.vip_port and lb_model.vip_port.fixed_ips:
            for fixed_ip in lb_model.vip_port.fixed_ips:
                subnet_dict = self.plugin.db._core_plugin.get_subnet(
                    context, fixed_ip.subnet_id
                )
                setattr(fixed_ip, 'subnet', data_models.Subnet.from_dict(
                    subnet_dict))
        if lb_model.provider:
            device_driver = self.plugin.drivers[
                lb_model.provider.provider_name].device_driver
            setattr(lb_model.provider, 'device_driver', device_driver)
        if lb_model.vip_port:
            network_dict = self.plugin.db._core_plugin.get_network(
                context, lb_model.vip_port.network_id)
            setattr(lb_model.vip_port, 'network',
                    data_models.Network.from_dict(network_dict))
        lb_dict = lb_model.to_dict(stats=False)

        return lb_dict

    def loadbalancer_deployed(self, context, loadbalancer_id):
        with context.session.begin(subtransactions=True):
            qry = context.session.query(db_models.LoadBalancer)
            qry = qry.filter_by(id=loadbalancer_id)
            loadbalancer = qry.one()

            # set all resources to active
            if (loadbalancer.provisioning_status in
                    constants.ACTIVE_PENDING_STATUSES):
                loadbalancer.provisioning_status = constants.ACTIVE

            if loadbalancer.listeners:
                for l in loadbalancer.listeners:
                    if (l.provisioning_status in
                            constants.ACTIVE_PENDING_STATUSES):
                        l.provisioning_status = constants.ACTIVE
                    if (l.default_pool and
                        l.default_pool.provisioning_status in
                            constants.ACTIVE_PENDING_STATUSES):
                        l.default_pool.provisioning_status = constants.ACTIVE
                        if l.default_pool.members:
                            for m in l.default_pool.members:
                                if (m.provisioning_status in
                                        constants.ACTIVE_PENDING_STATUSES):
                                    m.provisioning_status = constants.ACTIVE
                        if l.default_pool.healthmonitor:
                            hm = l.default_pool.healthmonitor
                            ps = hm.provisioning_status
                            if ps in constants.ACTIVE_PENDING_STATUSES:
                                (l.default_pool.healthmonitor
                                 .provisioning_status) = constants.ACTIVE

    def update_status(self, context, obj_type, obj_id,
                      provisioning_status=None, operating_status=None):
        if not provisioning_status and not operating_status:
            LOG.warning('update_status for %(obj_type)s %(obj_id)s called '
                        'without specifying provisioning_status or '
                        'operating_status' % {'obj_type': obj_type,
                                              'obj_id': obj_id})
            return
        model_mapping = {
            'loadbalancer': db_models.LoadBalancer,
            'pool': db_models.PoolV2,
            'listener': db_models.Listener,
            'member': db_models.MemberV2,
            'healthmonitor': db_models.HealthMonitorV2
        }
        if obj_type not in model_mapping:
            raise n_exc.Invalid(_('Unknown object type: %s') % obj_type)
        try:
            self.plugin.db.update_status(
                context, model_mapping[obj_type], obj_id,
                provisioning_status=provisioning_status,
                operating_status=operating_status)
        except n_exc.NotFound:
            # update_status may come from agent on an object which was
            # already deleted from db with other request
            LOG.warning('Cannot update status: %(obj_type)s %(obj_id)s '
                        'not found in the DB, it was probably deleted '
                        'concurrently',
                        {'obj_type': obj_type, 'obj_id': obj_id})

    def loadbalancer_destroyed(self, context, loadbalancer_id=None):
        """Agent confirmation hook that a load balancer has been destroyed.

        This method exists for subclasses to change the deletion
        behavior.
        """
        pass

    def plug_vip_port(self, context, port_id=None, host=None):
        if not port_id:
            return

        try:
            port = self.plugin.db._core_plugin.get_port(
                context,
                port_id
            )
        except n_exc.PortNotFound:
            LOG.debug('Unable to find port %s to plug.', port_id)
            return

        port['admin_state_up'] = True
        port[portbindings.HOST_ID] = host
        port['device_owner'] = constants.DEVICE_OWNER_LOADBALANCERV2
        self.plugin.db._core_plugin.update_port(
            context,
            port_id,
            {'port': port}
        )

    def unplug_vip_port(self, context, port_id=None, host=None):
        if not port_id:
            return

        try:
            port = self.plugin.db._core_plugin.get_port(
                context,
                port_id
            )
        except n_exc.PortNotFound:
            LOG.debug('Unable to find port %s to unplug. This can occur when '
                      'the Vip has been deleted first.',
                      port_id)
            return

        port['admin_state_up'] = False
        port['device_owner'] = ''
        port['device_id'] = ''

        try:
            self.plugin.db._core_plugin.update_port(
                context,
                port_id,
                {'port': port}
            )

        except n_exc.PortNotFound:
            LOG.debug('Unable to find port %s to unplug.  This can occur when '
                      'the Vip has been deleted first.',
                      port_id)

    def update_loadbalancer_stats(self, context,
                                  loadbalancer_id=None,
                                  stats=None):
        self.plugin.db.update_loadbalancer_stats(context, loadbalancer_id,
                                                 stats)
