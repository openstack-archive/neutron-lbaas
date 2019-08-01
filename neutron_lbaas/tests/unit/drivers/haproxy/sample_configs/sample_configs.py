# Copyright 2014 OpenStack Foundation
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
#

import collections

from neutron_lbaas.services.loadbalancer import constants

RET_PERSISTENCE = {
    'type': 'HTTP_COOKIE',
    'cookie_name': 'HTTP_COOKIE'}

HASHSEED_ORDERED_CODES = list({'404', '405', '500'})
PIPED_CODES = '|'.join(HASHSEED_ORDERED_CODES)

RET_MONITOR = {
    'id': 'sample_monitor_id_1',
    'type': 'HTTP',
    'delay': 30,
    'timeout': 31,
    'max_retries': 3,
    'http_method': 'GET',
    'url_path': '/index.html',
    'expected_codes': PIPED_CODES,
    'admin_state_up': True}

RET_MEMBER_1 = {
    'id': 'sample_member_id_1',
    'address': '10.0.0.99',
    'protocol_port': 82,
    'weight': 13,
    'subnet_id': '10.0.0.1/24',
    'admin_state_up': True,
    'provisioning_status': 'ACTIVE'}

RET_MEMBER_2 = {
    'id': 'sample_member_id_2',
    'address': '10.0.0.98',
    'protocol_port': 82,
    'weight': 13,
    'subnet_id': '10.0.0.1/24',
    'admin_state_up': True,
    'provisioning_status': 'ACTIVE'}

RET_POOL = {
    'id': 'sample_pool_id_1',
    'protocol': 'http',
    'lb_algorithm': 'roundrobin',
    'members': [RET_MEMBER_1, RET_MEMBER_2],
    'health_monitor': RET_MONITOR,
    'session_persistence': RET_PERSISTENCE,
    'admin_state_up': True,
    'provisioning_status': 'ACTIVE'}

RET_DEF_TLS_CONT = {'id': 'cont_id_1', 'allencompassingpem': 'imapem'}
RET_SNI_CONT_1 = {'id': 'cont_id_2', 'allencompassingpem': 'imapem2'}
RET_SNI_CONT_2 = {'id': 'cont_id_3', 'allencompassingpem': 'imapem3'}

RET_LISTENER = {
    'id': 'sample_listener_id_1',
    'protocol_port': '80',
    'protocol': 'HTTP',
    'protocol_mode': 'http',
    'default_pool': RET_POOL,
    'connection_limit': 98}

RET_LISTENER_TLS = {
    'id': 'sample_listener_id_1',
    'protocol_port': '443',
    'protocol_mode': 'http',
    'protocol': 'TERMINATED_HTTPS',
    'default_pool': RET_POOL,
    'connection_limit': 98,
    'default_tls_container_id': 'cont_id_1',
    'default_tls_path': '/v2/sample_loadbalancer_id_1/cont_id_1.pem',
    'default_tls_container': RET_DEF_TLS_CONT}

RET_LISTENER_TLS_SNI = {
    'id': 'sample_listener_id_1',
    'protocol_port': '443',
    'protocol_mode': 'http',
    'protocol': 'TERMINATED_HTTPS',
    'default_pool': RET_POOL,
    'connection_limit': 98,
    'default_tls_container_id': 'cont_id_1',
    'default_tls_path': '/v2/sample_loadbalancer_id_1/cont_id_1.pem',
    'default_tls_container': RET_DEF_TLS_CONT,
    'crt_dir': '/v2/sample_loadbalancer_id_1',
    'sni_container_ids': ['cont_id_2', 'cont_id_3'],
    'sni_containers': [RET_SNI_CONT_1, RET_SNI_CONT_2]}

RET_LB = {
    'id': 'sample_loadbalancer_id_1',
    'vip_address': '10.0.0.2',
    'listeners': [RET_LISTENER],
    'connection_limit': RET_LISTENER['connection_limit'],
    'pools': [RET_POOL]}

RET_LB_TLS = {
    'id': 'sample_loadbalancer_id_1',
    'vip_address': '10.0.0.2',
    'listeners': [RET_LISTENER_TLS],
    'connection_limit': RET_LISTENER_TLS['connection_limit'],
    'pools': [RET_POOL]}

RET_LB_TLS_SNI = {
    'id': 'sample_loadbalancer_id_1',
    'vip_address': '10.0.0.2',
    'listeners': [RET_LISTENER_TLS_SNI],
    'connection_limit': RET_LISTENER_TLS_SNI['connection_limit'],
    'pools': [RET_POOL]}


