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


class TestHealthMonitorBasic(base.BaseTestCase):

    @utils.services('compute', 'network')
    def test_health_monitor_basic(self):
        """This test checks load balancing with health monitor.

        The following is the scenario outline:
        1. Create two instances.
        2. SSH to the instances and start two servers: primary and secondary.
        3. Create a load balancer, with two members and with
           ROUND_ROBIN algorithm, associate the VIP with a floating ip.
        4. Create a health monitor.
        5. Send NUM requests to the floating ip and check that they are shared
           between the two servers.
        6. Disable the primary server and validate the traffic is being sent
           only to the secondary server.
        """
        self._create_servers()
        self._start_servers()
        self._create_load_balancer()
        self._create_health_monitor()
        self._check_load_balancing()
        # stopping the primary server
        self._stop_server()
        # Asserting the traffic is sent only to the secondary server
        self._traffic_validation_after_stopping_server()
