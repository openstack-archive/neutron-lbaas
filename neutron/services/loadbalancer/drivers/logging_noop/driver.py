# Copyright 2014, Doug Wiegley (dougwig), A10 Networks
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

from neutron.openstack.common import log as logging
from neutron.services.loadbalancer.drivers import driver_base

LOG = logging.getLogger(__name__)


class LoggingNoopLoadBalancerDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        self.plugin = plugin

        # Each of the major LBaaS objects in the neutron database
        # need a corresponding manager/handler class.
        #
        # Put common things that are shared across the entire driver, like
        # config or a rest client handle, here.
        #
        # This function is executed when neutron-server starts.

        self.load_balancer = LoggingNoopLoadBalancerManager(self)
        self.listener = LoggingNoopListenerManager(self)
        self.pool = LoggingNoopPoolManager(self)
        self.member = LoggingNoopMemberManager(self)
        self.health_monitor = LoggingNoopHealthMonitorManager(self)


class LoggingNoopCommonManager(object):

    def create(self, context, obj):
        LOG.debug("LB %s no-op, create %s", self.__class__.__name__, obj.id)

    def update(self, context, old_obj, obj):
        LOG.debug("LB %s no-op, update %s", self.__class__.__name__, obj.id)

    def delete(self, context, obj):
        LOG.debug("LB %s no-op, delete %s", self.__class__.__name__, obj.id)


class LoggingNoopLoadBalancerManager(LoggingNoopCommonManager,
                                     driver_base.BaseLoadBalancerManager):

    def refresh(self, context, lb_obj, force=False):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.debug("LB pool refresh %s, force=%s", lb_obj.id, force)

    def stats(self, context, lb_obj):
        LOG.debug("LB stats %s", lb_obj.id)
        return {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }

    def create(self, context, loadbalancer):
        super(LoggingNoopLoadBalancerManager, self).create(context,
                                                           loadbalancer)
        self.driver.activate_cascade(context, loadbalancer)

    def update(self, context, old_loadbalancer, loadbalancer):
        super(LoggingNoopLoadBalancerManager, self).update(context,
                                                           old_loadbalancer,
                                                           loadbalancer)
        self.driver.activate_cascade(context, loadbalancer)

    def delete(self, context, loadbalancer):
        super(LoggingNoopLoadBalancerManager, self).delete(context,
                                                           loadbalancer)
        self.db_delete(context, loadbalancer.id)


class LoggingNoopListenerManager(LoggingNoopCommonManager,
                                 driver_base.BaseListenerManager):
    def create(self, context, obj):
        super(LoggingNoopListenerManager, self).create(context, obj)
        self.driver.activate_cascade(context, obj)

    def update(self, context, old_listener, new_listener):
        super(LoggingNoopListenerManager, self).update(context, old_listener,
                                                       new_listener)
        if new_listener.attached_to_loadbalancer():
            # Always activate listener and its children if attached to
            # loadbalancer
            self.driver.activate_cascade(context, new_listener)
        elif old_listener.attached_to_loadbalancer():
            # If listener has just been detached from loadbalancer
            # defer listener and its children
            self.defer_cascade(context, new_listener)

        if not new_listener.default_pool and old_listener.default_pool:
            # if listener's pool has been detached then defer the pool
            # and its children
            self.driver.pool.defer_cascade(context, old_listener.default_pool)

    def delete(self, context, listener):
        super(LoggingNoopListenerManager, self).delete(context, listener)
        if listener.default_pool:
            self.driver.pool.defer_cascade(context, listener.default_pool)
        self.db_delete(context, listener.id)


class LoggingNoopPoolManager(LoggingNoopCommonManager,
                             driver_base.BasePoolManager):
    def create(self, context, pool):
        super(LoggingNoopPoolManager, self).create(context, pool)
        # This shouldn't be called since a pool cannot be created and linked
        # to a loadbalancer at the same time
        self.driver.activate_cascade(context, pool)

    def update(self, context, old_pool, pool):
        super(LoggingNoopPoolManager, self).update(context, old_pool, pool)
        self.driver.activate_cascade(context, pool)
        if not pool.healthmonitor and old_pool.healthmonitor:
            self.driver.health_monitor.defer(context,
                                             old_pool.healthmonitor.id)

    def delete(self, context, pool):
        super(LoggingNoopPoolManager, self).delete(context, pool)
        if pool.healthmonitor:
            self.driver.health_monitor.defer(context, pool.healthmonitor.id)
        self.db_delete(context, pool.id)


class LoggingNoopMemberManager(LoggingNoopCommonManager,
                               driver_base.BaseMemberManager):
    def create(self, context, member):
        super(LoggingNoopMemberManager, self).create(context, member)
        self.driver.activate_cascade(context, member)

    def update(self, context, old_member, member):
        super(LoggingNoopMemberManager, self).update(context, old_member,
                                                     member)
        self.driver.activate_cascade(context, member)

    def delete(self, context, member):
        super(LoggingNoopMemberManager, self).delete(context, member)
        self.db_delete(context, member.id)


class LoggingNoopHealthMonitorManager(LoggingNoopCommonManager,
                                      driver_base.BaseHealthMonitorManager):

    def create(self, context, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).create(context,
                                                            healthmonitor)
        self.driver.activate_cascade(context, healthmonitor)

    def update(self, context, old_healthmonitor, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).update(context,
                                                            old_healthmonitor,
                                                            healthmonitor)
        self.driver.activate_cascade(context, healthmonitor)

    def delete(self, context, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).delete(context,
                                                            healthmonitor)
        self.db_delete(context, healthmonitor.id)
