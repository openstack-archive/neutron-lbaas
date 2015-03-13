# Copyright 2015, Doug Wiegley (dougwig), A10 Networks
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

import a10_neutron_lbaas
from oslo_log import log as logging

from neutron_lbaas.drivers import driver_base

VERSION = "2.0.0"
LOG = logging.getLogger(__name__)


class ThunderDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(ThunderDriver, self).__init__(plugin)

        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)

        LOG.debug("A10Driver: v2 initializing, version=%s, lbaas_manager=%s",
                  VERSION, a10_neutron_lbaas.VERSION)

        self.a10 = a10_neutron_lbaas.A10OpenstackLBV2(self)


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    def create(self, context, lb):
        self.driver.a10.lb.create(context, lb)

    def update(self, context, old_lb, lb):
        self.driver.a10.lb.update(context, old_lb, lb)

    def delete(self, context, lb):
        self.driver.a10.lb.delete(context, lb)

    def refresh(self, context, lb):
        self.driver.a10.lb.refresh(context, lb)

    def stats(self, context, lb):
        return self.driver.a10.lb.stats(context, lb)


class ListenerManager(driver_base.BaseListenerManager):

    def create(self, context, listener):
        self.driver.a10.listener.create(context, listener)

    def update(self, context, old_listener, listener):
        self.driver.a10.listener.update(context, old_listener, listener)

    def delete(self, context, listener):
        self.driver.a10.listener.delete(context, listener)


class PoolManager(driver_base.BasePoolManager):

    def create(self, context, pool):
        self.driver.a10.pool.create(context, pool)

    def update(self, context, old_pool, pool):
        self.driver.a10.pool.update(context, old_pool, pool)

    def delete(self, context, pool):
        self.driver.a10.pool.delete(context, pool)


class MemberManager(driver_base.BaseMemberManager):

    def create(self, context, member):
        self.driver.a10.member.create(context, member)

    def update(self, context, old_member, member):
        self.driver.a10.member.update(context, old_member, member)

    def delete(self, context, member):
        self.driver.a10.member.delete(context, member)


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    def create(self, context, hm):
        self.driver.a10.hm.create(context, hm)

    def update(self, context, old_hm, hm):
        self.driver.a10.hm.update(context, old_hm, hm)

    def delete(self, context, hm):
        self.driver.a10.hm.delete(context, hm)