def sample_loadbalancer_tuple(proto=None, monitor=True, persistence=True,
                              persistence_type=None, tls=False, sni=False):
    proto = 'HTTP' if proto is None else proto
    in_lb = collections.namedtuple(
        'loadbalancer', 'id, vip_address, protocol, vip_port, '
                        'listeners, pools')
    return in_lb(
        id='sample_loadbalancer_id_1',
        vip_address='10.0.0.2',
        protocol=proto,
        vip_port=sample_vip_port_tuple(),
        listeners=[sample_listener_tuple(proto=proto, monitor=monitor,
                                         persistence=persistence,
                                         persistence_type=persistence_type,
                                         tls=tls,
                                         sni=sni)],
        pools=[sample_pool_tuple(proto=proto, monitor=monitor,
                                 persistence=persistence,
                                 persistence_type=persistence_type)]
    )


def sample_vip_port_tuple():
    vip_port = collections.namedtuple('vip_port', 'fixed_ips')
    ip_address = collections.namedtuple('ip_address', 'ip_address')
    in_address = ip_address(ip_address='10.0.0.2')
    return vip_port(fixed_ips=[in_address])


def sample_listener_tuple(proto=None, monitor=True, persistence=True,
                          persistence_type=None, tls=False, sni=False,
                          connection_limit=98):
    proto = 'HTTP' if proto is None else proto
    port = '443' if proto is 'HTTPS' or proto is 'TERMINATED_HTTPS' else '80'
    in_listener = collections.namedtuple(
        'listener', 'id, tenant_id, protocol_port, protocol, default_pool, '
        'connection_limit, admin_state_up, default_tls_container_id, '
                    'sni_container_ids, default_tls_container, '
                    'sni_containers, loadbalancer_id')
    return in_listener(
        id='sample_listener_id_1',
        tenant_id='sample_tenant_id',
        protocol_port=port,
        protocol=proto,
        default_pool=sample_pool_tuple(
            proto=proto, monitor=monitor, persistence=persistence,
            persistence_type=persistence_type),
        connection_limit=connection_limit,
        admin_state_up=True,
        default_tls_container_id='cont_id_1' if tls else '',
        sni_container_ids=['cont_id_2', 'cont_id_3'] if sni else [],
        default_tls_container=sample_tls_container_tuple(
            id='cont_id_1', certificate='--imapem1--\n',
            private_key='--imakey1--\n', intermediates=[
                '--imainter1--\n', '--imainter1too--\n'],
            primary_cn='fakeCNM'
        ) if tls else '',
        sni_containers=[
            sample_tls_sni_container_tuple(
                tls_container_id='cont_id_2',
                tls_container=sample_tls_container_tuple(
                    id='cont_id_2', certificate='--imapem2--\n',
                    private_key='--imakey2--\n', intermediates=[
                        '--imainter2--\n', '--imainter2too--\n'],
                    primary_cn='fakeCN')),
            sample_tls_sni_container_tuple(
                tls_container_id='cont_id_3',
                tls_container=sample_tls_container_tuple(
                    id='cont_id_3', certificate='--imapem3--\n',
                    private_key='--imakey3--\n', intermediates=[
                        '--imainter3--\n', '--imainter3too--\n'],
                    primary_cn='fakeCN2'))]
        if sni else [],
        loadbalancer_id='sample_loadbalancer_id_1'
    )


def sample_tls_sni_container_tuple(tls_container=None, tls_container_id=None):
    sc = collections.namedtuple('sni_container', 'tls_container,'
                                                 'tls_container_id')
    return sc(tls_container=tls_container, tls_container_id=tls_container_id)


def sample_tls_container_tuple(id='cont_id_1', certificate=None,
                               private_key=None, intermediates=None,
                               primary_cn=None):
    intermediates = intermediates or []
    sc = collections.namedtuple(
        'tls_cert',
        'id, certificate, private_key, intermediates, primary_cn')
    return sc(id=id, certificate=certificate, private_key=private_key,
              intermediates=intermediates or [], primary_cn=primary_cn)


