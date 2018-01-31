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

from neutron_lib import context as ncontext
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_service import service
from oslo_utils import excutils
import requests

from neutron_lbaas._i18n import _
from neutron_lbaas.common import exceptions
from neutron_lbaas.common import keystone
from neutron_lbaas.drivers import driver_base
from neutron_lbaas.drivers.octavia import octavia_messaging_consumer
from neutron_lbaas.services.loadbalancer import constants

LOG = logging.getLogger(__name__)
VERSION = "1.0.1"

OPTS = [
    cfg.StrOpt(
        'base_url',
        default='http://127.0.0.1:9876',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('URL of Octavia controller root'),
    ),
    cfg.IntOpt(
        'request_poll_interval',
        default=3,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Interval in seconds to poll octavia when an entity is created,'
               ' updated, or deleted.')
    ),
    cfg.IntOpt(
        'request_poll_timeout',
        default=100,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Time to stop polling octavia when a status of an entity does '
               'not change.')
    ),
    cfg.BoolOpt(
        'allocates_vip',
        default=False,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('True if Octavia will be responsible for allocating the VIP.'
               ' False if neutron-lbaas will allocate it and pass to Octavia.')
    )
]

cfg.CONF.register_opts(OPTS, 'octavia')


def thread_op(manager, entity, delete=False, lb_create=False):
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
            kwargs = {'delete': delete}
            if manager.driver.allocates_vip and lb_create:
                kwargs['lb_create'] = lb_create
                # TODO(blogan): drop fk constraint on vip_port_id to ports
                # table because the port can't be removed unless the load
                # balancer has been deleted.  Until then we won't populate the
                # vip_port_id field.
                # entity.vip_port_id = octavia_lb.get('vip').get('port_id')
                entity.vip_address = octavia_lb.get('vip').get('ip_address')
            manager.successful_completion(context, entity, **kwargs)
            return
        elif prov_status == 'ERROR':
            manager.failed_completion(context, entity)
            return
        time.sleep(poll_interval)
    LOG.warning("Timeout has expired for load balancer {0} to complete an "
              "operation.  The last reported status was "
              "{1}".format(entity.root_loadbalancer.id, prov_status))
    manager.failed_completion(context, entity)


# A decorator for wrapping driver operations, which will automatically
# set the neutron object's status based on whether it sees an exception

