# Copyright 2014 OpenStack Foundation.
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
#

from neutron.tests import base as n_base
from neutron.tests.unit.db import test_db_base_plugin_v2
from neutron.tests.unit.extensions import base as ext_base
from neutron.tests.unit.extensions import test_quotasv2
from neutron.tests.unit import testlib_api
from testtools import matchers


class BaseTestCase(n_base.BaseTestCase):
    pass


class NeutronDbPluginV2TestCase(
    test_db_base_plugin_v2.NeutronDbPluginV2TestCase):

    def new_list_request(self, resource, fmt=None, params=None, id=None,
                         subresource=None):
        return self._req(
            'GET', resource, None, fmt, params=params, subresource=subresource,
            id=id
        )

    def new_show_request(self, resource, id, fmt=None,
                         subresource=None, sub_id=None, fields=None):
        if fields:
            params = "&".join(["fields=%s" % x for x in fields])
        else:
            params = None
        return self._req('GET', resource, None, fmt, id=id,
                         params=params, subresource=subresource, sub_id=sub_id)

    def new_update_request(self, resource, data, id, fmt=None,
                           subresource=None, context=None, sub_id=None):
        return self._req(
            'PUT', resource, data, fmt, id=id, subresource=subresource,
            context=context, sub_id=sub_id
        )

    def _test_list_with_sort(self, resource,
                             items, sorts, resources=None,
                             query_params='',
                             id=None,
                             subresource=None,
                             subresources=None):
        query_str = query_params
        for key, direction in sorts:
            query_str = query_str + "&sort_key=%s&sort_dir=%s" % (key,
                                                                  direction)
        if not resources:
            resources = '%ss' % resource
        if subresource and not subresources:
            subresources = '%ss' % subresource
        req = self.new_list_request(resources,
                                    params=query_str,
                                    id=id,
                                    subresource=subresources)
        api = self._api_for_resource(resources)
        res = self.deserialize(self.fmt, req.get_response(api))
        if subresource:
            resource = subresource
        if subresources:
            resources = subresources
        resource = resource.replace('-', '_')
        resources = resources.replace('-', '_')
        expected_res = [item[resource]['id'] for item in items]
        self.assertEqual(expected_res, [n['id'] for n in res[resources]])

    def _test_list_with_pagination(self, resource, items, sort,
                                   limit, expected_page_num,
                                   resources=None,
                                   query_params='',
                                   verify_key='id',
                                   id=None,
                                   subresource=None,
                                   subresources=None):
        if not resources:
            resources = '%ss' % resource
        if subresource and not subresources:
            subresources = '%ss' % subresource
        query_str = query_params + '&' if query_params else ''
        query_str = query_str + ("limit=%s&sort_key=%s&"
                                 "sort_dir=%s") % (limit, sort[0], sort[1])
        req = self.new_list_request(resources, params=query_str, id=id,
                                    subresource=subresources)
        items_res = []
        page_num = 0
        api = self._api_for_resource(resources)
        if subresource:
            resource = subresource
        if subresources:
            resources = subresources
        resource = resource.replace('-', '_')
        resources = resources.replace('-', '_')
        while req:
            page_num = page_num + 1
            res = self.deserialize(self.fmt, req.get_response(api))
            self.assertThat(len(res[resources]),
                            matchers.LessThan(limit + 1))
            items_res = items_res + res[resources]
            req = None
            if '%s_links' % resources in res:
                for link in res['%s_links' % resources]:
                    if link['rel'] == 'next':
                        content_type = 'application/%s' % self.fmt
                        req = testlib_api.create_request(link['href'],
                                                         '', content_type)
                        self.assertEqual(len(res[resources]),
                                         limit)
        self.assertEqual(expected_page_num, page_num)
        self.assertEqual([item[resource][verify_key] for item in items],
                         [n[verify_key] for n in items_res])

    def _test_list_with_pagination_reverse(self, resource, items, sort,
                                           limit, expected_page_num,
                                           resources=None,
                                           query_params='',
                                           id=None,
                                           subresource=None,
                                           subresources=None):
        if not resources:
            resources = '%ss' % resource
        if subresource and not subresources:
            subresources = '%ss' % subresource
        resource = resource.replace('-', '_')
        api = self._api_for_resource(resources)
        if subresource:
            marker = items[-1][subresource]['id']
        else:
            marker = items[-1][resource]['id']
        query_str = query_params + '&' if query_params else ''
        query_str = query_str + ("limit=%s&page_reverse=True&"
                                 "sort_key=%s&sort_dir=%s&"
                                 "marker=%s") % (limit, sort[0], sort[1],
                                                 marker)
        req = self.new_list_request(resources, params=query_str, id=id,
                                    subresource=subresources)
        if subresource:
            resource = subresource
        if subresources:
            resources = subresources
        item_res = [items[-1][resource]]
        page_num = 0
        resources = resources.replace('-', '_')
        while req:
            page_num = page_num + 1
            res = self.deserialize(self.fmt, req.get_response(api))
            self.assertThat(len(res[resources]),
                            matchers.LessThan(limit + 1))
            res[resources].reverse()
            item_res = item_res + res[resources]
            req = None
            if '%s_links' % resources in res:
                for link in res['%s_links' % resources]:
                    if link['rel'] == 'previous':
                        content_type = 'application/%s' % self.fmt
                        req = testlib_api.create_request(link['href'],
                                                         '', content_type)
                        self.assertEqual(len(res[resources]),
                                         limit)
        self.assertEqual(expected_page_num, page_num)
        expected_res = [item[resource]['id'] for item in items]
        expected_res.reverse()
        self.assertEqual(expected_res, [n['id'] for n in item_res])


class ExtensionTestCase(ext_base.ExtensionTestCase):
    pass


class QuotaExtensionTestCase(test_quotasv2.QuotaExtensionTestCase):
    pass
