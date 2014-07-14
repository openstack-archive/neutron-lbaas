# Copyright 2014 OpenStack Foundation
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
#

import collections

RET_PERSISTENCE = {
        'type': 'HTTP_COOKIE',
        'cookie_name': 'HTTP_COOKIE'}

RET_MONITOR = {
        'id': 'sample_monitor_id_1',
        'type': 'HTTP',
        'delay': 30,
        'timeout': 31,
        'max_retries': 3,
        'http_method': 'GET',
        'url_path': '/index.html',
        'expected_codes': '405|404|500',
        'admin_state_up': 'true'}

RET_MEMBER_1 = {
        'id': 'sample_member_id_1',
        'address': '10.0.0.99',
        'protocol_port': 82,
        'weight': 13,
        'subnet_id': '10.0.0.1/24',
        'admin_state_up': 'true',
        'status': 'ACTIVE'}

RET_MEMBER_2 = {
        'id': 'sample_member_id_2',
        'address': '10.0.0.98',
        'protocol_port': 82,
        'weight': 13,
        'subnet_id': '10.0.0.1/24',
        'admin_state_up': 'true',
        'status': 'ACTIVE'}

RET_POOL = {
        'id': 'sample_pool_id_1',
        'protocol': 'http',
        'lb_algorithm': 'roundrobin',
        'members': [RET_MEMBER_1, RET_MEMBER_2],
        'health_monitor': RET_MONITOR,
        'session_persistence': RET_PERSISTENCE,
        'admin_state_up': 'true',
        'status': 'ACTIVE'}

RET_LISTENER = {
        'id': 'sample_listener_id_1',
        'protocol_port': 80,
        'protocol': 'http',
        'default_pool': RET_POOL,
        'connection_limit': 98}

RET_LB = {
        'name': 'test-lb',
        'vip_address': '10.0.0.2',
        'listeners': [RET_LISTENER]}


def sample_loadbalancer_tuple(proto=None, monitor=True, persistence=True,
                              persistence_type=None):
    proto = 'HTTP' if proto is None else proto
    in_lb = collections.namedtuple(
        'loadbalancer', 'id, name, vip_address, protocol, vip_port, '
                        'listeners')
    return in_lb(
        id='sample_loadbalancer_id_1',
        name='test-lb',
        vip_address='10.0.0.2',
        protocol=proto,
        vip_port=sample_vip_port_tuple(),
        listeners=[sample_listener_tuple(proto=proto, monitor=monitor,
                                         persistence=persistence,
                                         persistence_type=persistence_type)]
    )


def sample_vip_port_tuple():
    vip_port = collections.namedtuple('vip_port', 'fixed_ips')
    ip_address = collections.namedtuple('ip_address', 'ip_address')
    in_address = ip_address(ip_address='10.0.0.2')
    return vip_port(fixed_ips=[in_address])


def sample_listener_tuple(proto=None, monitor=True, persistence=True,
                          persistence_type=None):
    proto = 'HTTP' if proto is None else proto
    in_listener = collections.namedtuple(
        'listener', 'id, protocol_port, protocol, default_pool, '
                    'connection_limit')
    return in_listener(
        id='sample_listener_id_1',
        protocol_port=80,
        protocol=proto,
        default_pool=sample_pool_tuple(proto=proto, monitor=monitor,
                                       persistence=persistence,
                                       persistence_type=persistence_type),
        connection_limit=98
    )


def sample_pool_tuple(proto=None, monitor=True, persistence=True,
                      persistence_type=None):
    proto = 'HTTP' if proto is None else proto
    in_pool = collections.namedtuple(
        'pool', 'id, protocol, lb_algorithm, members, healthmonitor,'
                'sessionpersistence, admin_state_up, status')
    mon = sample_health_monitor_tuple(proto=proto) if monitor is True else None
    persis = sample_session_persistence_tuple(
        persistence_type=persistence_type) if persistence is True else None
    return in_pool(
        id='sample_pool_id_1',
        protocol=proto,
        lb_algorithm='ROUND_ROBIN',
        members=[sample_member_tuple('sample_member_id_1', '10.0.0.99'),
                 sample_member_tuple('sample_member_id_2', '10.0.0.98')],
        healthmonitor=mon,
        sessionpersistence=persis,
        admin_state_up='true',
        status='ACTIVE')


def sample_member_tuple(id, ip):
    in_member = collections.namedtuple('member',
                                       'id, address, protocol_port, '
                                       'weight, subnet_id, '
                                       'admin_state_up, status')
    return in_member(
        id=id,
        address=ip,
        protocol_port=82,
        weight=13,
        subnet_id='10.0.0.1/24',
        admin_state_up='true',
        status='ACTIVE')


def sample_session_persistence_tuple(persistence_type=None):
    spersistence = collections.namedtuple('SessionPersistence',
                                          'type, cookie_name')
    pt = 'HTTP_COOKIE' if persistence_type is None else persistence_type
    return spersistence(type=pt,
                        cookie_name=pt)


def sample_health_monitor_tuple(proto=None):
    proto = 'HTTP' if proto is None else proto
    monitor = collections.namedtuple(
        'monitor', 'id, type, delay, timeout, max_retries, http_method, '
                   'url_path, expected_codes, admin_state_up')

    return monitor(id='sample_monitor_id_1', type=proto, delay=30,
                   timeout=31, max_retries=3, http_method='GET',
                   url_path='/index.html', expected_codes='500, 405, 404',
                   admin_state_up='true')


def sample_base_expected_config(frontend=None, backend=None):
    if frontend is None:
        frontend = ("frontend sample_listener_id_1\n"
                    "    option tcplog\n"
                    "    maxconn 98\n"
                    "    option forwardfor\n"
                    "    bind 10.0.0.2:80\n"
                    "    mode http\n"
                    "    default_backend sample_pool_id_1\n\n")
    if backend is None:
        backend = ("backend sample_pool_id_1\n"
                   "    mode http\n"
                   "    balance roundrobin\n"
                   "    cookie SRV insert indirect nocache\n"
                   "    timeout check 31\n"
                   "    option httpchk GET /index.html\n"
                   "    http-check expect rstatus 405|404|500\n"
                   "    server sample_member_id_1 10.0.0.99:82 weight 13 "
                   "check inter 30s fall 3 cookie sample_member_id_1\n"
                   "    server sample_member_id_2 10.0.0.98:82 weight 13 "
                   "check inter 30s fall 3 cookie sample_member_id_2\n")
    return ("# Configuration for test-lb\n"
            "global\n"
            "    daemon\n"
            "    user nobody\n"
            "    group nogroup\n"
            "    log /dev/log local0\n"
            "    log /dev/log local1 notice\n"
            "    stats socket /sock_path mode 0666 level user\n\n"
            "defaults\n"
            "    log global\n"
            "    retries 3\n"
            "    option redispatch\n"
            "    timeout connect 5000\n"
            "    timeout client 50000\n"
            "    timeout server 50000\n\n" + frontend + backend)
