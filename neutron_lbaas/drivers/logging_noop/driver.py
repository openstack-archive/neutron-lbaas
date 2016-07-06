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
        self.l7policy = LoggingNoopL7PolicyManager(self)
        self.l7rule = LoggingNoopL7RuleManager(self)


class LoggingNoopCommonManager(object):

    @driver_base.driver_op
    def create(self, context, obj):
        LOG.debug("LB %s no-op, create %s", self.__class__.__name__, obj.id)

    @driver_base.driver_op
    def update(self, context, old_obj, obj):
        LOG.debug("LB %s no-op, update %s", self.__class__.__name__, obj.id)

    @driver_base.driver_op
    def delete(self, context, obj):
        LOG.debug("LB %s no-op, delete %s", self.__class__.__name__, obj.id)


class LoggingNoopLoadBalancerManager(LoggingNoopCommonManager,
                                     driver_base.BaseLoadBalancerManager):

    @property
    def allows_create_graph(self):
        return True

    @property
    def allows_healthmonitor_thresholds(self):
        return True

    @property
    def allocates_vip(self):
        LOG.debug('allocates_vip queried')
        return False

    def create_and_allocate_vip(self, context, obj):
        LOG.debug("LB %s no-op, create_and_allocate_vip %s",
                  self.__class__.__name__, obj.id)
        self.create(context, obj)

    @driver_base.driver_op
    def refresh(self, context, obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.debug("LB pool refresh %s", obj.id)

    @driver_base.driver_op
    def stats(self, context, lb_obj):
        LOG.debug("LB stats %s", lb_obj.id)
        return {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }


class LoggingNoopListenerManager(LoggingNoopCommonManager,
                                 driver_base.BaseListenerManager):
    pass


class LoggingNoopPoolManager(LoggingNoopCommonManager,
                             driver_base.BasePoolManager):
    pass


class LoggingNoopMemberManager(LoggingNoopCommonManager,
                               driver_base.BaseMemberManager):
    pass


class LoggingNoopHealthMonitorManager(LoggingNoopCommonManager,
                                      driver_base.BaseHealthMonitorManager):
    pass


class LoggingNoopL7PolicyManager(LoggingNoopCommonManager,
                                 driver_base.BaseL7PolicyManager):
    pass


class LoggingNoopL7RuleManager(LoggingNoopCommonManager,
                               driver_base.BaseL7RuleManager):
    pass
