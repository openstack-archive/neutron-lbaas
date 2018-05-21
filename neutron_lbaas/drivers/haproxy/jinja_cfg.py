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

import os

import jinja2
from neutron_lib.utils import file as file_utils
from oslo_config import cfg
import six

from neutron_lib import constants as nl_constants

from neutron_lbaas._i18n import _
from neutron_lbaas.common import cert_manager
from neutron_lbaas.common.tls_utils import cert_parser
from neutron_lbaas.services.loadbalancer import constants
from neutron_lbaas.services.loadbalancer import data_models

CERT_MANAGER_PLUGIN = cert_manager.get_backend()

PROTOCOL_MAP = {
    constants.PROTOCOL_TCP: 'tcp',
    constants.PROTOCOL_HTTP: 'http',
    constants.PROTOCOL_HTTPS: 'tcp',
    constants.PROTOCOL_TERMINATED_HTTPS: 'http'
}

BALANCE_MAP = {
    constants.LB_METHOD_ROUND_ROBIN: 'roundrobin',
    constants.LB_METHOD_LEAST_CONNECTIONS: 'leastconn',
    constants.LB_METHOD_SOURCE_IP: 'source'
}

STATS_MAP = {
    constants.STATS_ACTIVE_CONNECTIONS: 'scur',
    constants.STATS_MAX_CONNECTIONS: 'smax',
    constants.STATS_CURRENT_SESSIONS: 'scur',
    constants.STATS_MAX_SESSIONS: 'smax',
    constants.STATS_TOTAL_CONNECTIONS: 'stot',
    constants.STATS_TOTAL_SESSIONS: 'stot',
    constants.STATS_IN_BYTES: 'bin',
    constants.STATS_OUT_BYTES: 'bout',
    constants.STATS_CONNECTION_ERRORS: 'econ',
    constants.STATS_RESPONSE_ERRORS: 'eresp'
}

MEMBER_STATUSES = nl_constants.ACTIVE_PENDING_STATUSES + (
    nl_constants.INACTIVE,)

TEMPLATES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), 'templates/'))
JINJA_ENV = None

jinja_opts = [
    cfg.StrOpt(
        'jinja_config_template',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default=os.path.join(
            TEMPLATES_DIR,
            'haproxy.loadbalancer.j2'),
        help=_('Jinja template file for haproxy configuration'))
]

cfg.CONF.register_opts(jinja_opts, 'haproxy')


def save_config(conf_path, loadbalancer, socket_path, user_group,
                haproxy_base_dir):
    """Convert a logical configuration to the HAProxy version.

    :param conf_path: location of Haproxy configuration
    :param loadbalancer: the load balancer object
    :param socket_path: location of haproxy socket data
    :param user_group: user group
    :param haproxy_base_dir: location of the instances state data
    """
    config_str = render_loadbalancer_obj(loadbalancer,
                                         user_group,
                                         socket_path,
                                         haproxy_base_dir)
    file_utils.replace_file(conf_path, config_str)


def _get_template():
    """Retrieve Jinja template

    :returns: Jinja template
    """
    global JINJA_ENV
    if not JINJA_ENV:
        template_loader = jinja2.FileSystemLoader(
            searchpath=os.path.dirname(cfg.CONF.haproxy.jinja_config_template))
        JINJA_ENV = jinja2.Environment(
            loader=template_loader, trim_blocks=True, lstrip_blocks=True)
    return JINJA_ENV.get_template(os.path.basename(
        cfg.CONF.haproxy.jinja_config_template))


def _store_listener_crt(haproxy_base_dir, listener, cert):
    """Store TLS certificate

    :param haproxy_base_dir: location of the instances state data
    :param listener: the listener object
    :param cert: the TLS certificate
    :returns: location of the stored certificate
    """
    cert_path = _retrieve_crt_path(haproxy_base_dir, listener,
                                   cert.primary_cn)
    # build a string that represents the pem file to be saved
    pem = _build_pem(cert)
    file_utils.replace_file(cert_path, pem)
    return cert_path


