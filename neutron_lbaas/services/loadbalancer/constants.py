# Copyright 2013 Mirantis, Inc.
# All Rights Reserved.
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

#FIXME(brandon-logan): change these to LB_ALGORITHM
LB_METHOD_ROUND_ROBIN = 'ROUND_ROBIN'
LB_METHOD_LEAST_CONNECTIONS = 'LEAST_CONNECTIONS'
LB_METHOD_SOURCE_IP = 'SOURCE_IP'
SUPPORTED_LB_ALGORITHMS = (LB_METHOD_LEAST_CONNECTIONS, LB_METHOD_ROUND_ROBIN,
                           LB_METHOD_SOURCE_IP)

PROTOCOL_TCP = 'TCP'
PROTOCOL_HTTP = 'HTTP'
PROTOCOL_HTTPS = 'HTTPS'
PROTOCOL_TERMINATED_HTTPS = 'TERMINATED_HTTPS'
POOL_SUPPORTED_PROTOCOLS = (PROTOCOL_TCP, PROTOCOL_HTTPS, PROTOCOL_HTTP)
LISTENER_SUPPORTED_PROTOCOLS = (PROTOCOL_TCP, PROTOCOL_HTTPS, PROTOCOL_HTTP,
                                PROTOCOL_TERMINATED_HTTPS)

LISTENER_POOL_COMPATIBLE_PROTOCOLS = (
    (PROTOCOL_TCP, PROTOCOL_TCP),
    (PROTOCOL_HTTP, PROTOCOL_HTTP),
    (PROTOCOL_HTTPS, PROTOCOL_HTTPS),
    (PROTOCOL_HTTP, PROTOCOL_TERMINATED_HTTPS))


HEALTH_MONITOR_PING = 'PING'
HEALTH_MONITOR_TCP = 'TCP'
HEALTH_MONITOR_HTTP = 'HTTP'
HEALTH_MONITOR_HTTPS = 'HTTPS'

SUPPORTED_HEALTH_MONITOR_TYPES = (HEALTH_MONITOR_HTTP, HEALTH_MONITOR_HTTPS,
                                  HEALTH_MONITOR_PING, HEALTH_MONITOR_TCP)

SESSION_PERSISTENCE_SOURCE_IP = 'SOURCE_IP'
SESSION_PERSISTENCE_HTTP_COOKIE = 'HTTP_COOKIE'
SESSION_PERSISTENCE_APP_COOKIE = 'APP_COOKIE'
SUPPORTED_SP_TYPES = (SESSION_PERSISTENCE_SOURCE_IP,
                      SESSION_PERSISTENCE_HTTP_COOKIE,
                      SESSION_PERSISTENCE_APP_COOKIE)

STATS_ACTIVE_CONNECTIONS = 'active_connections'
STATS_MAX_CONNECTIONS = 'max_connections'
STATS_TOTAL_CONNECTIONS = 'total_connections'
STATS_CURRENT_SESSIONS = 'current_sessions'
STATS_MAX_SESSIONS = 'max_sessions'
STATS_TOTAL_SESSIONS = 'total_sessions'
STATS_IN_BYTES = 'bytes_in'
STATS_OUT_BYTES = 'bytes_out'
STATS_CONNECTION_ERRORS = 'connection_errors'
STATS_RESPONSE_ERRORS = 'response_errors'
STATS_STATUS = 'status'
STATS_HEALTH = 'health'
STATS_FAILED_CHECKS = 'failed_checks'

# Constants to extend status strings in neutron.plugins.common.constants
ONLINE = 'ONLINE'
OFFLINE = 'OFFLINE'
DEGRADED = 'DEGRADED'
DISABLED = 'DISABLED'
NO_MONITOR = 'NO_MONITOR'
OPERATING_STATUSES = (ONLINE, OFFLINE, DEGRADED, DISABLED, NO_MONITOR)

NO_CHECK = 'no check'

# LBaaS V2 Agent Constants
# LBaaS V1 Agent constants live in neutron
LBAAS_AGENT_SCHEDULER_V2_EXT_ALIAS = 'lbaas_agent_schedulerv2'
AGENT_TYPE_LOADBALANCERV2 = 'Loadbalancerv2 agent'
LOADBALANCER_PLUGINV2 = 'n-lbaasv2-plugin'
LOADBALANCER_AGENTV2 = 'n-lbaasv2_agent'
