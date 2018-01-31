# Copyright 2017, Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools

from neutron.db import servicetype_db as st_db
from neutron.services import provider_configuration as pconf
from neutron_lib import exceptions as lib_exc
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
import requests

from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants

LOG = logging.getLogger(__name__)
VERSION = 'v2.0'
OCTAVIA_PROXY_CLIENT = (
    "LBaaS V2 Octavia Proxy/{version} "
    "(https://wiki.openstack.org/wiki/Octavia)").format(version=VERSION)
FILTER = ['vip_address', 'vip_network_id', 'flavor_id',
          'provider', 'redirect_pool_id']

LOADBALANCER = 'loadbalancer'
LISTENER = 'listener'
POOL = 'pool'
L7POLICY = 'l7policy'
L7POLICY_RULE = 'rule'
MEMBER = 'member'
HEALTH_MONITOR = 'healthmonitor'
STATUS = 'status'
GRAPH = 'graph'
STATS = 'stats'

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
]

cfg.CONF.register_opts(OPTS, 'octavia')


def add_provider_configuration(type_manager, service_type):
    type_manager.add_provider_configuration(
        service_type,
        pconf.ProviderConfiguration('neutron_lbaas_proxy'))


class LoadBalancerProxyPluginv2(loadbalancerv2.LoadBalancerPluginBaseV2):
    """Implementation of the Neutron Loadbalancer Proxy Plugin.

    This class proxies all requests/reponses to Octavia
    """

    supported_extension_aliases = ["lbaasv2",
                                   "shared_pools",
                                   "l7",
                                   "lbaas_agent_schedulerv2",
                                   "service-type",
                                   "lb-graph",
                                   "lb_network_vip",
                                   "hm_max_retries_down"]
    path_prefix = loadbalancerv2.LOADBALANCERV2_PREFIX

    def __init__(self):
        LOG.warning('neutron-lbaas is now deprecated. See: '
                    'https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                    'Deprecation')
        self.service_type_manager = st_db.ServiceTypeManager.get_instance()
        add_provider_configuration(
            self.service_type_manager, constants.LOADBALANCERV2)
        self.get = functools.partial(self.request, 'GET')
        self.post = functools.partial(self.request, 'POST')
        self.put = functools.partial(self.request, 'PUT')
        self.delete = functools.partial(self.request, 'DELETE')
        self.base_url = '{}/{}/lbaas'.format(cfg.CONF.octavia.base_url,
                                             VERSION)

    def get_plugin_type(self):
        return constants.LOADBALANCERV2

    def get_plugin_description(self):
        return "Neutron LoadBalancer Proxy Plugin"

    def request(self, method, url, token=None, args=None, headers=None,
                accepted_codes=[200, 201, 202, 204]):
        params = {}
        if args:
            # extract filter and fields
            if 'filters' in args:
                params = args.pop('filters')
            if 'fields' in args:
                params['fields'] = args.pop('fields')
            args = jsonutils.dumps(args)
        if not headers:
            headers = {
                'Content-type': 'application/json',
                'X-Auth-Token': token
            }
        headers['User-Agent'] = OCTAVIA_PROXY_CLIENT

        url = '{}/{}'.format(self.base_url, str(url))
        LOG.debug("url = %s", url)
        LOG.debug("args = %s", args)
        LOG.debug("params = %s", str(params))
        r = requests.request(method, url, data=args, params=params,
                             headers=headers)
        LOG.debug("Octavia Response Code: {0}".format(r.status_code))
        LOG.debug("Octavia Response Body: {0}".format(r.content))
        LOG.debug("Octavia Response Headers: {0}".format(r.headers))

        if r.status_code in accepted_codes:
            if method != 'DELETE':
                return r.json()
        elif r.status_code == 413:
            e = lib_exc.OverQuota()
            e.msg = str(r.content)
            raise e
        elif r.status_code == 409:
            e = lib_exc.Conflict()
            e.msg = str(r.content)
            raise e
        elif r.status_code == 401:
            e = lib_exc.NotAuthorized()
            e.msg = str(r.content)
            raise e
        elif r.status_code == 404:
            e = lib_exc.NotFound()
            e.msg = str(r.content)
            raise e
        elif r.status_code == 400:
            e = lib_exc.BadRequest(resource="", msg="")
            e.msg = str(r.content)
            raise e
        else:
            raise loadbalancerv2.DriverError(msg=str(r.content))

    def _filter(self, keys, map):
        """Filter the args map

        keys: The keys to filter out
        map: the args in a map

        NOTE: This returns a deep copy - leaving the original alone
        """

        res = {}
        for k in map:
            if k not in keys:
                if map[k]:
                    res[k] = map[k]
        if 'tenant_id' in res:
            res['project_id'] = res.pop('tenant_id')
        return res

    def pluralize(self, name):
        if name.endswith('y'):
            return name[:-1] + "ies"
        elif not name.endswith('s'):
            return "{}s".format(name)
        return name

    def _path(self, resource, sub_resource, resource_id):
        url = resource
        if sub_resource:
            url = "{}/{}/{}".format(self.pluralize(resource),
                                    resource_id, sub_resource)
        return self.pluralize(url)

    def _create_resource(self, resource, context, res, sub_resource=None,
                         resource_id=None):
        # clean up the map
        resource_ = resource if not sub_resource else sub_resource
        r = self._filter(FILTER, res[resource_])
        r = self.post(self._path(resource, sub_resource, resource_id),
                      context.auth_token, {resource_: r})
        return r[resource_]

    def _get_resources(self, resource, context, filters=None, fields=None,
                       sub_resource=None, resource_id=None,
                       pass_through=False):
        # not sure how to test that or if we even support sorting/filtering?
        resource_ = resource if not sub_resource else sub_resource
        args = {}
        if filters:
            if 'tenant_id' in filters:
                filters['project_id'] = filters.pop('tenant_id')
            args['filters'] = filters
        if fields:
            args['fields'] = fields
        res = self.get(self._path(resource, sub_resource, resource_id),
                       context.auth_token, args)
        return res[self.pluralize(resource_)] if not pass_through else res

    def _get_resource(self, resource, context, id, fields=None,
                      sub_resource=None, resource_id=None):
        # not sure how to test that or if we even support sorting/filtering?
        args = {}
        if fields:
            args['fields'] = fields
        resource_ = resource if not sub_resource else sub_resource
        res = self.get('{}/{}'.format(
            self._path(resource, sub_resource, resource_id), id),
                       context.auth_token, args)
        return res[resource_]

    def _update_resource(self, resource, context, id, res,
                         sub_resource=None, resource_id=None):
        # clean up the map
        resource_ = resource if not sub_resource else sub_resource
        r = self._filter(FILTER, res[resource_])
        res = self.put('{}/{}'.format(self._path(
            resource, sub_resource, resource_id), id),
                       context.auth_token,
                       {resource_: r})
        return res[resource_]

    def _delete_resource(self, resource, context, id,
                         sub_resource=None, resource_id=None):
        self.delete('{}/{}'.format(self._path(
            resource, sub_resource, resource_id), id),
            context.auth_token)

    def create_loadbalancer(self, context, loadbalancer):
        return self._create_resource(LOADBALANCER, context, loadbalancer)

    def get_loadbalancers(self, context, filters=None, fields=None):
        return self._get_resources(LOADBALANCER, context, filters, fields)

    def get_loadbalancer(self, context, id, fields=None):
        return self._get_resource(LOADBALANCER, context, id, fields)

    def update_loadbalancer(self, context, id, loadbalancer):
        return self._update_resource(LOADBALANCER, context, id, loadbalancer)

    def delete_loadbalancer(self, context, id):
        self._delete_resource(LOADBALANCER, context, id)

    def create_listener(self, context, listener):
        return self._create_resource(LISTENER, context, listener)

    def get_listener(self, context, id, fields=None):
        return self._get_resource(LISTENER, context, id, fields)

    def get_listeners(self, context, filters=None, fields=None):
        return self._get_resources(LISTENER, context, filters, fields)

    def update_listener(self, context, id, listener):
        return self._update_resource(LISTENER, context, id, listener)

    def delete_listener(self, context, id):
        return self._delete_resource(LISTENER, context, id)

    def get_pools(self, context, filters=None, fields=None):
        return self._get_resources(POOL, context, filters, fields)

    def get_pool(self, context, id, fields=None):
        return self._get_resource(POOL, context, id, fields)

    def create_pool(self, context, pool):
        return self._create_resource(POOL, context, pool)

    def update_pool(self, context, id, pool):
        return self._update_resource(POOL, context, id, pool)

    def delete_pool(self, context, id):
        return self._delete_resource(POOL, context, id)

    def get_pool_members(self, context, pool_id,
                         filters=None,
                         fields=None):
        return self._get_resources(POOL, context, filters, fields,
                                   MEMBER, pool_id)

    def get_pool_member(self, context, id, pool_id,
                        fields=None):
        return self._get_resource(POOL, context, id, fields,
                                  MEMBER, pool_id)

    def create_pool_member(self, context, pool_id, member):
        return self._create_resource(POOL, context, member, MEMBER, pool_id)

    def update_pool_member(self, context, id, pool_id, member):
        return self._update_resource(POOL, context, id, member,
                                     MEMBER, pool_id)

    def delete_pool_member(self, context, id, pool_id):
        return self._delete_resource(POOL, context, id, MEMBER, pool_id)

    def get_healthmonitors(self, context, filters=None, fields=None):
        return self._get_resources(HEALTH_MONITOR, context, filters, fields)

    def get_healthmonitor(self, context, id, fields=None):
        return self._get_resource(HEALTH_MONITOR, context, id, fields)

    def create_healthmonitor(self, context, healthmonitor):
        return self._create_resource(HEALTH_MONITOR, context, healthmonitor)

    def update_healthmonitor(self, context, id, healthmonitor):
        return self._update_resource(HEALTH_MONITOR, context,
                                     id, healthmonitor)

    def delete_healthmonitor(self, context, id):
        return self._delete_resource(HEALTH_MONITOR, context, id)

    def get_members(self, context, filters=None, fields=None):
        pass

    def get_member(self, context, id, fields=None):
        pass

    def statuses(self, context, loadbalancer_id):
        return self._get_resources(LOADBALANCER, context, sub_resource=STATUS,
                                   resource_id=loadbalancer_id,
                                   pass_through=True)

    def get_l7policies(self, context, filters=None, fields=None):
        return self._get_resources(L7POLICY, context, filters, fields)

    def get_l7policy(self, context, id, fields=None):
        return self._get_resource(L7POLICY, context, id, fields)

    def create_l7policy(self, context, l7policy):
        return self._create_resource(L7POLICY, context, l7policy)

    def update_l7policy(self, context, id, l7policy):
        return self._update_resource(L7POLICY, context, id, l7policy)

    def delete_l7policy(self, context, id):
        return self._delete_resource(L7POLICY, context, id)

    def get_l7policy_rules(self, context, l7policy_id,
                           filters=None, fields=None):
        return self._get_resources(L7POLICY, context, filters, fields,
                                   L7POLICY_RULE, l7policy_id)

    def get_l7policy_rule(self, context, id, l7policy_id, fields=None):
        return self._get_resource(L7POLICY, context, id, fields,
                                  L7POLICY_RULE, l7policy_id)

    def create_l7policy_rule(self, context, rule, l7policy_id):
        return self._create_resource(L7POLICY, context, rule, L7POLICY_RULE,
                                     l7policy_id)

    def update_l7policy_rule(self, context, id, rule, l7policy_id):
        return self._update_resource(L7POLICY, context, id, rule,
                                     L7POLICY_RULE, l7policy_id)

    def delete_l7policy_rule(self, context, id, l7policy_id):
        return self._delete_resource(L7POLICY, context, id, L7POLICY_RULE,
                                     l7policy_id)

    def create_graph(self, context, graph):
        return self._create_resource(GRAPH, context, graph)

    def stats(self, context, loadbalancer_id):
        return self._get_resources(LOADBALANCER, context, sub_resource=STATS,
                                   resource_id=loadbalancer_id,
                                   pass_through=True)
