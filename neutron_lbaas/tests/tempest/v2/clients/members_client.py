# Copyright 2014, 2016 Rackspace US Inc.  All rights reserved.
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

from oslo_serialization import jsonutils
from six.moves.urllib import parse
from tempest.lib.common import rest_client


class MembersClientJSON(rest_client.RestClient):
    """
    Tests Members API
    """

    def list_members(self, pool_id, params=None):
        """
        List all Members
        """
        url = 'v2.0/lbaas/pools/{0}/members'.format(pool_id)
        if params:
            url = "{0}?{1}".format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBodyList(resp, body['members'])

    def get_member(self, pool_id, member_id, params=None):
        url = 'v2.0/lbaas/pools/{0}/members/{1}'.format(pool_id, member_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body["member"])

    def create_member(self, pool_id, **kwargs):
        url = 'v2.0/lbaas/pools/{0}/members'.format(pool_id)
        post_body = jsonutils.dumps({"member": kwargs})
        resp, body = self.post(url, post_body)
        body = jsonutils.loads(body)
        self.expected_success(201, resp.status)
        return rest_client.ResponseBody(resp, body["member"])

    def update_member(self, pool_id, member_id, **kwargs):
        url = 'v2.0/lbaas/pools/{0}/members/{1}'.format(pool_id, member_id)
        put_body = jsonutils.dumps({"member": kwargs})
        resp, body = self.put(url, put_body)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body["member"])

    def delete_member(self, pool_id, member_id, **kwargs):
        url = 'v2.0/lbaas/pools/{0}/members/{1}'.format(pool_id, member_id)
        resp, body = self.delete(url)
        self.expected_success(204, resp.status)
