# Copyright 2015, Radware LTD. All rights reserved
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

from oslo_config import cfg
from oslo_log import helpers as log_helpers

from neutron_lbaas._i18n import _
from neutron_lbaas.drivers import driver_base


VERSION = "P1.0.0"

driver_opts = [
    cfg.StrOpt('vdirect_address',
               help=_('IP address of vDirect server.')),
    cfg.StrOpt('ha_secondary_address',
               help=_('IP address of secondary vDirect server.')),
    cfg.StrOpt('vdirect_user',
               default='vDirect',
               help=_('vDirect user name.')),
    cfg.StrOpt('vdirect_password',
               default='radware',
               secret=True,
               help=_('vDirect user password.')),
    cfg.IntOpt('port',
               default=2189,
               help=_('vDirect port. Default:2189')),
    cfg.BoolOpt('ssl',
               default=True,
               help=_('Use SSL. Default: True')),
    cfg.BoolOpt('ssl_verify_context',
                default=True,
                help=_('Enables or disables the SSL context verification '
                       'for legacy python that verifies HTTPS '
                       'certificates by default. Default: True.')),
    cfg.IntOpt('timeout',
               default=5000,
               help=_('vDirect connection timeout. Default:5000')),
    cfg.StrOpt('base_uri',
               default='',
               help=_('Base vDirect URI. Default:\'\'')),
    cfg.StrOpt('service_adc_type',
               default="VA",
               help=_('Service ADC type. Default: VA.')),
    cfg.StrOpt('service_adc_version',
               default="",
               help=_('Service ADC version.')),
    cfg.BoolOpt('service_ha_pair',
                default=False,
                help=_('Enables or disables the Service HA pair. '
                       'Default: False.')),
    cfg.BoolOpt('configure_allowed_address_pairs',
                default=False,
                help=_('Enables or disables allowed address pairs '
                       'configuration for VIP addresses. '
                       'Default: False.')),
    cfg.IntOpt('service_throughput',
               default=1000,
               help=_('Service throughput. Default: 1000.')),
    cfg.IntOpt('service_ssl_throughput',
               default=100,
               help=_('Service SSL throughput. Default: 100.')),
    cfg.IntOpt('service_compression_throughput',
               default=100,
               help=_('Service compression throughput. Default: 100.')),
    cfg.IntOpt('service_cache',
               default=20,
               help=_('Size of service cache. Default: 20.')),
    cfg.ListOpt('service_resource_pool_ids',
                default=[],
                help=_('Resource pool IDs.')),
    cfg.IntOpt('service_isl_vlan',
               default=-1,
               help=_('A required VLAN for the interswitch link to use.')),
    cfg.BoolOpt('service_session_mirroring_enabled',
                default=False,
                help=_('Enable or disable Alteon interswitch link for '
                       'stateful session failover. Default: False.')),
    cfg.StrOpt('workflow_template_name',
               default='os_lb_v2',
               help=_('Name of the workflow template. Default: os_lb_v2.')),
    cfg.ListOpt('child_workflow_template_names',
               default=['manage_l3'],
               help=_('Name of child workflow templates used.'
                      'Default: manage_l3')),
    cfg.DictOpt('workflow_params',
                default={"twoleg_enabled": "_REPLACE_",
                         "ha_network_name": "HA-Network",
                         "ha_ip_pool_name": "default",
                         "allocate_ha_vrrp": True,
                         "allocate_ha_ips": True,
                         "data_port": 1,
                         "data_ip_address": "192.168.200.99",
                         "data_ip_mask": "255.255.255.0",
                         "gateway": "192.168.200.1",
                         "ha_port": 2},
                help=_('Parameter for l2_l3 workflow constructor.')),
    cfg.StrOpt('workflow_action_name',
               default='apply',
               help=_('Name of the workflow action. '
                      'Default: apply.')),
    cfg.StrOpt('stats_action_name',
               default='stats',
               help=_('Name of the workflow action for statistics. '
                      'Default: stats.'))
]

driver_debug_opts = [
    cfg.BoolOpt('provision_service',
                default=True,
                help=_('Provision ADC service?')),
    cfg.BoolOpt('configure_l3',
                default=True,
                help=_('Configule ADC with L3 parameters?')),
    cfg.BoolOpt('configure_l4',
                default=True,
                help=_('Configule ADC with L4 parameters?'))
]

cfg.CONF.register_opts(driver_opts, "radwarev2")
cfg.CONF.register_opts(driver_debug_opts, "radwarev2_debug")


