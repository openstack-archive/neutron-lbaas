# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from neutron.plugins.common import constants

from neutron_lbaas.db.loadbalancer import loadbalancer_db as lb_db
from neutron_lbaas.extensions import loadbalancer as lb_ext
from neutron_lbaas.services.loadbalancer.drivers import abstract_driver
from neutron_lbaas.services.loadbalancer.drivers.vmware import db


class EdgeLoadbalancerDriver(abstract_driver.LoadBalancerAbstractDriver):

    def __init__(self, plugin):
        self._plugin = plugin

    @property
    def _nsxv_driver(self):
        return self._plugin._core_plugin.nsx_v

    def create_pool_successful(self, context, pool, edge_id, edge_pool_id):
        db.add_nsxv_edge_pool_mapping(
            context, pool['id'], edge_id, edge_pool_id)

        self.pool_successful(context, pool)

    def delete_pool_successful(self, context, pool):
        self._plugin._delete_db_pool(context, pool['id'])
        db.delete_nsxv_edge_pool_mapping(context, pool['id'])

    def pool_successful(self, context, pool):
        self._plugin.update_status(
            context, lb_db.Pool, pool['id'], constants.ACTIVE)

    def pool_failed(self, context, pool):
        self._plugin.update_status(
            context, lb_db.Pool, pool['id'], constants.ERROR)

    def create_pool(self, context, pool):
        super(EdgeLoadbalancerDriver, self).create_pool(context, pool)
        self._nsxv_driver.create_pool(context, pool)

    def update_pool(self, context, old_pool, pool):
        super(EdgeLoadbalancerDriver, self).update_pool(
            context, old_pool, pool)
        pool_mapping = db.get_nsxv_edge_pool_mapping(context, old_pool['id'])
        self._nsxv_driver.update_pool(
            context, old_pool, pool, pool_mapping)

    def delete_pool(self, context, pool):
        vip_id = self._plugin.get_pool(context, pool['id']).get('vip_id', None)
        if vip_id:
            raise lb_ext.PoolInUse(pool_id=pool['id'])
        else:
            super(EdgeLoadbalancerDriver, self).delete_pool(context, pool)
            pool_mapping = db.get_nsxv_edge_pool_mapping(context, pool['id'])
            self._nsxv_driver.delete_pool(context, pool, pool_mapping)

    def create_vip_successful(self, context, vip, edge_id, app_profile_id,
                              edge_vip_id, edge_fw_rule_id):
        db.add_nsxv_edge_vip_mapping(context, vip['pool_id'], edge_id,
                                     app_profile_id, edge_vip_id,
                                     edge_fw_rule_id)
        self.vip_successful(context, vip)

    def delete_vip_successful(self, context, vip):
        db.delete_nsxv_edge_vip_mapping(context, vip['pool_id'])
        self._plugin._delete_db_vip(context, vip['id'])

    def vip_successful(self, context, vip):
        self._plugin.update_status(
            context, lb_db.Vip, vip['id'], constants.ACTIVE)

    def vip_failed(self, context, vip):
        self._plugin.update_status(
            context, lb_db.Vip, vip['id'], constants.ERROR)

    def create_vip(self, context, vip):
        super(EdgeLoadbalancerDriver, self).create_vip(context, vip)

        pool_mapping = db.get_nsxv_edge_pool_mapping(context, vip['pool_id'])
        self._nsxv_driver.create_vip(context, vip, pool_mapping)

    def update_vip(self, context, old_vip, vip):
        super(EdgeLoadbalancerDriver, self).update_vip(context, old_vip, vip)

        pool_mapping = db.get_nsxv_edge_pool_mapping(context, vip['pool_id'])
        vip_mapping = db.get_nsxv_edge_vip_mapping(context, vip['pool_id'])
        self._nsxv_driver.update_vip(context, old_vip, vip, pool_mapping,
                                     vip_mapping)

    def delete_vip(self, context, vip):
        super(EdgeLoadbalancerDriver, self).delete_vip(context, vip)
        vip_mapping = db.get_nsxv_edge_vip_mapping(context, vip['pool_id'])
        self._nsxv_driver.delete_vip(context, vip, vip_mapping)

    def member_successful(self, context, member):
        self._plugin.update_status(
            context, lb_db.Member, member['id'], constants.ACTIVE)

    def member_failed(self, context, member):
        self._plugin.update_status(
            context, lb_db.Member, member['id'], constants.ERROR)

    def create_member(self, context, member):
        super(EdgeLoadbalancerDriver, self).create_member(context, member)
        pool_mapping = db.get_nsxv_edge_pool_mapping(
            context, member['pool_id'])
        self._nsxv_driver.create_member(
            context, member, pool_mapping)

    def update_member(self, context, old_member, member):
        super(EdgeLoadbalancerDriver, self).update_member(
            context, old_member, member)
        pool_mapping = db.get_nsxv_edge_pool_mapping(
            context, member['pool_id'])

        self._nsxv_driver.update_member(
            context, old_member, member, pool_mapping)

    def delete_member(self, context, member):
        super(EdgeLoadbalancerDriver, self).delete_member(context, member)
        pool_mapping = db.get_nsxv_edge_pool_mapping(
            context, member['pool_id'])

        self._nsxv_driver.delete_member(context, member, pool_mapping)

    def create_pool_health_monitor_successful(self, context, health_monitor,
                                              pool_id, edge_id, edge_mon_id):
        db.add_nsxv_edge_monitor_mapping(
            context, health_monitor['id'], edge_id, edge_mon_id)
        self.pool_health_monitor_successful(context, health_monitor, pool_id)

    def delete_pool_health_monitor_successful(self, context, health_monitor,
                                              pool_id, mon_mapping):
        db.delete_nsxv_edge_monitor_mapping(
            context, health_monitor['id'], mon_mapping['edge_id'])
        self._plugin._delete_db_pool_health_monitor(
            context, health_monitor['id'], pool_id)

    def pool_health_monitor_successful(self, context, health_monitor, pool_id):
        self._plugin.update_pool_health_monitor(
            context, health_monitor['id'], pool_id, constants.ACTIVE, '')

    def pool_health_monitor_failed(self, context, health_monitor, pool_id):
        self._plugin.update_pool_health_monitor(
            context, health_monitor['id'], pool_id, constants.ERROR, '')

    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        super(EdgeLoadbalancerDriver, self).create_pool_health_monitor(
            context, health_monitor, pool_id)

        pool_mapping = db.get_nsxv_edge_pool_mapping(context, pool_id)
        mon_mapping = db.get_nsxv_edge_monitor_mapping(
            context, health_monitor['id'], pool_mapping['edge_id'])

        self._nsxv_driver.create_pool_health_monitor(
            context, health_monitor, pool_id, pool_mapping, mon_mapping)

    def update_pool_health_monitor(self, context, old_health_monitor,
                                   health_monitor, pool_id):
        super(EdgeLoadbalancerDriver, self).update_pool_health_monitor(
            context, old_health_monitor, health_monitor, pool_id)

        pool_mapping = db.get_nsxv_edge_pool_mapping(context, pool_id)
        mon_mapping = db.get_nsxv_edge_monitor_mapping(
            context, health_monitor['id'], pool_mapping['edge_id'])

        self._nsxv_driver.update_pool_health_monitor(
            context, old_health_monitor, health_monitor, pool_id, mon_mapping)

    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        super(EdgeLoadbalancerDriver, self).delete_pool_health_monitor(
            context, health_monitor, pool_id)

        pool_mapping = db.get_nsxv_edge_pool_mapping(context, pool_id)
        edge_id = pool_mapping['edge_id']
        mon_mapping = db.get_nsxv_edge_monitor_mapping(
            context, health_monitor['id'], edge_id)
        self._nsxv_driver.delete_pool_health_monitor(
            context, health_monitor, pool_id, pool_mapping, mon_mapping)

    def stats(self, context, pool_id):
        super(EdgeLoadbalancerDriver, self).stats(context, pool_id)
        pool_mapping = db.get_nsxv_edge_pool_mapping(context, pool_id)
        return self._nsxv_driver.stats(context, pool_id, pool_mapping)

    def is_edge_in_use(self, context, edge_id):
        pool_mappings = db.get_nsxv_edge_pool_mapping_by_edge(context, edge_id)

        if pool_mappings:
            return True

        return False
