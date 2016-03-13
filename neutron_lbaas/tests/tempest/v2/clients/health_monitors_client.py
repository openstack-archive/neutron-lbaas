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


class HealthMonitorsClientJSON(rest_client.RestClient):
    """
    Tests Health Monitors API
    """

    def list_health_monitors(self, params=None):
        """List all health monitors."""
        url = 'v2.0/lbaas/healthmonitors'
        if params:
            url = "{0}?{1}".format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBodyList(resp, body['healthmonitors'])

    def get_health_monitor(self, health_monitor_id, params=None):
        """Get health monitor details."""
        url = 'v2.0/lbaas/healthmonitors/{0}'.format(health_monitor_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body["healthmonitor"])

    def create_health_monitor(self, **kwargs):
        """Create a health monitor."""
        url = 'v2.0/lbaas/healthmonitors'
        post_body = jsonutils.dumps({"healthmonitor": kwargs})
        resp, body = self.post(url, post_body)
        body = jsonutils.loads(body)
        self.expected_success(201, resp.status)
        return rest_client.ResponseBody(resp, body["healthmonitor"])

    def update_health_monitor(self, health_monitor_id, **kwargs):
        """Update a health monitor."""
        url = 'v2.0/lbaas/healthmonitors/{0}'.format(health_monitor_id)
        put_body = jsonutils.dumps({"healthmonitor": kwargs})
        resp, body = self.put(url, put_body)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return rest_client.ResponseBody(resp, body["healthmonitor"])

    def delete_health_monitor(self, health_monitor_id):
        """Delete an existing health monitor."""
        url = 'v2.0/lbaas/healthmonitors/{0}'.format(health_monitor_id)
        resp, body = self.delete(url)
        self.expected_success(204, resp.status)
        return rest_client.ResponseBody(resp, body)