class RadwareLBaaSBaseV2Driver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(RadwareLBaaSBaseV2Driver, self).__init__(plugin)

        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.l7policy = L7PolicyManager(self)
        self.l7rule = L7RuleManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    @log_helpers.log_method_call
    def create(self, context, lb):
        self.successful_completion(context, lb)

    @log_helpers.log_method_call
    def update(self, context, old_lb, lb):
        if self.driver.workflow_exists(old_lb):
            self.driver.execute_workflow(
                context, self, lb, old_data_model=old_lb)
        else:
            self.successful_completion(context, lb)

    @log_helpers.log_method_call
    def delete(self, context, lb):
        if self.driver.workflow_exists(lb):
            self.driver.remove_workflow(
                context, self, lb)
        else:
            self.successful_completion(context, lb, delete=True)

    @log_helpers.log_method_call
    def refresh(self, context, lb):
        if lb.listeners and any(listener.default_pool and
            listener.default_pool.members for listener in lb.listeners):
            self.driver.execute_workflow(
                context, self, lb)
        else:
            self.successful_completion(context, lb)

    @log_helpers.log_method_call
    def stats(self, context, lb):
        if self.driver.workflow_exists(lb):
            return self.driver.get_stats(context, lb)
        else:
            self.successful_completion(context, lb)


class ListenerManager(driver_base.BaseListenerManager):

    @log_helpers.log_method_call
    def create(self, context, listener):
        if self.driver.workflow_exists(listener.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, listener)
        else:
            self.successful_completion(context, listener)

    @log_helpers.log_method_call
    def update(self, context, old_listener, listener):
        if self.driver.workflow_exists(old_listener.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, listener, old_data_model=old_listener)
        else:
            self.successful_completion(context, listener)

    @log_helpers.log_method_call
    def delete(self, context, listener):
        if self.driver.workflow_exists(listener.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, listener, delete=True)
        else:
            self.successful_completion(context, listener, delete=True)


class L7PolicyManager(driver_base.BaseL7PolicyManager):

    @log_helpers.log_method_call
    def create(self, context, policy):
        if self.driver.workflow_exists(policy.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, policy)
        else:
            self.successful_completion(context, policy)

    @log_helpers.log_method_call
    def update(self, context, old_policy, policy):
        if self.driver.workflow_exists(old_policy.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, policy, old_data_model=old_policy)
        else:
            self.successful_completion(context, policy)

    @log_helpers.log_method_call
    def delete(self, context, policy):
        if self.driver.workflow_exists(policy.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, policy, delete=True)
        else:
            self.successful_completion(context, policy, delete=True)


class L7RuleManager(driver_base.BaseL7RuleManager):

    @log_helpers.log_method_call
    def create(self, context, rule):
        if self.driver.workflow_exists(rule.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, rule)
        else:
            self.successful_completion(context, rule)

    @log_helpers.log_method_call
    def update(self, context, old_rule, rule):
        if self.driver.workflow_exists(old_rule.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, rule, old_data_model=old_rule)
        else:
            self.successful_completion(context, rule)

    @log_helpers.log_method_call
    def delete(self, context, rule):
        if self.driver.workflow_exists(rule.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, rule, delete=True)
        else:
            self.successful_completion(context, rule, delete=True)


class PoolManager(driver_base.BasePoolManager):

    @log_helpers.log_method_call
    def create(self, context, pool):
        if self.driver.workflow_exists(pool.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, pool)
        else:
            self.successful_completion(context, pool)

    @log_helpers.log_method_call
    def update(self, context, old_pool, pool):
        if self.driver.workflow_exists(old_pool.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, pool, old_data_model=old_pool)
        else:
            self.successful_completion(context, pool)

    @log_helpers.log_method_call
    def delete(self, context, pool):
        if self.driver.workflow_exists(pool.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, pool, delete=True)
        else:
            self.successful_completion(context, pool,
                                       delete=True)


class MemberManager(driver_base.BaseMemberManager):

    @log_helpers.log_method_call
    def create(self, context, member):
        self.driver.execute_workflow(
            context, self, member)

    @log_helpers.log_method_call
    def update(self, context, old_member, member):
        self.driver.execute_workflow(
            context, self, member, old_data_model=old_member)

    @log_helpers.log_method_call
    def delete(self, context, member):
        self.driver.execute_workflow(
            context, self, member,
            delete=True)


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    @log_helpers.log_method_call
    def create(self, context, hm):
        if self.driver.workflow_exists(hm.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, hm)
        else:
            self.successful_completion(context, hm)

    @log_helpers.log_method_call
    def update(self, context, old_hm, hm):
        if self.driver.workflow_exists(old_hm.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, hm, old_data_model=old_hm)
        else:
            self.successful_completion(context, hm)

    @log_helpers.log_method_call
    def delete(self, context, hm):
        if self.driver.workflow_exists(hm.root_loadbalancer):
            self.driver.execute_workflow(
                context, self, hm, delete=True)
        else:
            self.successful_completion(context, hm,
                                       delete=True)
