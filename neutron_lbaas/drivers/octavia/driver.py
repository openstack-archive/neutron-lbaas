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
from datetime import datetime
from functools import wraps
import threading
import time

from neutron import context as ncontext
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import excutils
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
    cfg.IntOpt(
        'request_poll_interval',
        default=3,
        help=_('Interval in seconds to poll octavia when an entity is created,'
               ' updated, or deleted.')
    ),
    cfg.IntOpt(
        'request_poll_timeout',
        default=100,
        help=_('Time to stop polling octavia when a status of an entity does '
               'not change.')
    )
]
cfg.CONF.register_opts(OPTS, 'octavia')


def thread_op(manager, entity, delete=False):
    context = ncontext.get_admin_context()
    poll_interval = cfg.CONF.octavia.request_poll_interval
    poll_timeout = cfg.CONF.octavia.request_poll_timeout
    start_dt = datetime.now()
    prov_status = None
    while (datetime.now() - start_dt).seconds < poll_timeout:
        octavia_lb = manager.driver.load_balancer.get(entity.root_loadbalancer)
        prov_status = octavia_lb.get('provisioning_status')
        LOG.debug("Octavia reports load balancer {0} has provisioning status "
                  "of {1}".format(entity.root_loadbalancer.id, prov_status))
        if prov_status == 'ACTIVE' or prov_status == 'DELETED':
            manager.successful_completion(context, entity, delete=delete)
            return
        elif prov_status == 'ERROR':
            manager.failed_completion(context, entity)
            return
        time.sleep(poll_interval)
    LOG.debug("Timeout has expired for load balancer {0} to complete an "
              "operation.  The last reported status was "
              "{1}".format(entity.root_loadbalancer.id, prov_status))
    manager.failed_completion(context, entity)


# A decorator for wrapping driver operations, which will automatically
# set the neutron object's status based on whether it sees an exception

def async_op(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        d = (func.__name__ == 'delete')
        try:
            r = func(*args, **kwargs)
            thread = threading.Thread(target=thread_op,
                                      args=(args[0], args[2]),
                                      kwargs={'delete': d})
            thread.setDaemon(True)
            thread.start()
            return r
        except Exception:
            with excutils.save_and_reraise_exception():
                args[0].failed_completion(args[1], args[2])
    return func_wrapper


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
        LOG.debug("Octavia Response Code: {0}".format(r.status_code))
        LOG.debug("Octavia Response Body: {0}".format(r.content))
        LOG.debug("Octavia Response Headers: {0}".format(r.headers))
        if method != 'DELETE':
            return r.json()

    def post(self, url, args):
        return self.request('POST', url, args)

    def put(self, url, args):
        return self.request('PUT', url, args)

    def delete(self, url):
        self.request('DELETE', url)

    def get(self, url):
        return self.request('GET', url)


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

    @async_op
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

    @async_op
    def update(self, context, old_lb, lb):
        args = {
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
        }
        self.driver.req.put(self._url(lb, lb.id), args)

    @async_op
    def delete(self, context, lb):
        self.driver.req.delete(self._url(lb, lb.id))

    @async_op
    def refresh(self, context, lb):
        pass

    def stats(self, context, lb):
        return {}  # todo

    def get(self, lb):
        return self.driver.req.get(self._url(lb, lb.id))


class ListenerManager(driver_base.BaseListenerManager):

    @staticmethod
    def _url(listener, id=None):
        s = '/v1/loadbalancers/%s/listeners' % listener.loadbalancer.id
        if id:
            s += '/%s' % id
        return s

    @classmethod
    def _write(cls, write_func, url, listener, create=True):
        sni_container_ids = [sni.tls_container_id
                             for sni in listener.sni_containers]
        args = {
            'name': listener.name,
            'description': listener.description,
            'enabled': listener.admin_state_up,
            'protocol': listener.protocol,
            'protocol_port': listener.protocol_port,
            'connection_limit': listener.connection_limit,
            'tls_certificate_id': listener.default_tls_container_id,
            'sni_containers': sni_container_ids,
        }
        if create:
            args['id'] = listener.id
        write_func(url, args)

    @async_op
    def create(self, context, listener):
        self._write(self.driver.req.post, self._url(listener), listener)

    @async_op
    def update(self, context, old_listener, listener):
        self._write(self.driver.req.put, self._url(listener, id=listener.id),
                    listener, create=False)

    @async_op
    def delete(self, context, listener):
        self.driver.req.delete(self._url(listener, id=listener.id))


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
    def _write(cls, write_func, url, pool, create=True):
        args = {
            'name': pool.name,
            'description': pool.description,
            'enabled': pool.admin_state_up,
            'protocol': pool.protocol,
            'lb_algorithm': pool.lb_algorithm,
        }
        if pool.session_persistence:
            args['session_persistence'] = {
                'type': pool.session_persistence.type,
                'cookie_name': pool.session_persistence.cookie_name,
            }
        if create:
            args['id'] = pool.id
        write_func(url, args)

    @async_op
    def create(self, context, pool):
        self._write(self.driver.req.post, self._url(pool), pool)

    @async_op
    def update(self, context, old_pool, pool):
        self._write(self.driver.req.put, self._url(pool, id=pool.id), pool,
                    create=False)

    @async_op
    def delete(self, context, pool):
        self.driver.req.delete(self._url(pool, id=pool.id))


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

    @async_op
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

    @async_op
    def update(self, context, old_member, member):
        args = {
            'enabled': member.admin_state_up,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
        }
        self.driver.req.put(self._url(member, member.id), args)

    @async_op
    def delete(self, context, member):
        self.driver.req.delete(self._url(member, member.id))


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    @staticmethod
    def _url(hm):
        s = '/v1/loadbalancers/%s/listeners/%s/pools/%s/healthmonitor' % (
            hm.pool.listener.loadbalancer.id,
            hm.pool.listener.id,
            hm.pool.id)
        return s

    @classmethod
    def _write(cls, write_func, url, hm):
        args = {
            'type': hm.type,
            'delay': hm.delay,
            'timeout': hm.timeout,
            'rise_threshold': hm.max_retries,
            'fall_threshold': hm.max_retries,
            'http_method': hm.http_method,
            'url_path': hm.url_path,
            'expected_codes': hm.expected_codes,
            'enabled': hm.admin_state_up,
        }
        write_func(cls._url(hm), args)

    @async_op
    def create(self, context, hm):
        self._write(self.driver.req.post, self._url(hm), hm)

    @async_op
    def update(self, context, old_hm, hm):
        self._write(self.driver.req.put, self._url(hm), hm)

    @async_op
    def delete(self, context, hm):
        self.driver.req.delete(self._url(hm))
