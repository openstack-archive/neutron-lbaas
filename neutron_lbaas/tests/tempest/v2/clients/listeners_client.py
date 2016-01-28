# Copyright 2015, 2016 Rackspace US Inc.  All rights reserved.
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


class ListenersClientJSON(rest_client.RestClient):
    """
    Tests Listeners API
    """

    def list_listeners(self, params=None):
        """List all listeners."""
        url = 'v2.0/lbaas/listeners'
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBodyList(resp, body['listeners'])

    def get_listener(self, listener_id, params=None):
        """Get listener details."""
        url = 'v2.0/lbaas/listeners/{0}'.format(listener_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body['listener'])

    def create_listener(self, **kwargs):
        """Create a listener build."""
        post_body = jsonutils.dumps({'listener': kwargs})
        resp, body = self.post('v2.0/lbaas/listeners', post_body)
        body = jsonutils.loads(body)
        self.expected_success(201, resp.status)
        return rest_client.ResponseBody(resp, body['listener'])

    def update_listener(self, listener_id, **kwargs):
        """Update an listener build."""
        put_body = jsonutils.dumps({'listener': kwargs})
        resp, body = self.put('v2.0/lbaas/listeners/{0}'
                              .format(listener_id), put_body)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body['listener'])

    def delete_listener(self, listener_id):
        """Delete an existing listener build."""
        resp, body = self.delete("v2.0/lbaas/listeners/{0}"
                                 .format(listener_id))
        self.expected_success(204, resp.status)
        return rest_client.ResponseBody(resp, body)
