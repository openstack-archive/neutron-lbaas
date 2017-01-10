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

import contextlib

from neutron.tests.unit.db import test_db_base_plugin_v2
from neutron_lib import constants
from neutron_lib import context
import webob.exc

from neutron_lbaas._i18n import _
from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.extensions import healthmonitor_max_retries_down
from neutron_lbaas.extensions import l7
from neutron_lbaas.extensions import lb_graph
from neutron_lbaas.extensions import lb_network_vip
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.extensions import sharedpools
from neutron_lbaas.services.loadbalancer import constants as lb_const


class ExtendedPluginAwareExtensionManager(object):
    def __init__(self, extension_aliases):
        self.extension_aliases = extension_aliases

    def get_resources(self):
        extensions_list = []
        if 'shared_pools' in self.extension_aliases:
            extensions_list.append(sharedpools)
        if 'l7' in self.extension_aliases:
            extensions_list.append(l7)
        if 'lb-graph' in self.extension_aliases:
            extensions_list.append(lb_graph)
        if 'lb_network_vip' in self.extension_aliases:
            extensions_list.append(lb_network_vip)
        if 'hm_max_retries_down' in self.extension_aliases:
            extensions_list.append(healthmonitor_max_retries_down)
        for extension in extensions_list:
            if 'RESOURCE_ATTRIBUTE_MAP' in extension.__dict__:
                loadbalancerv2.RESOURCE_ATTRIBUTE_MAP.update(
                    extension.RESOURCE_ATTRIBUTE_MAP)
            if 'SUB_RESOURCE_ATTRIBUTE_MAP' in extension.__dict__:
                loadbalancerv2.SUB_RESOURCE_ATTRIBUTE_MAP.update(
                    extension.SUB_RESOURCE_ATTRIBUTE_MAP)
            if 'EXTENDED_ATTRIBUTES_2_0' in extension.__dict__:
                for key in loadbalancerv2.RESOURCE_ATTRIBUTE_MAP.keys():
                    loadbalancerv2.RESOURCE_ATTRIBUTE_MAP[key].update(
                        extension.EXTENDED_ATTRIBUTES_2_0.get(key, {}))
        return loadbalancerv2.Loadbalancerv2.get_resources()

    def get_actions(self):
        return []

    def get_request_extensions(self):
        return []


