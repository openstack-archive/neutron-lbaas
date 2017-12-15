# Copyright 2016-2017 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import f5lbaasdriver
from f5lbaasdriver.v2.bigip.driver_v2 import F5DriverV2

from oslo_log import log as logging

from neutron_lbaas.drivers import driver_base

VERSION = "1.0.0"
LOG = logging.getLogger(__name__)


class UndefinedEnvironment(Exception):
    pass


class F5LBaaSV2Driver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin, env='Project'):
        super(F5LBaaSV2Driver, self).__init__(plugin)

        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)
        self.l7policy = L7PolicyManager(self)
        self.l7rule = L7RuleManager(self)

        if not env:
            msg = "F5LBaaSV2Driver cannot be intialized because the "\
                "environment is not defined. To set the environment, edit "\
                "neutron_lbaas.conf and append the environment name to the "\
                "service_provider class name."
            LOG.debug(msg)
            raise UndefinedEnvironment(msg)

        LOG.debug("F5LBaaSV2Driver: initializing, version=%s, impl=%s, env=%s"
                  % (VERSION, f5lbaasdriver.__version__, env))

        self.f5 = F5DriverV2(plugin, env)


class F5LBaaSV2DriverTest(F5LBaaSV2Driver):

    def __init__(self, plugin, env='Test'):
        super(F5LBaaSV2DriverTest, self).__init__(plugin, env)

        LOG.debug(
            "F5LBaaSV2DriverTest: initializing, version=%s, f5=%s, env=%s"
            % (VERSION, f5lbaasdriver.__version__, env))


class F5LBaaSV2DriverProject(F5LBaaSV2Driver):

    def __init__(self, plugin, env='Project'):
        super(F5LBaaSV2DriverProject, self).__init__(plugin, env)

        LOG.debug(
            "F5LBaaSV2DriverProject: initializing, version=%s, f5=%s, env=%s"
            % (VERSION, f5lbaasdriver.__version__, env))


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    def create(self, context, lb):
        self.driver.f5.loadbalancer.create(context, lb)

    def update(self, context, old_lb, lb):
        self.driver.f5.loadbalancer.update(context, old_lb, lb)

    def delete(self, context, lb):
        self.driver.f5.loadbalancer.delete(context, lb)

    def refresh(self, context, lb):
        self.driver.f5.loadbalancer.refresh(context, lb)

    def stats(self, context, lb):
        return self.driver.f5.loadbalancer.stats(context, lb)


class ListenerManager(driver_base.BaseListenerManager):

    def create(self, context, listener):
        self.driver.f5.listener.create(context, listener)

    def update(self, context, old_listener, listener):
        self.driver.f5.listener.update(context, old_listener, listener)

    def delete(self, context, listener):
        self.driver.f5.listener.delete(context, listener)


class PoolManager(driver_base.BasePoolManager):

    def create(self, context, pool):
        self.driver.f5.pool.create(context, pool)

    def update(self, context, old_pool, pool):
        self.driver.f5.pool.update(context, old_pool, pool)

    def delete(self, context, pool):
        self.driver.f5.pool.delete(context, pool)


class MemberManager(driver_base.BaseMemberManager):

    def create(self, context, member):
        self.driver.f5.member.create(context, member)

    def update(self, context, old_member, member):
        self.driver.f5.member.update(context, old_member, member)

    def delete(self, context, member):
        self.driver.f5.member.delete(context, member)


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    def create(self, context, health_monitor):
        self.driver.f5.healthmonitor.create(context, health_monitor)

    def update(self, context, old_health_monitor, health_monitor):
        self.driver.f5.healthmonitor.update(context, old_health_monitor,
                                   health_monitor)

    def delete(self, context, health_monitor):
        self.driver.f5.healthmonitor.delete(context, health_monitor)


class L7PolicyManager(driver_base.BaseL7PolicyManager):

    def create(self, context, l7policy):
        self.driver.f5.l7policy.create(context, l7policy)

    def update(self, context, old_l7policy, l7policy):
        self.driver.f5.l7policy.update(context, old_l7policy, l7policy)

    def delete(self, context, l7policy):
        self.driver.f5.l7policy.delete(context, l7policy)


class L7RuleManager(driver_base.BaseL7RuleManager):

    def create(self, context, l7rule):
        self.driver.f5.l7rule.create(context, l7rule)

    def update(self, context, old_l7rule, l7rule):
        self.driver.f5.l7rule.update(context, old_l7rule, l7rule)

    def delete(self, context, l7rule):
        self.driver.f5.l7rule.delete(context, l7rule)