def async_op(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        d = (func.__name__ == 'delete' or func.__name__ == 'delete_cascade')
        lb_create = ((func.__name__ == 'create') and
                     isinstance(args[0], LoadBalancerManager))
        try:
            r = func(*args, **kwargs)
            thread = threading.Thread(target=thread_op,
                                      args=(args[0], args[2]),
                                      kwargs={'delete': d,
                                              'lb_create': lb_create})
            thread.setDaemon(True)
            thread.start()
            return r
        except Exception:
            with excutils.save_and_reraise_exception():
                args[0].failed_completion(args[1], args[2])
    return func_wrapper


class OctaviaRequest(object):

    def __init__(self, base_url, auth_session):
        self.base_url = base_url
        self.auth_session = auth_session

    def request(self, method, url, args=None, headers=None):
        if args:
            args = jsonutils.dumps(args)

        if not headers or not headers.get('X-Auth-Token'):
            headers = headers or {
                'Content-type': 'application/json',
            }
            headers['X-Auth-Token'] = self.auth_session.get_token()

        LOG.debug("url = %s", '%s%s' % (self.base_url, str(url)))
        LOG.debug("args = %s", args)
        r = requests.request(method,
                             '%s%s' % (self.base_url, str(url)),
                             data=args,
                             headers=headers)
        LOG.debug("Octavia Response Code: {0}".format(r.status_code))
        LOG.debug("Octavia Response Body: {0}".format(r.content))
        LOG.debug("Octavia Response Headers: {0}".format(r.headers))
        # We need to raise Octavia errors up to neutron API.
        try:
            fault_string = jsonutils.loads(r.content)['faultstring']
        except Exception:
            fault_string = "Unknown Octavia error."
        if r.status_code == 400:
            raise exceptions.BadRequestException(fault_string=fault_string)
        elif r.status_code == 401:
            raise exceptions.NotAuthorizedException(fault_string=fault_string)
        elif r.status_code == 403:
            raise exceptions.NotAuthorizedException(fault_string=fault_string)
        elif r.status_code == 404:
            raise exceptions.NotFoundException(fault_string=fault_string)
        elif r.status_code == 409:
            raise exceptions.ConflictException(fault_string=fault_string)
        elif r.status_code == 500:
            raise exceptions.UnknownException(fault_string=fault_string)
        elif r.status_code == 503:
            raise exceptions.ServiceUnavailableException(
                fault_string=fault_string)

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
        self.req = OctaviaRequest(cfg.CONF.octavia.base_url,
                                  keystone.get_session())

        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)
        self.l7policy = L7PolicyManager(self)
        self.l7rule = L7RuleManager(self)
        self.octavia_consumer = octavia_messaging_consumer.OctaviaConsumer(
            self)
        service.launch(cfg.CONF, self.octavia_consumer)
        LOG.debug("OctaviaDriver: initialized, version=%s", VERSION)

    @property
    def allocates_vip(self):
        return self.load_balancer.allocates_vip


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    @staticmethod
    def _url(lb, id=None):
        s = '/v1/loadbalancers'
        if id:
            s += '/%s' % id
        return s

    @property
    def allows_create_graph(self):
        return True

    @property
    def allows_healthmonitor_thresholds(self):
        return True

    @property
    def allocates_vip(self):
        return cfg.CONF.octavia.allocates_vip

    @property
    def deletes_cascade(self):
        return True

    def _construct_args(self, db_lb, create=True, graph=False):
        args = {'name': db_lb.name,
                'description': db_lb.description,
                'enabled': db_lb.admin_state_up}
        if not create:
            return args

        create_args = {'project_id': db_lb.tenant_id, 'id': db_lb.id,
                       'vip': {'subnet_id': db_lb.vip_subnet_id,
                               'ip_address': db_lb.vip_address,
                               'port_id': db_lb.vip_port_id}}
        args.update(create_args)

        if not graph:
            return args

        if db_lb.listeners:
            args['listeners'] = []
        for db_listener in db_lb.listeners:
            listener_args = self.driver.listener._construct_args(db_listener,
                                                                 graph=True)
            args['listeners'].append(listener_args)
        return args

    def create_and_allocate_vip(self, context, lb):
        self.create(context, lb)

    @async_op
    def create(self, context, lb):
        graph = (lb.listeners and len(lb.listeners) > 0)
        args = self._construct_args(lb, graph=graph)
        self.driver.req.post(self._url(lb), args)

    @async_op
    def update(self, context, old_lb, lb):
        args = self._construct_args(lb, create=False)
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

    @async_op
    def delete_cascade(self, context, lb):
        self.driver.req.delete(self._url(lb, lb.id) + '/delete_cascade')


class ListenerManager(driver_base.BaseListenerManager):

    @staticmethod
    def _url(listener, id=None):
        s = '/v1/loadbalancers/%s/listeners' % listener.loadbalancer.id
        if id:
            s += '/%s' % id
        return s

    def _construct_args(self, listener, create=True, graph=False):
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
            'default_pool_id': listener.default_pool_id,
            'sni_containers': sni_container_ids
        }

        if not create:
            return args

        args['project_id'] = listener.tenant_id
        args['id'] = listener.id

        if not graph:
            return args

        del args['default_pool_id']

        if listener.default_pool:
            pool = listener.default_pool
            args['default_pool'] = self.driver.pool._construct_args(pool,
                                                                    graph=True)
        if listener.l7_policies:
            args['l7policies'] = []
            l7_policies = listener.l7_policies
            for l7_policy in l7_policies:
                l7_policy_args = self.driver.l7policy._construct_args(
                    l7_policy, graph=True)
                args['l7policies'].append(l7_policy_args)
        return args

    @async_op
    def create(self, context, listener):
        args = self._construct_args(listener)
        self.driver.req.post(self._url(listener), args)

    @async_op
    def update(self, context, old_listener, listener):
        args = self._construct_args(listener, create=False)
        self.driver.req.put(self._url(listener, id=listener.id), args)

    @async_op
    def delete(self, context, listener):
        self.driver.req.delete(self._url(listener, id=listener.id))


