# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

from oslo_log.helpers import log_method_call as call_log

from neutron_lbaas.common import cert_manager
from neutron_lbaas.drivers import driver_base


class EdgeDriverBaseManager(object):
    @property
    def lbv2_driver(self):
        return self.driver.plugin.db._core_plugin.lbv2_driver


class EdgeLoadBalancerDriverV2(driver_base.LoadBalancerBaseDriver):
    @call_log
    def __init__(self, plugin):
        self.plugin = plugin
        super(EdgeLoadBalancerDriverV2, self).__init__(plugin)
        self.load_balancer = EdgeLoadBalancerManager(self)
        self.listener = EdgeListenerManager(self)
        self.pool = EdgePoolManager(self)
        self.member = EdgeMemberManager(self)
        self.health_monitor = EdgeHealthMonitorManager(self)
        self.l7policy = L7PolicyManager(self)
        self.l7rule = L7RuleManager(self)


class EdgeLoadBalancerManager(driver_base.BaseLoadBalancerManager,
                              EdgeDriverBaseManager):
    @call_log
    def create(self, context, lb):
        self.lbv2_driver.loadbalancer.create(context, lb)

    @call_log
    def update(self, context, old_lb, new_lb):
        self.lbv2_driver.loadbalancer.update(context, old_lb, new_lb)

    @call_log
    def delete(self, context, lb):
        self.lbv2_driver.loadbalancer.delete(context, lb)

    @call_log
    def refresh(self, context, lb):
        return self.lbv2_driver.loadbalancer.refresh(context, lb)

    @call_log
    def stats(self, context, lb):
        return self.lbv2_driver.loadbalancer.stats(context, lb)


class EdgeListenerManager(driver_base.BaseListenerManager,
                          EdgeDriverBaseManager):

    def _get_default_cert(self, listener):
        if listener.default_tls_container_id:
            cert_backend = cert_manager.get_backend()
            if cert_backend:
                return cert_backend.CertManager().get_cert(
                    project_id=listener.tenant_id,
                    cert_ref=listener.default_tls_container_id,
                    resource_ref=cert_backend.CertManager.get_service_url(
                        listener.loadbalancer_id)
                )

    @call_log
    def create(self, context, listener):
        self.lbv2_driver.listener.create(
            context, listener, certificate=self._get_default_cert(listener))

    @call_log
    def update(self, context, old_listener, new_listener):
        self.lbv2_driver.listener.update(
            context, old_listener, new_listener,
            certificate=self._get_default_cert(new_listener))

    @call_log
    def delete(self, context, listener):
        self.lbv2_driver.listener.delete(context, listener)


class EdgePoolManager(driver_base.BasePoolManager,
                      EdgeDriverBaseManager):
    @call_log
    def create(self, context, pool):
        self.lbv2_driver.pool.create(context, pool)

    @call_log
    def update(self, context, old_pool, new_pool):
        self.lbv2_driver.pool.update(context, old_pool, new_pool)

    @call_log
    def delete(self, context, pool):
        self.lbv2_driver.pool.delete(context, pool)


class EdgeMemberManager(driver_base.BaseMemberManager,
                        EdgeDriverBaseManager):
    @call_log
    def create(self, context, member):
        self.lbv2_driver.member.create(context, member)

    @call_log
    def update(self, context, old_member, new_member):
        self.lbv2_driver.member.update(context, old_member, new_member)

    @call_log
    def delete(self, context, member):
        self.lbv2_driver.member.delete(context, member)


class EdgeHealthMonitorManager(driver_base.BaseHealthMonitorManager,
                               EdgeDriverBaseManager):
    @call_log
    def create(self, context, hm):
        self.lbv2_driver.healthmonitor.create(context, hm)

    @call_log
    def update(self, context, old_hm, new_hm):
        self.lbv2_driver.healthmonitor.update(context, old_hm, new_hm)

    @call_log
    def delete(self, context, hm):
        self.lbv2_driver.healthmonitor.delete(context, hm)


class L7PolicyManager(driver_base.BaseL7PolicyManager,
                      EdgeDriverBaseManager):
    @call_log
    def create(self, context, pol):
        self.lbv2_driver.l7policy.create(context, pol)

    @call_log
    def update(self, context, old_pol, new_pol):
        self.lbv2_driver.l7policy.update(context, old_pol, new_pol)

    @call_log
    def delete(self, context, pol):
        self.lbv2_driver.l7policy.delete(context, pol)


class L7RuleManager(driver_base.BaseL7RuleManager,
                    EdgeDriverBaseManager):
    @call_log
    def create(self, context, rule):
        self.lbv2_driver.l7rule.create(context, rule)

    @call_log
    def update(self, context, old_rule, new_rule):
        self.lbv2_driver.l7rule.update(context, old_rule, new_rule)

    @call_log
    def delete(self, context, rule):
        self.lbv2_driver.l7rule.delete(context, rule)
