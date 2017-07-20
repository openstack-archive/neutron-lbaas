# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

from tempest import config
from tempest.lib import decorators
import testscenarios

from neutron_lbaas.tests.tempest.v2.ddt import base_ddt

CONF = config.CONF

scenario_lb_T = ('lb_T', {'lb_flag': True})
scenario_lb_F = ('lb_F', {'lb_flag': False})

scenario_listener_T = ('listener_T', {'listener_flag': True})
scenario_listener_F = ('listener_F', {'listener_flag': False})

scenario_pool_T = ('pool_T', {'pool_flag': True})
scenario_pool_F = ('pool_F', {'pool_flag': False})

scenario_healthmonitor_T = ('healthmonitor_T', {'healthmonitor_flag': True})
scenario_healthmonitor_F = ('healthmonitor_F', {'healthmonitor_flag': False})

scenario_healthmonitor_to_flag_T = ('healthmonitor_to_flag_T', {
    'healthmonitor_to_flag': True})
scenario_healthmonitor_to_flag_F = ('healthmonitor_to_flag_F', {
    'healthmonitor_to_flag': False})

# The following command creates 16 unique scenarios
scenario_create_health_monitor = testscenarios.multiply_scenarios(
    [scenario_lb_T, scenario_lb_F],
    [scenario_listener_T, scenario_listener_F],
    [scenario_pool_T, scenario_pool_F],
    [scenario_healthmonitor_T, scenario_healthmonitor_F])

# The following command creates 32 unique scenarios
scenario_update_health_monitor = testscenarios.multiply_scenarios(
    [scenario_healthmonitor_to_flag_T, scenario_healthmonitor_to_flag_F],
    scenario_create_health_monitor)


class BaseHealthMonitorAdminStateTest(base_ddt.AdminStateTests):
    @classmethod
    def resource_setup(cls):
        super(BaseHealthMonitorAdminStateTest, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(BaseHealthMonitorAdminStateTest, cls).resource_cleanup()

    def setUp(self):
        """Set up resources.

        Including :load balancer, listener, and pool and
        health_monitor with scenarios.
        """
        super(BaseHealthMonitorAdminStateTest, self).setUp()
        self.resource_setup_load_balancer(self.lb_flag)
        self.addCleanup(self._delete_load_balancer, self.load_balancer_id)

        self.resource_setup_listener(self.listener_flag)
        self.addCleanup(self._delete_listener, self.listener_id)

        self.resource_setup_pool(self.pool_flag)
        self.addCleanup(self._delete_pool, self.pool_id)
        self.resource_set_health_monitor(self.healthmonitor_flag,
                self._create_health_monitor)
        self.addCleanup(self._delete_health_monitor, self.health_monitor_id)

    @classmethod
    def resource_setup_listener(cls, admin_state_up_flag):
        """Set up resources for listener."""
        (super(BaseHealthMonitorAdminStateTest, cls).
         resource_setup_listener(admin_state_up_flag))

    @classmethod
    def resource_setup_pool(cls, admin_state_up_flag):
        """Set up resources for pool."""
        (super(BaseHealthMonitorAdminStateTest, cls).
         resource_setup_pool(admin_state_up_flag))

    @classmethod
    def resource_setup_load_balancer(cls, admin_state_up_flag):
        """Set up resources for load balancer."""
        (super(BaseHealthMonitorAdminStateTest, cls).
         resource_setup_load_balancer(admin_state_up_flag))


class CreateHealthMonitorAdminStateTest(BaseHealthMonitorAdminStateTest):
    scenarios = scenario_create_health_monitor

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for health monitor with testscenarios, the goal is to test
    the various admin_state_up boolean combinations and their expected
    operating_status and provision_status results from the status tree.

        create healthmonitor
    """

    # @decorators.skip_because(bug="1449775")
    def test_create_health_monitor_with_scenarios(self):
        """Test creating healthmonitor with 16 scenarios.

        Compare the status tree before and after setting up admin_state_up flag
        for health monitor.
        """
        self.check_operating_status()


class UpdateHealthMonitorAdminStateTest(BaseHealthMonitorAdminStateTest):
    scenarios = scenario_update_health_monitor

    """
    Tests the following operations in the Neutron-LBaaS API using the
    REST client for health monitor with testscenarios, the goal is to test
    the various admin_state_up boolean combinations and their expected
    operating_status and provision_status results from the status tree.

        update healthmonitor
    """

    @decorators.skip_because(bug="1449775")
    def test_update_health_monitor_with_admin_state_up(self):
        """Test update a monitor.
        Compare the status tree before and after setting the admin_state_up
        flag for health_monitor.

        """
        self.create_health_monitor_kwargs = {
            'admin_state_up': self.healthmonitor_to_flag}
        self.health_monitor = self._update_health_monitor(
            self.health_monitor_id, **self.create_health_monitor_kwargs)
        self.check_operating_status()
