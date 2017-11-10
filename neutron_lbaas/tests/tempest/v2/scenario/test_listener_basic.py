# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

from tempest.common import utils

from neutron_lbaas.tests.tempest.v2.scenario import base


class TestListenerBasic(base.BaseTestCase):
    """
    This test checks load balancing and validates traffic
    The following is the scenario outline:
    1. Create an instance
    2. SSH to the instance and start two servers: primary, secondary
    3. Create a load balancer, listener and pool with two members using
    ROUND_ROBIN algorithm, associate the VIP with a floating ip
    4. Send NUM requests to the floating ip and check that they are shared
       between the two servers.
    5. Delete listener and validate the traffic is not sent to any members
    """

    def _delete_listener(self):
        """Delete a listener to test listener scenario."""
        self._cleanup_pool(self.pool['id'])
        self._cleanup_listener(self.listener['id'])

    @utils.services('compute', 'network')
    def test_listener_basic(self):
        self._create_server('server1')
        self._start_servers()
        self._create_load_balancer()
        self._check_load_balancing()
        self._delete_listener()
        self._check_load_balancing_after_deleting_resources()
