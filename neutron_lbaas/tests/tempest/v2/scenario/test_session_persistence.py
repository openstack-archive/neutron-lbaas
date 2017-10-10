# Copyright 2015 Mirantis Inc.
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
from tempest import config

from neutron_lbaas.tests.tempest.v2.scenario import base


CONF = config.CONF


class TestSessionPersistence(base.BaseTestCase):

    @utils.services('compute', 'network')
    def test_session_persistence(self):
        """This test checks checks load balancing with session persistence.

        The following is the scenario outline:
        1. Boot two instances.
        2. SSH to the instance and start two servers.
        3. Create a pool with SOURCE_IP session persistence type.
        4. Create a load balancer with two members and with ROUND_ROBIN
           algorithm.
        5. Send 10 requests to the floating ip, associated with the VIP,
           and make sure all the requests from the same ip
           are processed by the same member of the pool.
        6. Change session persistence type of the pool to HTTP_COOKIE.
        7. Check that this session persistence type also forces all
           the requests containing the same cookie to hit the same
           member of the pool.
        8. Change session persistence type of the pool to APP_COOKIE.
        9. Perform the same check.
        10. Turn session persistence off and check that the requests
            are again distributed according to the ROUND_ROBIN algorithm.
        """
        self._create_server('server1')
        self._start_servers()
        session_persistence_types = CONF.lbaas.session_persistence_types
        if "SOURCE_IP" in session_persistence_types:
            self._create_load_balancer(persistence_type="SOURCE_IP")
            self._check_source_ip_persistence()
        if "HTTP_COOKIE" in session_persistence_types:
            self._update_pool_session_persistence("HTTP_COOKIE")
            self._check_cookie_session_persistence()
        if "APP_COOKIE" in session_persistence_types:
            self._update_pool_session_persistence("APP_COOKIE",
                                                  cookie_name="JSESSIONID")
            self._check_cookie_session_persistence()
        self._update_pool_session_persistence()
        self._check_load_balancing()