class PoolManager(driver_base.BasePoolManager):

    @staticmethod
    def _url(pool, id=None):
        s = '/v1/loadbalancers/%s/pools' % (
            pool.loadbalancer.id)
        if id:
            s += '/%s' % id
        return s

    def _construct_args(self, pool, create=True, graph=False):
        args = {
            'name': pool.name,
            'description': pool.description,
            'enabled': pool.admin_state_up,
            'protocol': pool.protocol,
            'lb_algorithm': pool.lb_algorithm
        }
        if pool.session_persistence:
            args['session_persistence'] = {
                'type': pool.session_persistence.type,
                'cookie_name': pool.session_persistence.cookie_name,
            }
        else:
            args['session_persistence'] = None

        if not create:
            return args

        args['project_id'] = pool.tenant_id
        args['id'] = pool.id
        if pool.listeners:
            args['listener_id'] = pool.listeners[0].id

        if not graph:
            return args

        if pool.members:
            args['members'] = []
            for member in pool.members:
                member_args = self.driver.member._construct_args(member)
                args['members'].append(member_args)
        if pool.healthmonitor:
            hm_args = self.driver.health_monitor._construct_args(
                pool.healthmonitor)
            args['health_monitor'] = hm_args
        return args

    @async_op
    def create(self, context, pool):
        args = self._construct_args(pool)
        self.driver.req.post(self._url(pool), args)

    @async_op
    def update(self, context, old_pool, pool):
        args = self._construct_args(pool, create=False)
        self.driver.req.put(self._url(pool, id=pool.id), args)

    @async_op
    def delete(self, context, pool):
        self.driver.req.delete(self._url(pool, id=pool.id))


class MemberManager(driver_base.BaseMemberManager):

    @staticmethod
    def _url(member, id=None):
        s = '/v1/loadbalancers/%s/pools/%s/members' % (
            member.pool.loadbalancer.id,
            member.pool.id)
        if id:
            s += '/%s' % id
        return s

    def _construct_args(self, member, create=True):
        args = {
            'enabled': member.admin_state_up,
            'protocol_port': member.protocol_port,
            'weight': member.weight
        }
        if not create:
            return args

        create_args = {
            'id': member.id,
            'ip_address': member.address,
            'subnet_id': member.subnet_id,
            'project_id': member.tenant_id
        }
        args.update(create_args)

        return args

    @async_op
    def create(self, context, member):
        args = self._construct_args(member)
        self.driver.req.post(self._url(member), args)

    @async_op
    def update(self, context, old_member, member):
        args = self._construct_args(member, create=False)
        self.driver.req.put(self._url(member, member.id), args)

    @async_op
    def delete(self, context, member):
        self.driver.req.delete(self._url(member, member.id))


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    @staticmethod
    def _url(hm):
        s = '/v1/loadbalancers/%s/pools/%s/healthmonitor' % (
            hm.pool.loadbalancer.id,
            hm.pool.id)
        return s

    def _construct_args(self, hm, create=True):
        args = {
            'type': hm.type,
            'delay': hm.delay,
            'timeout': hm.timeout,
            'rise_threshold': hm.max_retries,
            'fall_threshold': hm.max_retries_down,
            'http_method': hm.http_method,
            'url_path': hm.url_path,
            'expected_codes': hm.expected_codes,
            'enabled': hm.admin_state_up
        }
        if create:
            args['project_id'] = hm.tenant_id
        return args

    @async_op
    def create(self, context, hm):
        args = self._construct_args(hm)
        self.driver.req.post(self._url(hm), args)

    @async_op
    def update(self, context, old_hm, hm):
        args = self._construct_args(hm, create=False)
        self.driver.req.put(self._url(hm), args)

    @async_op
    def delete(self, context, hm):
        self.driver.req.delete(self._url(hm))


