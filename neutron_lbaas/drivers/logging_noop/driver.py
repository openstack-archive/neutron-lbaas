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

from oslo_log import log as logging

from neutron_lbaas.drivers import driver_base

LOG = logging.getLogger(__name__)


class LoggingNoopLoadBalancerDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(LoggingNoopLoadBalancerDriver, self).__init__(plugin)

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

    def refresh(self, context, obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.debug("LB pool refresh %s", obj.id)

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
        self.successful_completion(context, loadbalancer)

    def update(self, context, old_loadbalancer, loadbalancer):
        super(LoggingNoopLoadBalancerManager, self).update(context,
                                                           old_loadbalancer,
                                                           loadbalancer)
        self.successful_completion(context, loadbalancer)

    def delete(self, context, loadbalancer):
        super(LoggingNoopLoadBalancerManager, self).delete(context,
                                                           loadbalancer)
        self.successful_completion(context, loadbalancer, delete=True)


class LoggingNoopListenerManager(LoggingNoopCommonManager,
                                 driver_base.BaseListenerManager):
    def create(self, context, listener):
        super(LoggingNoopListenerManager, self).create(context, listener)
        self.successful_completion(context, listener)

    def update(self, context, old_listener, listener):
        super(LoggingNoopListenerManager, self).update(context, old_listener,
                                                       listener)
        self.successful_completion(context, listener)

    def delete(self, context, listener):
        super(LoggingNoopListenerManager, self).delete(context, listener)
        self.successful_completion(context, listener, delete=True)


class LoggingNoopPoolManager(LoggingNoopCommonManager,
                             driver_base.BasePoolManager):
    def create(self, context, pool):
        super(LoggingNoopPoolManager, self).create(context, pool)
        self.successful_completion(context, pool)

    def update(self, context, old_pool, pool):
        super(LoggingNoopPoolManager, self).update(context, old_pool, pool)
        self.successful_completion(context, pool)

    def delete(self, context, pool):
        super(LoggingNoopPoolManager, self).delete(context, pool)
        self.successful_completion(context, pool, delete=True)


class LoggingNoopMemberManager(LoggingNoopCommonManager,
                               driver_base.BaseMemberManager):
    def create(self, context, member):
        super(LoggingNoopMemberManager, self).create(context, member)
        self.successful_completion(context, member)

    def update(self, context, old_member, member):
        super(LoggingNoopMemberManager, self).update(context, old_member,
                                                     member)
        self.successful_completion(context, member)

    def delete(self, context, member):
        super(LoggingNoopMemberManager, self).delete(context, member)
        self.successful_completion(context, member, delete=True)


class LoggingNoopHealthMonitorManager(LoggingNoopCommonManager,
                                      driver_base.BaseHealthMonitorManager):

    def create(self, context, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).create(context,
                                                            healthmonitor)
        self.successful_completion(context, healthmonitor)

    def update(self, context, old_healthmonitor, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).update(context,
                                                            old_healthmonitor,
                                                            healthmonitor)
        self.successful_completion(context, healthmonitor)

    def delete(self, context, healthmonitor):
        super(LoggingNoopHealthMonitorManager, self).delete(context,
                                                            healthmonitor)
        self.successful_completion(context, healthmonitor, delete=True)
