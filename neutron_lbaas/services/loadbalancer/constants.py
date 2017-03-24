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

HTTP_METHOD_GET = 'GET'
HTTP_METHOD_HEAD = 'HEAD'
HTTP_METHOD_POST = 'POST'
HTTP_METHOD_PUT = 'PUT'
HTTP_METHOD_DELETE = 'DELETE'
HTTP_METHOD_TRACE = 'TRACE'
HTTP_METHOD_OPTIONS = 'OPTIONS'
HTTP_METHOD_CONNECT = 'CONNECT'
HTTP_METHOD_PATCH = 'PATCH'


SUPPORTED_HTTP_METHODS = (HTTP_METHOD_GET, HTTP_METHOD_HEAD, HTTP_METHOD_POST,
                          HTTP_METHOD_PUT, HTTP_METHOD_DELETE,
                          HTTP_METHOD_TRACE, HTTP_METHOD_OPTIONS,
                          HTTP_METHOD_CONNECT, HTTP_METHOD_PATCH)

# URL path regex according to RFC 3986
# Format: path = "/" *( "/" segment )
#         segment       = *pchar
#         pchar         = unreserved / pct-encoded / sub-delims / ":" / "@"
#         unreserved    = ALPHA / DIGIT / "-" / "." / "_" / "~"
#         pct-encoded   = "%" HEXDIG HEXDIG
#         sub-delims    = "!" / "$" / "&" / "'" / "(" / ")"
#                         / "*" / "+" / "," / ";" / "="
SUPPORTED_URL_PATH = (
    "^(/([a-zA-Z0-9-._~!$&\'()*+,;=:@]|(%[a-fA-F0-9]{2}))*)+$")

SESSION_PERSISTENCE_SOURCE_IP = 'SOURCE_IP'
SESSION_PERSISTENCE_HTTP_COOKIE = 'HTTP_COOKIE'
SESSION_PERSISTENCE_APP_COOKIE = 'APP_COOKIE'
SUPPORTED_SP_TYPES = (SESSION_PERSISTENCE_SOURCE_IP,
                      SESSION_PERSISTENCE_HTTP_COOKIE,
                      SESSION_PERSISTENCE_APP_COOKIE)

L7_RULE_TYPE_HOST_NAME = 'HOST_NAME'
L7_RULE_TYPE_PATH = 'PATH'
L7_RULE_TYPE_FILE_TYPE = 'FILE_TYPE'
L7_RULE_TYPE_HEADER = 'HEADER'
L7_RULE_TYPE_COOKIE = 'COOKIE'
SUPPORTED_L7_RULE_TYPES = (L7_RULE_TYPE_HOST_NAME,
                           L7_RULE_TYPE_PATH,
                           L7_RULE_TYPE_FILE_TYPE,
                           L7_RULE_TYPE_HEADER,
                           L7_RULE_TYPE_COOKIE)

L7_RULE_COMPARE_TYPE_REGEX = 'REGEX'
L7_RULE_COMPARE_TYPE_STARTS_WITH = 'STARTS_WITH'
L7_RULE_COMPARE_TYPE_ENDS_WITH = 'ENDS_WITH'
L7_RULE_COMPARE_TYPE_CONTAINS = 'CONTAINS'
L7_RULE_COMPARE_TYPE_EQUAL_TO = 'EQUAL_TO'
SUPPORTED_L7_RULE_COMPARE_TYPES = (L7_RULE_COMPARE_TYPE_REGEX,
                                   L7_RULE_COMPARE_TYPE_STARTS_WITH,
                                   L7_RULE_COMPARE_TYPE_ENDS_WITH,
                                   L7_RULE_COMPARE_TYPE_CONTAINS,
                                   L7_RULE_COMPARE_TYPE_EQUAL_TO)

L7_POLICY_ACTION_REJECT = 'REJECT'
L7_POLICY_ACTION_REDIRECT_TO_POOL = 'REDIRECT_TO_POOL'
L7_POLICY_ACTION_REDIRECT_TO_URL = 'REDIRECT_TO_URL'
SUPPORTED_L7_POLICY_ACTIONS = (L7_POLICY_ACTION_REJECT,
                               L7_POLICY_ACTION_REDIRECT_TO_POOL,
                               L7_POLICY_ACTION_REDIRECT_TO_URL)

URL_REGEX = "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|\
             (?:%[0-9a-fA-F][0-9a-fA-F]))+"

# See RFCs 2616, 2965, 6265, 7230: Should match characters valid in a
# http header or cookie name.
HTTP_HEADER_COOKIE_NAME_REGEX = r'\A[a-zA-Z0-9!#$%&\'*+-.^_`|~]+\Z'

# See RFCs 2616, 2965, 6265: Should match characters valid in a cookie value.
HTTP_COOKIE_VALUE_REGEX = r'\A[a-zA-Z0-9!#$%&\'()*+-./:<=>?@[\]^_`{|}~]+\Z'

# See RFC 7230: Should match characters valid in a header value.
HTTP_HEADER_VALUE_REGEX = (r'\A[a-zA-Z0-9'
                           r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~\\]+\Z')

# Also in RFC 7230: Should match characters valid in a header value
# when quoted with double quotes.
HTTP_QUOTED_HEADER_VALUE_REGEX = (r'\A"[a-zA-Z0-9 \t'
                                  r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~\\]*"\Z')

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
LBAAS_AGENT_SCHEDULER_V2_EXT_ALIAS = 'lbaas_agent_schedulerv2'
AGENT_TYPE_LOADBALANCERV2 = 'Loadbalancerv2 agent'
LOADBALANCER_PLUGINV2 = 'n-lbaasv2-plugin'
LOADBALANCER_AGENTV2 = 'n-lbaasv2_agent'

LOADBALANCER = "LOADBALANCER"
LOADBALANCERV2 = "LOADBALANCERV2"

# Used to check number of connections per second allowed
# for the LBaaS V1 vip and LBaaS V2 listeners. -1 indicates
# no limit, the value cannot be less than -1.
MIN_CONNECT_VALUE = -1

# LBaas V2 Table entities
LISTENER_EVENT = 'listener'
LISTENER_STATS_EVENT = 'listener_stats'
LOADBALANCER_EVENT = 'loadbalancer'
LOADBALANCER_STATS_EVENT = 'loadbalancer_stats'
MEMBER_EVENT = 'member'
OPERATING_STATUS = 'operating_status'
POOL_EVENT = 'pool'
