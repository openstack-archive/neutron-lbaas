# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest import config
import testscenarios

from neutron_lbaas.tests.tempest.v2.ddt import base_ddt

CONF = config.CONF


"""
Tests the following operations in the Neutron-LBaaS API using the
REST client for Listeners:

    |-----|------------------|------------------|-------------------------|
    |S.No |Action            |LB admin_state_up | Listener admin_state_up |
    |-----|------------------|------------------|-------------------------|
    | 1   | Create Listener  | True             | True                    |
    | 2   |                  | True             | False                   |
    | 3   |                  | False            | True                    |
    | 4   |                  | False            | False                   |
    | 5   | Update Listener  | True             | True  --> True          |
    | 6   |                  | True             | True  --> False         |
    | 7   |                  | True             | False --> True          |
    | 8   |                  | True             | False --> False         |
    | 9   |                  | False            | True  --> True          |
    | 10  |                  | False            | True  --> False         |
    | 11  |                  | False            | False --> True          |
    | 12  |                  | False            | False --> False         |
    |-----|------------------|------------------|-------------------------|

"""
# set up the scenarios
scenario_lb_T = ('lb_T', {'lb_flag': True})
scenario_lb_F = ('lb_F', {'lb_flag': False})

scenario_listener_T = ('listener_T', {'listener_flag': True})
scenario_listener_F = ('listener_F', {'listener_flag': False})

scenario_lis_to_flag_T = ('listener_to_flag_T', {'listener_to_flag': True})
scenario_lis_to_flag_F = ('listener_to_flag_F', {'listener_to_flag': False})

# The following command creates 4 unique scenarios
scenario_create_member = testscenarios.multiply_scenarios(
        [scenario_lb_T, scenario_lb_F],
        [scenario_listener_T, scenario_listener_F])

# The following command creates 8 unique scenarios
scenario_update_member = testscenarios.multiply_scenarios(
    [scenario_lis_to_flag_T, scenario_lis_to_flag_F],
    scenario_create_member)


class CreateListenerAdminStateTests(base_ddt.AdminStateTests):

    scenarios = scenario_create_member

    @classmethod
    def resource_setup(cls):
        super(CreateListenerAdminStateTests, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(CreateListenerAdminStateTests, cls).resource_cleanup()

    @classmethod
    def setup_load_balancer(cls, **kwargs):
        super(CreateListenerAdminStateTests,
              cls).setup_load_balancer(**kwargs)

    def test_create_listener_with_lb_and_listener_admin_states_up(self):
        """Test create a listener.

        Create a listener with various combinations of
        values for admin_state_up field of the listener and
        the load-balancer.
        """

        self.resource_setup_load_balancer(self.lb_flag)
        self.resource_setup_listener(self.listener_flag)
        self.check_operating_status()
        self._delete_listener(self.listener_id)
        self._delete_load_balancer(self.load_balancer_id)


class UpdateListenerAdminStateTests(base_ddt.AdminStateTests):

    scenarios = scenario_update_member

    @classmethod
    def resource_setup(cls):
        super(UpdateListenerAdminStateTests, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(UpdateListenerAdminStateTests, cls).resource_cleanup()

    @classmethod
    def setup_load_balancer(cls, **kwargs):
        super(UpdateListenerAdminStateTests,
              cls).setup_load_balancer(**kwargs)

    def test_update_listener_with_listener_admin_state_up(self):
        """Test updating a listener.

        Update a listener with various combinations of
        admin_state_up field of the listener and the
        load-balancer.
        """

        self.resource_setup_load_balancer(self.lb_flag)
        self.resource_setup_listener(self.listener_flag)
        self.check_operating_status()
        self.listener = (self._update_listener(
            self.listener_id,
            name='new_name',
            admin_state_up=self.listener_to_flag))
        self.check_operating_status()
        self._delete_listener(self.listener_id)
        self._delete_load_balancer(self.load_balancer_id)
