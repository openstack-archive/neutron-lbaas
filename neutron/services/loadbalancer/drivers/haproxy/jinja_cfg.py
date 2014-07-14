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
import six

from neutron.agent.linux import utils
from neutron.plugins.common import constants as plugin_constants
from neutron.services.loadbalancer import constants
from oslo.config import cfg

PROTOCOL_MAP = {
    constants.PROTOCOL_TCP: 'tcp',
    constants.PROTOCOL_HTTP: 'http',
    constants.PROTOCOL_HTTPS: 'tcp'
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

ACTIVE_PENDING_STATUSES = plugin_constants.ACTIVE_PENDING_STATUSES + (
    plugin_constants.INACTIVE, plugin_constants.DEFERRED)

TEMPLATES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), 'templates/'))
JINJA_ENV = None

jinja_opts = [
    cfg.StrOpt(
        'jinja_config_template',
        default=os.path.join(
            TEMPLATES_DIR,
            'haproxy_v1.4.template'),
        help=_('Jinja template file for haproxy configuration'))
]

cfg.CONF.register_opts(jinja_opts, 'haproxy')


def save_config(conf_path, loadbalancer, socket_path=None,
                user_group='nogroup'):
    """Convert a logical configuration to the HAProxy version."""
    config_str = render_loadbalancer_obj(loadbalancer, user_group, socket_path)
    utils.replace_file(conf_path, config_str)


def _get_template():
    global JINJA_ENV
    if not JINJA_ENV:
        template_loader = jinja2.FileSystemLoader(
            searchpath=os.path.dirname(cfg.CONF.haproxy.jinja_config_template))
        JINJA_ENV = jinja2.Environment(
            loader=template_loader, trim_blocks=True, lstrip_blocks=True)
    return JINJA_ENV.get_template(os.path.basename(
        cfg.CONF.haproxy.jinja_config_template))


def render_loadbalancer_obj(loadbalancer, user_group, socket_path):
    loadbalancer = _transform_loadbalancer(loadbalancer)
    return _get_template().render({'loadbalancer': loadbalancer,
                                   'user_group': user_group,
                                   'stats_sock': socket_path},
                                  constants=constants)


def _transform_loadbalancer(loadbalancer):
    listeners = [_transform_listener(x) for x in loadbalancer.listeners]
    return {
        'name': loadbalancer.name,
        'vip_address': loadbalancer.vip_address,
        'listeners': listeners
    }


def _transform_listener(listener):
    ret_value = {
        'id': listener.id,
        'protocol_port': listener.protocol_port,
        'protocol': PROTOCOL_MAP[listener.protocol]
    }
    if listener.connection_limit and listener.connection_limit > -1:
        ret_value['connection_limit'] = listener.connection_limit
    if listener.default_pool:
        ret_value['default_pool'] = _transform_pool(listener.default_pool)

    return ret_value


def _transform_pool(pool):
    ret_value = {
        'id': pool.id,
        'protocol': PROTOCOL_MAP[pool.protocol],
        'lb_algorithm': BALANCE_MAP.get(pool.lb_algorithm, 'roundrobin'),
        'members': [],
        'health_monitor': '',
        'session_persistence': '',
        'admin_state_up': pool.admin_state_up,
        'status': pool.status
    }
    members = [_transform_member(x)
               for x in pool.members if _include_member(x)]
    ret_value['members'] = members
    if pool.healthmonitor:
        ret_value['health_monitor'] = _transform_health_monitor(
            pool.healthmonitor)
    if pool.sessionpersistence:
        ret_value['session_persistence'] = _transform_session_persistence(
            pool.sessionpersistence)
    return ret_value


def _transform_session_persistence(persistence):
    return {
        'type': persistence.type,
        'cookie_name': persistence.cookie_name
    }


def _transform_member(member):
    return {
        'id': member.id,
        'address': member.address,
        'protocol_port': member.protocol_port,
        'weight': member.weight,
        'admin_state_up': member.admin_state_up,
        'subnet_id': member.subnet_id,
        'status': member.status
    }


def _transform_health_monitor(monitor):
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
    return member.status in ACTIVE_PENDING_STATUSES and member.admin_state_up


def _expand_expected_codes(codes):
    """Expand the expected code string in set of codes.

    200-204 -> 200, 201, 202, 204
    200, 203 -> 200, 203
    """

    retval = set()
    for code in codes.replace(',', ' ').split(' '):
        code = code.strip()

        if not code:
            continue
        elif '-' in code:
            low, hi = code.split('-')[:2]
            retval.update(
                str(i) for i in six.moves.xrange(int(low), int(hi) + 1))
        else:
            retval.add(code)
    return retval