def sample_pool_tuple(proto=None, monitor=True, persistence=True,
                      persistence_type=None, hm_admin_state=True):
    proto = 'HTTP' if proto is None else proto
    in_pool = collections.namedtuple(
        'pool', 'id, protocol, lb_algorithm, members, healthmonitor,'
                'session_persistence, admin_state_up, provisioning_status')
    mon = (sample_health_monitor_tuple(proto=proto, admin_state=hm_admin_state)
           if monitor is True else None)
    persis = sample_session_persistence_tuple(
        persistence_type=persistence_type) if persistence is True else None
    return in_pool(
        id='sample_pool_id_1',
        protocol=proto,
        lb_algorithm='ROUND_ROBIN',
        members=[sample_member_tuple('sample_member_id_1', '10.0.0.99'),
                 sample_member_tuple('sample_member_id_2', '10.0.0.98')],
        healthmonitor=mon,
        session_persistence=persis,
        admin_state_up=True,
        provisioning_status='ACTIVE')


def sample_member_tuple(id, ip, admin_state_up=True, status='ACTIVE'):
    in_member = collections.namedtuple('member',
                                       'id, address, protocol_port, '
                                       'weight, subnet_id, '
                                       'admin_state_up, provisioning_status')
    return in_member(
        id=id,
        address=ip,
        protocol_port=82,
        weight=13,
        subnet_id='10.0.0.1/24',
        admin_state_up=admin_state_up,
        provisioning_status=status)


def sample_session_persistence_tuple(persistence_type=None):
    spersistence = collections.namedtuple('SessionPersistence',
                                          'type, cookie_name')
    pt = 'HTTP_COOKIE' if persistence_type is None else persistence_type
    return spersistence(type=pt,
                        cookie_name=pt)


def sample_health_monitor_tuple(proto='HTTP', admin_state=True):
    proto = 'HTTP' if proto is 'TERMINATED_HTTPS' else proto
    monitor = collections.namedtuple(
        'monitor', 'id, type, delay, timeout, max_retries, http_method, '
                   'url_path, expected_codes, admin_state_up')

    return monitor(id='sample_monitor_id_1', type=proto, delay=30,
                   timeout=31, max_retries=3, http_method='GET',
                   url_path='/index.html', expected_codes='500, 405, 404',
                   admin_state_up=admin_state)


def sample_base_expected_config(backend, frontend=None,
                                fe_proto=constants.PROTOCOL_HTTP):
    if frontend is None:
        tcp_frontend = ("frontend sample_listener_id_1\n"
                        "    option tcplog\n"
                        "    maxconn 98\n"
                        "    bind 10.0.0.2:80\n"
                        "    mode tcp\n"
                        "    default_backend sample_pool_id_1\n\n")
        http_frontend = ("frontend sample_listener_id_1\n"
                         "    option httplog\n"
                         "    maxconn 98\n"
                         "    option forwardfor\n"
                         "    bind 10.0.0.2:80\n"
                         "    mode http\n"
                         "    default_backend sample_pool_id_1\n\n")
        https_frontend = ("frontend sample_listener_id_1\n"
                          "    option tcplog\n"
                          "    maxconn 98\n"
                          "    bind 10.0.0.2:443\n"
                          "    mode tcp\n"
                          "    default_backend sample_pool_id_1\n\n")
        https_tls_frontend = ("frontend sample_listener_id_1\n"
                              "    option httplog\n"
                              "    redirect scheme https if !{ ssl_fc }\n"
                              "    maxconn 98\n"
                              "    option forwardfor\n"
                              "    bind 10.0.0.2:443\n"
                              "    mode http\n"
                              "    default_backend sample_pool_id_1\n\n")
        fe_mapper = {
            constants.PROTOCOL_TCP: tcp_frontend,
            constants.PROTOCOL_HTTP: http_frontend,
            constants.PROTOCOL_HTTPS: https_frontend,
            constants.PROTOCOL_TERMINATED_HTTPS: https_tls_frontend
        }
        frontend = fe_mapper[fe_proto]
    return ("# Configuration for sample_loadbalancer_id_1\n"
            "global\n"
            "    daemon\n"
            "    user nobody\n"
            "    group nogroup\n"
            "    log /dev/log local0 debug alert\n"
            "    log /dev/log local1 notice alert\n"
            "    maxconn 98\n"
            "    stats socket /sock_path mode 0666 level user\n\n"
            "defaults\n"
            "    log global\n"
            "    retries 3\n"
            "    option redispatch\n"
            "    timeout connect 5000\n"
            "    timeout client 50000\n"
            "    timeout server 50000\n\n" + frontend + backend)