class L7PolicyManager(driver_base.BaseL7PolicyManager):

    @staticmethod
    def _url(l7p, id=None):
        s = '/v1/loadbalancers/%s/listeners/%s/l7policies' % (
            l7p.listener.loadbalancer.id,
            l7p.listener.id)
        if id:
            s += '/%s' % id
        return s

    def _construct_args(self, l7p, create=True, graph=False):
        args = {
            'name': l7p.name,
            'description': l7p.description,
            'action': l7p.action,
            'redirect_url': l7p.redirect_url,
            'position': l7p.position,
            'enabled': l7p.admin_state_up
        }
        if args['action'] == constants.L7_POLICY_ACTION_REJECT:
            del args['redirect_url']
        elif args['action'] == constants.L7_POLICY_ACTION_REDIRECT_TO_POOL:
            args['redirect_pool_id'] = l7p.redirect_pool_id
            del args['redirect_url']
        elif args['action'] == constants.L7_POLICY_ACTION_REDIRECT_TO_URL:
            if args.get('redirect_pool_id'):
                del args['redirect_pool_id']
        if not create:
            return args

        args['id'] = l7p.id

        if not graph:
            return args

        if (l7p.redirect_pool and l7p.action ==
                constants.L7_POLICY_ACTION_REDIRECT_TO_POOL):
            del args['redirect_pool_id']
            pool_args = self.driver.pool._construct_args(l7p.redirect_pool,
                                                         graph=True)
            args['redirect_pool'] = pool_args
        if l7p.rules:
            args['l7rules'] = []
            for rule in l7p.rules:
                rule_args = self.driver.l7rule._construct_args(rule)
                args['l7rules'].append(rule_args)
        return args

    @async_op
    def create(self, context, l7p):
        args = self._construct_args(l7p)
        self.driver.req.post(self._url(l7p), args)

    @async_op
    def update(self, context, old_l7p, l7p):
        args = self._construct_args(l7p, create=False)
        self.driver.req.put(self._url(l7p, id=l7p.id), args)

    @async_op
    def delete(self, context, l7p):
        self.driver.req.delete(self._url(l7p, id=l7p.id))


class L7RuleManager(driver_base.BaseL7RuleManager):

    @staticmethod
    def _url(l7r, id=None):
        s = '/v1/loadbalancers/%s/listeners/%s/l7policies/%s/l7rules' % (
            l7r.policy.listener.loadbalancer.id,
            l7r.policy.listener.id,
            l7r.policy.id)
        if id:
            s += '/%s' % id
        return s

    @classmethod
    def _construct_args(cls, l7r, create=True):
        args = {
            'type': l7r.type,
            'compare_type': l7r.compare_type,
            'key': l7r.key,
            'value': l7r.value,
            'invert': l7r.invert
        }
        if create:
            args['id'] = l7r.id
        return args

    @async_op
    def create(self, context, l7r):
        args = self._construct_args(l7r)
        self.driver.req.post(self._url(l7r), args)

    @async_op
    def update(self, context, old_l7r, l7r):
        args = self._construct_args(l7r, create=False)
        self.driver.req.put(self._url(l7r, id=l7r.id), args)

    @async_op
    def delete(self, context, l7r):
        self.driver.req.delete(self._url(l7r, id=l7r.id))
