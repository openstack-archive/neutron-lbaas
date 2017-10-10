# Copyright 2016 Rackspace Inc.
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


class TestSharedPools(base.BaseTestCase):

    @utils.services('compute', 'network')
    def test_shared_pools(self):
        """This test checks load balancing with shared pools.

        The following is the scenario outline:
        1. Boot 1 instance.
        2. SSH to instance and start two servers listening on different ports.
        3. Create a pool.
        4. Create 2 listeners.
        5. Create a load balancer with two members associated to the two
           servers on the instance, and with ROUND_ROBIN algorithm.
        6. Send NUM requests to one listener's floating ip and check that
           they are shared between the two members.
        7. Send NUM requests to the other listener's floating ip and check that
           they are shared between the two members.
        """
        second_listener_port = 8080

        self._create_server('server1')
        self._start_servers()
        # automatically creates first listener on port 80
        self._create_load_balancer()
        # create second listener
        self._create_listener(load_balancer_id=self.load_balancer['id'],
                              port=second_listener_port,
                              default_pool_id=self.pool['id'])
        self._create_security_group_rules_for_port(second_listener_port)
        self._wait_for_load_balancer_status(self.load_balancer['id'])
        # check via first listener's default port 80
        self._check_load_balancing()
        # check via second listener's port
        self._check_load_balancing(port=second_listener_port)
