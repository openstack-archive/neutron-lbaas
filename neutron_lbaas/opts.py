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

import itertools

import neutron.conf.agent.common
import neutron.conf.services.provider_configuration

import neutron_lbaas.agent.agent
import neutron_lbaas.common.cert_manager
import neutron_lbaas.common.cert_manager.local_cert_manager
import neutron_lbaas.common.keystone
import neutron_lbaas.drivers.common.agent_driver_base
import neutron_lbaas.drivers.haproxy.namespace_driver
import neutron_lbaas.drivers.octavia.driver
import neutron_lbaas.drivers.radware.base_v2_driver
import neutron_lbaas.extensions.loadbalancerv2


def list_agent_opts():
    return [
        ('DEFAULT',
         itertools.chain(
             neutron_lbaas.agent.agent.OPTS,
             neutron.conf.agent.common.INTERFACE_OPTS,
             neutron.conf.agent.common.INTERFACE_DRIVER_OPTS)
         ),
        ('haproxy',
         neutron_lbaas.drivers.haproxy.namespace_driver.OPTS)
    ]


def list_opts():
    return [
        ('DEFAULT',
         neutron_lbaas.drivers.common.agent_driver_base.AGENT_SCHEDULER_OPTS),
        ('quotas',
         neutron_lbaas.extensions.loadbalancerv2.lbaasv2_quota_opts),
        ('service_auth',
         neutron_lbaas.common.keystone.OPTS),
        ('service_providers',
         neutron.conf.services.provider_configuration.serviceprovider_opts),
        ('certificates',
         itertools.chain(
             neutron_lbaas.common.cert_manager.cert_manager_opts,
             neutron_lbaas.common.cert_manager.local_cert_manager.
             local_cert_manager_opts)
         )
    ]


def list_service_opts():
    return [
        ('radwarev2',
         neutron_lbaas.drivers.radware.base_v2_driver.driver_opts),
        ('radwarev2_debug',
         neutron_lbaas.drivers.radware.base_v2_driver.driver_debug_opts),
        ('haproxy',
         itertools.chain(
             neutron.conf.agent.common.INTERFACE_DRIVER_OPTS,
             neutron_lbaas.agent.agent.OPTS,
         )),
        ('octavia',
         neutron_lbaas.drivers.octavia.driver.OPTS)
    ]