def _retrieve_crt_path(haproxy_base_dir, listener, primary_cn):
    """Retrieve TLS certificate location

    :param haproxy_base_dir: location of the instances state data
    :param listener: the listener object
    :param primary_cn: primary_cn used for identifying TLS certificate
    :returns: TLS certificate location
    """
    confs_dir = os.path.abspath(os.path.normpath(haproxy_base_dir))
    confs_path = os.path.join(confs_dir, listener.id)
    if haproxy_base_dir and listener.id:
        if not os.path.isdir(confs_path):
            os.makedirs(confs_path, 0o755)
        return os.path.join(
            confs_path, '{0}.pem'.format(primary_cn))


def _process_tls_certificates(listener):
    """Processes TLS data from the listener.

    Converts and uploads PEM data to the Amphora API

    :param listener: the listener object
    :returns: TLS_CERT and SNI_CERTS
    """
    cert_mgr = CERT_MANAGER_PLUGIN.CertManager()

    tls_cert = None
    sni_certs = []
    # Retrieve, map and store default TLS certificate
    if listener.default_tls_container_id:
        tls_cert = _map_cert_tls_container(
            cert_mgr.get_cert(
                project_id=listener.tenant_id,
                cert_ref=listener.default_tls_container_id,
                resource_ref=cert_mgr.get_service_url(
                    listener.loadbalancer_id),
                check_only=True
            )
        )
    if listener.sni_containers:
        # Retrieve, map and store SNI certificates
        for sni_cont in listener.sni_containers:
            cert_container = _map_cert_tls_container(
                cert_mgr.get_cert(
                    project_id=listener.tenant_id,
                    cert_ref=sni_cont.tls_container_id,
                    resource_ref=cert_mgr.get_service_url(
                        listener.loadbalancer_id),
                    check_only=True
                )
            )
            sni_certs.append(cert_container)

    return {'tls_cert': tls_cert, 'sni_certs': sni_certs}


def _get_primary_cn(tls_cert):
    """Retrieve primary cn for TLS certificate

    :param tls_cert: the TLS certificate
    :returns: primary cn of the TLS certificate
    """
    return cert_parser.get_host_names(tls_cert)['cn']


def _map_cert_tls_container(cert):
    """Map cert data to TLS data model

    :param cert: TLS certificate
    :returns: mapped TLSContainer object
    """
    certificate = cert.get_certificate()
    pkey = cert_parser.dump_private_key(cert.get_private_key(),
                                        cert.get_private_key_passphrase())
    return data_models.TLSContainer(
        primary_cn=_get_primary_cn(certificate),
        private_key=pkey,
        certificate=certificate,
        intermediates=cert.get_intermediates())


def _build_pem(tls_cert):
    """Generate PEM encoded TLS certificate data

    :param tls_cert: TLS certificate
    :returns: PEm encoded certificate data
    """
    pem = ()
    if tls_cert.intermediates:
        for c in tls_cert.intermediates:
            pem = pem + (c,)
    if tls_cert.certificate:
        pem = pem + (tls_cert.certificate,)
    if tls_cert.private_key:
        pem = pem + (tls_cert.private_key,)
    return "\n".join(pem)


def render_loadbalancer_obj(loadbalancer, user_group, socket_path,
                            haproxy_base_dir):
    """Renders load balancer object

    :param loadbalancer: the load balancer object
    :param user_group: the user group
    :param socket_path: location of the instances socket data
    :param haproxy_base_dir:  location of the instances state data
    :returns: rendered load balancer configuration
    """
    loadbalancer = _transform_loadbalancer(loadbalancer, haproxy_base_dir)
    return _get_template().render({'loadbalancer': loadbalancer,
                                   'user_group': user_group,
                                   'stats_sock': socket_path},
                                  constants=constants)


def _transform_loadbalancer(loadbalancer, haproxy_base_dir):
    """Transforms load balancer object

    :param loadbalancer: the load balancer object
    :param haproxy_base_dir: location of the instances state data
    :returns: dictionary of transformed load balancer values
    """
    listeners = [_transform_listener(x, haproxy_base_dir)
        for x in loadbalancer.listeners if x.admin_state_up]
    pools = [_transform_pool(x) for x in loadbalancer.pools]
    connection_limit = _compute_global_connection_limit(listeners)
    return {
        'id': loadbalancer.id,
        'vip_address': loadbalancer.vip_address,
        'connection_limit': connection_limit,
        'listeners': listeners,
        'pools': pools
    }