class LbaasTestMixin(object):
    resource_keys = list(loadbalancerv2.RESOURCE_ATTRIBUTE_MAP.keys())
    resource_keys.extend(l7.RESOURCE_ATTRIBUTE_MAP.keys())
    resource_keys.extend(lb_graph.RESOURCE_ATTRIBUTE_MAP.keys())
    resource_keys.extend(lb_network_vip.EXTENDED_ATTRIBUTES_2_0.keys())
    resource_keys.extend(healthmonitor_max_retries_down.
                         EXTENDED_ATTRIBUTES_2_0.keys())
    resource_prefix_map = dict(
        (k, loadbalancerv2.LOADBALANCERV2_PREFIX)
        for k in resource_keys)

    def _get_loadbalancer_optional_args(self):
        return ('description', 'vip_address', 'admin_state_up', 'name',
                'listeners', 'vip_network_id', 'vip_subnet_id')

    def _create_loadbalancer(self, fmt, subnet_id,
                             expected_res_status=None, **kwargs):
        data = {'loadbalancer': {'vip_subnet_id': subnet_id,
                                 'tenant_id': self._tenant_id}}
        args = self._get_loadbalancer_optional_args()
        for arg in args:
            if arg in kwargs:
                if kwargs[arg] is not None:
                    data['loadbalancer'][arg] = kwargs[arg]
                else:
                    data['loadbalancer'].pop(arg, None)

        lb_req = self.new_create_request('loadbalancers', data, fmt)
        lb_res = lb_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, lb_res.status_int)

        return lb_res

    def _create_graph(self, fmt, subnet_id, expected_res_status=None,
                      **kwargs):
        data = {'vip_subnet_id': subnet_id, 'tenant_id': self._tenant_id}
        args = self._get_loadbalancer_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data[arg] = kwargs[arg]

        data = {'graph': {'loadbalancer': data, 'tenant_id': self._tenant_id}}
        lb_req = self.new_create_request('graphs', data, fmt)
        lb_res = lb_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, lb_res.status_int)

        return lb_res

    def _get_listener_optional_args(self):
        return ('name', 'description', 'default_pool_id', 'loadbalancer_id',
                'connection_limit', 'admin_state_up',
                'default_tls_container_ref', 'sni_container_refs')

    def _create_listener(self, fmt, protocol, protocol_port,
                         loadbalancer_id=None, default_pool_id=None,
                         expected_res_status=None, **kwargs):
        data = {'listener': {'protocol': protocol,
                             'protocol_port': protocol_port,
                             'tenant_id': self._tenant_id}}
        if loadbalancer_id:
            data['listener']['loadbalancer_id'] = loadbalancer_id
        if default_pool_id:
            data['listener']['default_pool_id'] = default_pool_id

        args = self._get_listener_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['listener'][arg] = kwargs[arg]

        listener_req = self.new_create_request('listeners', data, fmt)
        listener_res = listener_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, listener_res.status_int)

        return listener_res

    def _get_pool_optional_args(self):
        return 'name', 'description', 'admin_state_up', 'session_persistence'

    def _create_pool(self, fmt, protocol, lb_algorithm, listener_id=None,
                     loadbalancer_id=None, expected_res_status=None, **kwargs):
        data = {'pool': {'protocol': protocol,
                         'lb_algorithm': lb_algorithm,
                         'tenant_id': self._tenant_id}}
        if listener_id:
            data['pool']['listener_id'] = listener_id
        if loadbalancer_id:
            data['pool']['loadbalancer_id'] = loadbalancer_id

        args = self._get_pool_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['pool'][arg] = kwargs[arg]

        pool_req = self.new_create_request('pools', data, fmt)
        pool_res = pool_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, pool_res.status_int)

        return pool_res

    def _get_member_optional_args(self):
        return 'weight', 'admin_state_up', 'name'

    def _create_member(self, fmt, pool_id, address, protocol_port, subnet_id,
                       expected_res_status=None, **kwargs):
        data = {'member': {'address': address,
                           'protocol_port': protocol_port,
                           'subnet_id': subnet_id,
                           'tenant_id': self._tenant_id}}

        args = self._get_member_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['member'][arg] = kwargs[arg]
        member_req = self.new_create_request('pools',
                                             data,
                                             fmt=fmt,
                                             id=pool_id,
                                             subresource='members')
        member_res = member_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, member_res.status_int)

        return member_res

    def _get_healthmonitor_optional_args(self):
        return ('weight', 'admin_state_up', 'expected_codes', 'url_path',
                'http_method', 'name', 'max_retries_down')

    def _create_healthmonitor(self, fmt, pool_id, type, delay, timeout,
                              max_retries, expected_res_status=None, **kwargs):
        data = {'healthmonitor': {'type': type,
                                  'delay': delay,
                                  'timeout': timeout,
                                  'max_retries': max_retries,
                                  'pool_id': pool_id,
                                  'tenant_id': self._tenant_id}}

        args = self._get_healthmonitor_optional_args()
        for arg in args:
            if arg in kwargs and kwargs[arg] is not None:
                data['healthmonitor'][arg] = kwargs[arg]

        hm_req = self.new_create_request('healthmonitors', data, fmt=fmt)
        hm_res = hm_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(expected_res_status, hm_res.status_int)

        return hm_res

    def _add_optional_args(self, optional_args, data, **kwargs):
        for arg in optional_args:
            if arg in kwargs and kwargs[arg] is not None:
                data[arg] = kwargs[arg]

    def _get_l7policy_optional_args(self):
        return ('name', 'description', 'redirect_pool_id',
                'redirect_url', 'admin_state_up', 'position')

    def _create_l7policy(self, fmt, listener_id, action,
                         expected_res_status=None, **kwargs):
        data = {'l7policy': {'listener_id': listener_id,
                             'action': action,
                             'tenant_id': self._tenant_id}}

        optional_args = self._get_l7policy_optional_args()
        self._add_optional_args(optional_args, data['l7policy'], **kwargs)

        l7policy_req = self.new_create_request('l7policies', data, fmt)
        l7policy_res = l7policy_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(l7policy_res.status_int, expected_res_status)

        return l7policy_res

    def _get_l7rule_optional_args(self):
        return ('invert', 'key', 'admin_state_up')

    def _create_l7policy_rule(self, fmt, l7policy_id, type, compare_type,
                              value, expected_res_status=None, **kwargs):
        data = {'rule': {'type': type,
                         'compare_type': compare_type,
                         'value': value,
                         'tenant_id': self._tenant_id}}

        optional_args = self._get_l7rule_optional_args()
        self._add_optional_args(optional_args, data['rule'], **kwargs)

        rule_req = self.new_create_request('l7policies', data, fmt,
                                           id=l7policy_id,
                                           subresource='rules')
        rule_res = rule_req.get_response(self.ext_api)
        if expected_res_status:
            self.assertEqual(rule_res.status_int, expected_res_status)

        return rule_res

    @contextlib.contextmanager
    def loadbalancer(self, fmt=None, subnet=None, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        with test_db_base_plugin_v2.optional_ctx(
                subnet, self.subnet) as tmp_subnet:

            res = self._create_loadbalancer(fmt,
                                            tmp_subnet['subnet']['id'],
                                            **kwargs)
            if res.status_int >= webob.exc.HTTPClientError.code:
                exc = webob.exc.HTTPClientError(
                    explanation=_("Unexpected error code: %s") %
                    res.status_int)
                exc.code = res.status_int
                exc.status_code = res.status_int
                raise exc
            lb = self.deserialize(fmt or self.fmt, res)
            yield lb
            if not no_delete:
                self._delete('loadbalancers', lb['loadbalancer']['id'])

    @contextlib.contextmanager
    def graph(self, fmt=None, subnet=None, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        with test_db_base_plugin_v2.optional_ctx(
                subnet, self.subnet) as tmp_subnet:

            res = self._create_graph(fmt, tmp_subnet['subnet']['id'],
                                     **kwargs)
            if res.status_int >= webob.exc.HTTPClientError.code:
                exc = webob.exc.HTTPClientError(
                    explanation=_("Unexpected error code: %s") %
                    res.status_int
                )
                exc.code = res.status_int
                exc.status_code = res.status_int
                raise exc
            graph = self.deserialize(fmt or self.fmt, res)
            yield graph
            if not no_delete:
                # delete loadbalancer children if this was a loadbalancer
                # graph create call
                lb = graph['graph']['loadbalancer']
                for listener in lb.get('listeners', []):
                    pool = listener.get('default_pool')
                    if pool:
                        hm = pool.get('healthmonitor')
                        if hm:
                            self._delete('healthmonitors', hm['id'])
                        members = pool.get('members', [])
                        for member in members:
                            self._delete('pools', pool['id'],
                                         subresource='members',
                                         sub_id=member['id'])
                        self._delete('pools', pool['id'])
                    policies = listener.get('l7policies', [])
                    for policy in policies:
                        r_pool = policy.get('redirect_pool')
                        if r_pool:
                            r_hm = r_pool.get('healthmonitor')
                            if r_hm:
                                self._delete('healthmonitors', r_hm['id'])
                            r_members = r_pool.get('members', [])
                            for r_member in r_members:
                                self._delete('pools', r_pool['id'],
                                             subresource='members',
                                             sub_id=r_member['id'])
                            self._delete('pools', r_pool['id'])
                        self._delete('l7policies', policy['id'])
                    self._delete('listeners', listener['id'])
                self._delete('loadbalancers', lb['id'])

    @contextlib.contextmanager
    def listener(self, fmt=None, protocol='HTTP', loadbalancer_id=None,
                 protocol_port=80, default_pool_id=None, no_delete=False,
                 **kwargs):
        if not fmt:
            fmt = self.fmt

        if loadbalancer_id and default_pool_id:
            res = self._create_listener(fmt, protocol, protocol_port,
                                        loadbalancer_id=loadbalancer_id,
                                        default_pool_id=default_pool_id,
                                        **kwargs)
        elif loadbalancer_id:
            res = self._create_listener(fmt, protocol, protocol_port,
                                        loadbalancer_id=loadbalancer_id,
                                        **kwargs)
        else:
            res = self._create_listener(fmt, protocol, protocol_port,
                                        default_pool_id=default_pool_id,
                                        **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        listener = self.deserialize(fmt or self.fmt, res)
        yield listener
        if not no_delete:
            self._delete('listeners', listener['listener']['id'])

    @contextlib.contextmanager
    def pool(self, fmt=None, protocol='HTTP', lb_algorithm='ROUND_ROBIN',
             no_delete=False, listener_id=None,
             loadbalancer_id=None, **kwargs):
        if not fmt:
            fmt = self.fmt

        if listener_id and loadbalancer_id:
            res = self._create_pool(fmt,
                                    protocol=protocol,
                                    lb_algorithm=lb_algorithm,
                                    listener_id=listener_id,
                                    loadbalancer_id=loadbalancer_id,
                                    **kwargs)
        elif listener_id:
            res = self._create_pool(fmt,
                                    protocol=protocol,
                                    lb_algorithm=lb_algorithm,
                                    listener_id=listener_id,
                                    **kwargs)
        else:
            res = self._create_pool(fmt,
                                    protocol=protocol,
                                    lb_algorithm=lb_algorithm,
                                    loadbalancer_id=loadbalancer_id,
                                    **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        pool = self.deserialize(fmt or self.fmt, res)
        yield pool
        if not no_delete:
            self._delete('pools', pool['pool']['id'])

    @contextlib.contextmanager
    def member(self, fmt=None, pool_id='pool1id', address='127.0.0.1',
               protocol_port=80, subnet=None, no_delete=False,
               **kwargs):
        if not fmt:
            fmt = self.fmt
        subnet = subnet or self.test_subnet
        with test_db_base_plugin_v2.optional_ctx(
                subnet, self.subnet) as tmp_subnet:

            res = self._create_member(fmt,
                                      pool_id=pool_id,
                                      address=address,
                                      protocol_port=protocol_port,
                                      subnet_id=tmp_subnet['subnet']['id'],
                                      **kwargs)
            if res.status_int >= webob.exc.HTTPClientError.code:
                raise webob.exc.HTTPClientError(
                    explanation=_("Unexpected error code: %s") % res.status_int
                )

            member = self.deserialize(fmt or self.fmt, res)
        yield member
        if not no_delete:
            self._delete('pools', id=pool_id, subresource='members',
                         sub_id=member['member']['id'])

    @contextlib.contextmanager
    def healthmonitor(self, fmt=None, pool_id='pool1id', type='TCP', delay=1,
                      timeout=1, max_retries=2, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        res = self._create_healthmonitor(fmt,
                                         pool_id=pool_id,
                                         type=type,
                                         delay=delay,
                                         timeout=timeout,
                                         max_retries=max_retries,
                                         **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        healthmonitor = self.deserialize(fmt or self.fmt, res)
        yield healthmonitor
        if not no_delete:
            del_req = self.new_delete_request(
                'healthmonitors', fmt=fmt,
                id=healthmonitor['healthmonitor']['id'])
            del_res = del_req.get_response(self.ext_api)
            self.assertEqual(webob.exc.HTTPNoContent.code, del_res.status_int)

    @contextlib.contextmanager
    def l7policy(self, listener_id, fmt=None,
                 action=lb_const.L7_POLICY_ACTION_REJECT,
                 no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt

        res = self._create_l7policy(fmt,
                                    listener_id=listener_id,
                                    action=action,
                                    **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        l7policy = self.deserialize(fmt or self.fmt, res)
        yield l7policy
        if not no_delete:
            self.plugin.db.update_status(context.get_admin_context(),
                                         models.L7Policy,
                                         l7policy['l7policy']['id'],
                                         constants.ACTIVE)
            del_req = self.new_delete_request(
                'l7policies',
                fmt=fmt,
                id=l7policy['l7policy']['id'])
            del_res = del_req.get_response(self.ext_api)
            self.assertEqual(del_res.status_int,
                             webob.exc.HTTPNoContent.code)

    @contextlib.contextmanager
    def l7policy_rule(self, l7policy_id, fmt=None, value='value1',
                      type=lb_const.L7_RULE_TYPE_HOST_NAME,
                      compare_type=lb_const.L7_RULE_COMPARE_TYPE_EQUAL_TO,
                      no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt
        res = self._create_l7policy_rule(fmt,
                                         l7policy_id=l7policy_id,
                                         type=type,
                                         compare_type=compare_type,
                                         value=value,
                                         **kwargs)
        if res.status_int >= webob.exc.HTTPClientError.code:
            raise webob.exc.HTTPClientError(
                explanation=_("Unexpected error code: %s") % res.status_int
            )

        rule = self.deserialize(fmt or self.fmt, res)
        yield rule
        if not no_delete:
            self.plugin.db.update_status(context.get_admin_context(),
                                         models.L7Rule,
                                         rule['rule']['id'],
                                         constants.ACTIVE)
            del_req = self.new_delete_request(
                'l7policies',
                fmt=fmt,
                id=l7policy_id,
                subresource='rules',
                sub_id=rule['rule']['id'])
            del_res = del_req.get_response(self.ext_api)
            self.assertEqual(del_res.status_int,
                             webob.exc.HTTPNoContent.code)
