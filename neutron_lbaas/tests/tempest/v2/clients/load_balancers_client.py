# Copyright 2014 Rackspace US Inc.  All rights reserved.
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

from six.moves.urllib import parse

from oslo_serialization import jsonutils

from neutron_lbaas.tests.tempest.lib.common import service_client


class LoadBalancersClientJSON(service_client.ServiceClient):
    """
    Tests Load Balancers API
    """

    def list_load_balancers(self, params=None):
        """List all load balancers."""
        url = 'v2.0/lbaas/loadbalancers'
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return service_client.ResponseBodyList(resp, body['loadbalancers'])

    def get_load_balancer(self, load_balancer_id, params=None):
        """Get load balancer details."""
        url = 'v2.0/lbaas/loadbalancers/{0}'.format(load_balancer_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return service_client.ResponseBody(resp, body['loadbalancer'])

    def create_load_balancer(self, **kwargs):
        """Create a load balancer build."""
        post_body = jsonutils.dumps({'loadbalancer': kwargs})
        resp, body = self.post('v2.0/lbaas/loadbalancers', post_body)
        body = jsonutils.loads(body)
        self.expected_success(201, resp.status)
        return service_client.ResponseBody(resp, body['loadbalancer'])

    def update_load_balancer(self, load_balancer_id, **kwargs):
        """Update a load balancer build."""
        put_body = jsonutils.dumps({'loadbalancer': kwargs})
        resp, body = self.put('v2.0/lbaas/loadbalancers/{0}'
                              .format(load_balancer_id), put_body)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return service_client.ResponseBody(resp, body['loadbalancer'])

    def delete_load_balancer(self, load_balancer_id):
        """Delete an existing load balancer build."""
        resp, body = self.delete('v2.0/lbaas/loadbalancers/{0}'
                                 .format(load_balancer_id))
        self.expected_success(204, resp.status)
        return service_client.ResponseBody(resp, body)

    def get_load_balancer_status_tree(self, load_balancer_id, params=None):
        """Get a load balancer's status tree."""
        url = 'v2.0/lbaas/loadbalancers/{0}/statuses'.format(load_balancer_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return service_client.ResponseBody(resp, body['statuses'])

    def get_load_balancer_stats(self, load_balancer_id, params=None):
        """Get a load balancer's stats."""
        url = 'v2.0/lbaas/loadbalancers/{0}/stats'.format(load_balancer_id)
        if params:
            url = '{0}?{1}'.format(url, parse.urlencode(params))
        resp, body = self.get(url)
        body = jsonutils.loads(body)
        self.expected_success(200, resp.status)
        return service_client.ResponseBody(resp, body['stats'])
