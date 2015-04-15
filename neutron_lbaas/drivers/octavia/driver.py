# Copyright 2015, A10 Networks
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
from oslo_log import log as logging
from oslo_serialization import jsonutils
import requests

from neutron_lbaas.drivers import driver_base

LOG = logging.getLogger(__name__)
VERSION = "1.0.0"

OPTS = [
    cfg.StrOpt(
        'base_url',
        default='http://127.0.0.1:9876',
        help=_('URL of Octavia controller root'),
    ),
]
cfg.CONF.register_opts(OPTS, 'octavia')


class OctaviaRequest(object):

    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, method, url, args=None, headers=None):
        if args:
            if not headers:
                headers = {
                    'Content-type': 'application/json'
                }
            args = jsonutils.dumps(args)
        LOG.debug("url = %s", '%s%s' % (self.base_url, str(url)))
        LOG.debug("args = %s", args)
        r = requests.request(method,
                             '%s%s' % (self.base_url, str(url)),
                             data=args,
                             headers=headers)
        LOG.debug("r = %s", r)
        if method != 'DELETE':
            return r.json()

    def post(self, url, args):
        return self.request('POST', url, args)

    def put(self, url, args):
        return self.request('PUT', url, args)

    def delete(self, url):
        self.request('DELETE', url)


class OctaviaDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(OctaviaDriver, self).__init__(plugin)

        self.req = OctaviaRequest(cfg.CONF.octavia.base_url)

        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)

        LOG.debug("OctaviaDriver: initialized, version=%s", VERSION)


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    @staticmethod
    def _url(lb, id=None):
        s = '/v1/loadbalancers'
        if id:
            s += '/%s' % id
        return s

    @driver_base.driver_op
    def create(self, context, lb):
        args = {
            'id': lb.id,
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
            'vip': {
                'subnet_id': lb.vip_subnet_id,
                'ip_address': lb.vip_address,
                'port_id': lb.vip_port_id,
            }
        }
        self.driver.req.post(self._url(lb), args)

    @driver_base.driver_op
    def update(self, context, old_lb, lb):
        args = {
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
        }
        self.driver.req.put(self._url(lb, lb.id), args)

    @driver_base.driver_op
    def delete(self, context, lb):
        self.driver.req.delete(self._url(lb, lb.id))

    @driver_base.driver_op
    def refresh(self, context, lb):
        pass

    @driver_base.driver_op
    def stats(self, context, lb):
        return {}  # todo


class ListenerManager(driver_base.BaseListenerManager):

    @staticmethod
    def _url(listener, id=None):
        s = '/v1/loadbalancers/%s/listeners' % listener.loadbalancer.id
        if id:
            s += '/%s' % id
        return s

    @classmethod
    def _write(cls, write_func, url, listener):
        sni_container_ids = [sni.tls_container_id
                             for sni in listener.sni_containers]
        args = {
            'id': listener.id,
            'name': listener.name,
            'description': listener.description,
            'enabled': listener.admin_state_up,
            'protocol': listener.protocol,
            'protocol_port': listener.protocol_port,
            'connection_limit': listener.connection_limit,
            'tls_certificate_id': listener.default_tls_container_id,
            'sni_containers': sni_container_ids,
        }
        write_func(cls._url(listener), args)

    @driver_base.driver_op
    def create(self, context, listener):
        self._write(self.driver.req.post, self._url(listener), listener)

    @driver_base.driver_op
    def update(self, context, old_listener, listener):
        self._write(self.driver.req.put, self._url(listener, listener.id),
                    listener)

    @driver_base.driver_op
    def delete(self, context, listener):
        self.driver.req.delete(self._url(listener, listener.id))


class PoolManager(driver_base.BasePoolManager):

    @staticmethod
    def _url(pool, id=None):
        s = '/v1/loadbalancers/%s/listeners/%s/pools' % (
            pool.listener.loadbalancer.id,
            pool.listener.id)
        if id:
            s += '/%s' % id
        return s

    @classmethod
    def _write(cls, write_func, url, pool):
        args = {
            'id': pool.id,
            'name': pool.name,
            'description': pool.description,
            'enabled': pool.admin_state_up,
            'protocol': pool.protocol,
            'lb_algorithm': pool.lb_algorithm,
        }
        if pool.sessionpersistence:
            args['session_persistence'] = {
                'type': pool.sessionpersistence.type,
                'cookie_name': pool.sessionpersistence.cookie_name,
            }
        write_func(cls._url(pool), args)

    @driver_base.driver_op
    def create(self, context, pool):
        self._write(self.driver.req.post, self._url(pool), pool)

    @driver_base.driver_op
    def update(self, context, old_pool, pool):
        self._write(self.driver.req.put, self._url(pool, pool.id), pool)

    @driver_base.driver_op
    def delete(self, context, pool):
        self.driver.req.delete(self._url(pool, pool.id))


class MemberManager(driver_base.BaseMemberManager):

    @staticmethod
    def _url(member, id=None):
        s = '/v1/loadbalancers/%s/listeners/%s/pools/%s/members' % (
            member.pool.listener.loadbalancer.id,
            member.pool.listener.id,
            member.pool.id)
        if id:
            s += '/%s' % id
        return s

    @driver_base.driver_op
    def create(self, context, member):
        args = {
            'id': member.id,
            'enabled': member.admin_state_up,
            'ip_address': member.address,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
            'subnet_id': member.subnet_id,
        }
        self.driver.req.post(self._url(member), args)

    @driver_base.driver_op
    def update(self, context, old_member, member):
        args = {
            'enabled': member.admin_state_up,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
        }
        self.driver.req.put(self._url(member, member.id), args)

    @driver_base.driver_op
    def delete(self, context, member):
        self.driver.req.delete(self._url(member, member.id))


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    @staticmethod
    def _url(hm, id=None):
        s = '/v1/loadbalancers/%s/listeners/%s/pools/%s/healthmonitor' % (
            hm.pool.listener.loadbalancer.id,
            hm.pool.listener.id,
            hm.pool.id)
        if id:
            s += '/%s' % id
        return s

    @classmethod
    def _write(cls, write_func, url, hm):
        args = {
            'id': hm.id,
            'type': hm.type,
            'delay': hm.delay,
            'timeout': hm.timeout,
            'http_method': hm.http_method,
            'url_path': hm.url_path,
            'expected_codes': hm.expected_codes,
            'enabled': hm.admin_state_up,
        }
        write_func(cls._url(hm), args)

    @driver_base.driver_op
    def create(self, context, hm):
        self._write(self.driver.req.post, self._url(hm), hm)

    @driver_base.driver_op
    def update(self, context, old_hm, hm):
        self._write(self.driver.req.put, self._url(hm, hm.id), hm)

    @driver_base.driver_op
    def delete(self, context, hm):
        self.driver.req.delete(self._url(hm, hm.id))
