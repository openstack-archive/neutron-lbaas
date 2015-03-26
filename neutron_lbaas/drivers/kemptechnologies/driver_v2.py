#  Copyright 2015, Shane McGough, KEMPtechnologies
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from kemptech_openstack_lbaas import driver as kemptech
from oslo_config import cfg

from neutron_lbaas.drivers import driver_base
from neutron_lbaas.drivers.kemptechnologies import config

cfg.CONF.register_opts(config.KEMP_OPTS, 'kemptechnologies')
CONF = cfg.CONF.kemptechnologies


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    def create(self, context, lb):
        self.driver.kemptech.load_balancer.create(context, lb)

    def update(self, context, old_lb, lb):
        self.driver.kemptech.load_balancer.update(context, old_lb, lb)

    def delete(self, context, lb):
        self.driver.kemptech.load_balancer.delete(context, lb)

    def refresh(self, context, lb):
        self.driver.kemptech.load_balancer.refresh(context, lb)

    def stats(self, context, lb):
        return self.driver.kemptech.load_balancer.stats(context, lb)


class ListenerManager(driver_base.BaseListenerManager):

    def create(self, context, listener):
        self.driver.kemptech.listener.create(context, listener)

    def update(self, context, old_listener, listener):
        self.driver.kemptech.listener.update(context, old_listener, listener)

    def delete(self, context, listener):
        self.driver.kemptech.listener.delete(context, listener)


class PoolManager(driver_base.BasePoolManager):

    def create(self, context, pool):
        self.driver.kemptech.pool.create(context, pool)

    def update(self, context, old_pool, pool):
        self.driver.kemptech.pool.update(context, old_pool, pool)

    def delete(self, context, pool):
        self.driver.kemptech.pool.delete(context, pool)


class MemberManager(driver_base.BaseMemberManager):

    def create(self, context, member):
        self.driver.kemptech.member.create(context, member)

    def update(self, context, old_member, member):
        self.driver.kemptech.member.update(context, old_member, member)

    def delete(self, context, member):
        self.driver.kemptech.member.delete(context, member)


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    def create(self, context, health_monitor):
        self.driver.kemptech.health_monitor.create(context, health_monitor)

    def update(self, context, old_health_monitor, health_monitor):
        self.driver.kemptech.health_monitor.update(context,
                                                   old_health_monitor,
                                                   health_monitor)

    def delete(self, context, health_monitor):
        self.driver.kemptech.health_monitor.delete(context, health_monitor)


class KempLoadMasterDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(KempLoadMasterDriver, self).__init__(plugin)
        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)
        self.kemptech = kemptech.KempLoadMasterDriver(self, CONF)
