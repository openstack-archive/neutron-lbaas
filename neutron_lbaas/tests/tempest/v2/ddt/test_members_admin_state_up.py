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
REST client with various combinations of values for the
admin_state_up field of lb, listener, pool and member.

    create member
    update member

"""
# set up the scenarios
scenario_lb_T = ('lb_T', {'lb_flag': True})
scenario_lb_F = ('lb_F', {'lb_flag': False})

scenario_listener_T = ('listener_T', {'listener_flag': True})
scenario_listener_F = ('listener_F', {'listener_flag': False})

scenario_pool_T = ('pool_T', {'pool_flag': True})
scenario_pool_F = ('pool_F', {'pool_flag': False})

scenario_member_T = ('member_T', {'member_flag': True})
scenario_member_F = ('member_F', {'member_flag': False})


scenario_mem_to_flag_T = ('member_to_flag_T', {'member_to_flag': True})
scenario_mem_to_flag_F = ('member_to_flag_F', {'member_to_flag': False})

# The following command creates 16 unique scenarios
scenario_create_member = testscenarios.multiply_scenarios(
        [scenario_lb_T, scenario_lb_F],
        [scenario_listener_T, scenario_listener_F],
        [scenario_pool_T, scenario_pool_F],
        [scenario_member_T, scenario_member_F])

# The following command creates 32 unique scenarios
scenario_update_member = testscenarios.multiply_scenarios(
    [scenario_mem_to_flag_T, scenario_mem_to_flag_F],
    scenario_create_member)


class CreateMemberAdminStateTests(base_ddt.AdminStateTests):

    scenarios = scenario_create_member

    @classmethod
    def resource_setup(cls):
        super(CreateMemberAdminStateTests, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(CreateMemberAdminStateTests, cls).resource_cleanup()

    def setUp(self):
        """Set up load balancer, listener,  pool and member."""
        super(CreateMemberAdminStateTests, self).setUp()
        self.resource_setup_load_balancer(self.lb_flag)
        self.addCleanup(self._delete_load_balancer, self.load_balancer_id)

        self.resource_setup_listener(self.listener_flag)
        self.addCleanup(self._delete_listener, self.listener_id)

        self.resource_setup_pool(self.pool_flag)
        self.addCleanup(self._delete_pool, self.pool_id)

        self.resource_setup_member(self.member_flag)
        self.addCleanup(self._delete_member, self.pool_id, self.member_id)

    @classmethod
    def resource_setup_load_balancer(cls, admin_state_up_flag):
        (super(CreateMemberAdminStateTests, cls).
         resource_setup_load_balancer(admin_state_up_flag))

    @classmethod
    def resource_setup_listener(cls, admin_state_up_flag):
        (super(CreateMemberAdminStateTests, cls).
         resource_setup_listener(admin_state_up_flag))

    @classmethod
    def resource_setup_pool(cls, admin_state_up_flag):
        (super(CreateMemberAdminStateTests, cls).
         resource_setup_pool(admin_state_up_flag))

    @classmethod
    def resource_setup_member(cls, admin_state_up_flag):
        (super(CreateMemberAdminStateTests, cls).
         resource_setup_member(admin_state_up_flag))

    def test_create_member_with_admin_state_up(self):
        """Test create a member. """
        self.check_operating_status()


class UpdateMemberAdminStateTests(base_ddt.AdminStateTests):

    scenarios = scenario_update_member

    @classmethod
    def resource_setup(cls):
        super(UpdateMemberAdminStateTests, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        super(UpdateMemberAdminStateTests, cls).resource_cleanup()

    def setUp(self):
        """Set up load balancer, listener,  pool and member resources."""
        super(UpdateMemberAdminStateTests, self).setUp()
        self.resource_setup_load_balancer(self.lb_flag)
        self.addCleanup(self._delete_load_balancer, self.load_balancer_id)

        self.resource_setup_listener(self.listener_flag)
        self.addCleanup(self._delete_listener, self.listener_id)

        self.resource_setup_pool(self.pool_flag)
        self.addCleanup(self._delete_pool, self.pool_id)

        self.resource_setup_member(self.member_flag)
        self.addCleanup(self._delete_member, self.pool_id, self.member_id)

    @classmethod
    def resource_setup_load_balancer(cls, admin_state_up_flag):
        (super(UpdateMemberAdminStateTests, cls).
            resource_setup_load_balancer(admin_state_up_flag))

    @classmethod
    def resource_setup_listener(cls, admin_state_up_flag):
        (super(UpdateMemberAdminStateTests, cls).
         resource_setup_listener(admin_state_up_flag))

    @classmethod
    def resource_setup_pool(cls, admin_state_up_flag):
        (super(UpdateMemberAdminStateTests, cls).
         resource_setup_pool(admin_state_up_flag))

    @classmethod
    def resource_setup_member(cls, admin_state_up_flag):
        (super(UpdateMemberAdminStateTests, cls).
         resource_setup_member(admin_state_up_flag))

    def test_update_member_with_admin_state_up(self):
        """Test update a member. """
        self.create_member_kwargs = {'admin_state_up': self.member_to_flag}
        self.member = self._update_member(self.pool_id,
                                          self.member_id,
                                          **self.create_member_kwargs)
        self.check_operating_status()