def _compute_global_connection_limit(listeners):
    # NOTE(dlundquist): HAProxy has a global default connection limit
    # of 2000, so we will include 2000 connections for each listener
    # without a connection limit specified. This way we provide the
    # same behavior as a default haproxy configuration without
    # connection limit specified in the case of a single load balancer.
    return sum([x.get('connection_limit', 2000) for x in listeners])


def _transform_listener(listener, haproxy_base_dir):
    """Transforms listener object

    :param listener: the listener object
    :param haproxy_base_dir: location of the instances state data
    :returns: dictionary of transformed listener values
    """
    data_dir = os.path.join(haproxy_base_dir, listener.id)
    ret_value = {
        'id': listener.id,
        'protocol_port': listener.protocol_port,
        'protocol_mode': PROTOCOL_MAP[listener.protocol],
        'protocol': listener.protocol
    }
    if listener.connection_limit and listener.connection_limit > -1:
        ret_value['connection_limit'] = listener.connection_limit
    if listener.default_pool:
        ret_value['default_pool'] = _transform_pool(listener.default_pool)

    # Process and store certificates
    certs = _process_tls_certificates(listener)
    if listener.default_tls_container_id:
        ret_value['default_tls_path'] = _store_listener_crt(
            haproxy_base_dir, listener, certs['tls_cert'])
    if listener.sni_containers:
        for c in certs['sni_certs']:
            _store_listener_crt(haproxy_base_dir, listener, c)
        ret_value['crt_dir'] = data_dir
    return ret_value


def _transform_pool(pool):
    """Transforms pool object

    :param pool: the pool object
    :returns: dictionary of transformed pool values
    """
    ret_value = {
        'id': pool.id,
        'protocol': PROTOCOL_MAP[pool.protocol],
        'lb_algorithm': BALANCE_MAP.get(pool.lb_algorithm, 'roundrobin'),
        'members': [],
        'health_monitor': '',
        'session_persistence': '',
        'admin_state_up': pool.admin_state_up,
        'provisioning_status': pool.provisioning_status
    }
    members = [_transform_member(x)
               for x in pool.members if _include_member(x)]
    ret_value['members'] = members
    if pool.healthmonitor and pool.healthmonitor.admin_state_up:
        ret_value['health_monitor'] = _transform_health_monitor(
            pool.healthmonitor)
    if pool.session_persistence:
        ret_value['session_persistence'] = _transform_session_persistence(
            pool.session_persistence)
    return ret_value


def _transform_session_persistence(persistence):
    """Transforms session persistence object

    :param persistence: the session persistence object
    :returns: dictionary of transformed session persistence values
    """
    return {
        'type': persistence.type,
        'cookie_name': persistence.cookie_name
    }


def _transform_member(member):
    """Transforms member object

    :param member: the member object
    :returns: dictionary of transformed member values
    """
    return {
        'id': member.id,
        'address': member.address,
        'protocol_port': member.protocol_port,
        'weight': member.weight,
        'admin_state_up': member.admin_state_up,
        'subnet_id': member.subnet_id,
        'provisioning_status': member.provisioning_status
    }


def _transform_health_monitor(monitor):
    """Transforms health monitor object

    :param monitor: the health monitor object
    :returns: dictionary of transformed health monitor values
    """
    return {
        'id': monitor.id,
        'type': monitor.type,
        'delay': monitor.delay,
        'timeout': monitor.timeout,
        'max_retries': monitor.max_retries,
        'http_method': monitor.http_method,
        'url_path': monitor.url_path,
        'expected_codes': '|'.join(
            _expand_expected_codes(monitor.expected_codes)),
        'admin_state_up': monitor.admin_state_up,
    }


def _include_member(member):
    """Helper for verifying member statues

    :param member: the member object
    :returns: boolean of status check
    """
    return (member.provisioning_status in
            MEMBER_STATUSES and member.admin_state_up)


def _expand_expected_codes(codes):
    """Expand the expected code string in set of codes

    :param codes: string of status codes
    :returns: list of status codes
    """

    retval = set()
    for code in codes.replace(',', ' ').split(' '):
        code = code.strip()

        if not code:
            continue
        elif '-' in code:
            low, hi = code.split('-')[:2]
            retval.update(
                str(i) for i in six.moves.range(int(low), int(hi) + 1))
        else:
            retval.add(code)
    return retval
