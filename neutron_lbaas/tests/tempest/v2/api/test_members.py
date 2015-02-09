# Copyright 2015 Rackspace US Inc.
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
from neutron_lbaas.tests.tempest.v2.api import base

from tempest.common.utils import data_utils
from tempest import config
from tempest import exceptions as ex
from tempest.openstack.common import log as logging
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class MemberTestJSON(base.BaseTestCase):
    """
    Test the following operations in Neutron-LBaaS API using the
    REST client for members:

        list members of a pool
        create a member of a Pool
        update a pool member
        delete a member
    """

    @classmethod
    def resource_setup(cls):
        super(MemberTestJSON, cls).resource_setup()
        if not test.is_extension_enabled("lbaas", "network"):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network-')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.tenant_id = cls.subnet.get('tenant_id')
        cls.subnet_id = cls.subnet.get('id')
        cls.load_balancer = cls._create_active_load_balancer(
            tenant_id=cls.tenant_id,
            vip_subnet_id=cls.subnet.get('id'))
        cls.load_balancer_id = cls.load_balancer.get("id")
        cls._wait_for_load_balancer_status(cls.load_balancer_id)
        cls.listener = cls.listeners_client.create_listener(
            loadbalancer_id=cls.load_balancer.get('id'),
            protocol='HTTP', protocol_port=80)
        cls.listener_id = cls.listener.get('id')
        cls._wait_for_load_balancer_status(cls.load_balancer_id)
        cls.pool = cls.pools_client.create_pool(protocol='HTTP',
                                                tenant_id=cls.tenant_id,
                                                lb_algorithm='ROUND_ROBIN',
                                                listener_id=cls.listener_id)
        cls.pool_id = cls.pool.get('id')
        cls._wait_for_load_balancer_status(cls.load_balancer_id)

    @test.attr(type='smoke')
    def test_list_empty_members(self):
        """Test that pool members are empty."""
        members = self.members_client.list_members(self.pool_id)
        self.assertEmpty(members,
                         msg='Initial pool was supposed to be empty')

    @test.attr(type='smoke')
    def test_list_3_members(self):
        """Test that we can list members. """
        member_ips_exp = set([u"127.0.0.0", u"127.0.0.1", u"127.0.0.2"])
        for ip in member_ips_exp:
            member_opts = self.build_member_opts()
            member_opts["address"] = ip
            self.members_client.create_member(self.pool_id, **member_opts)
            self._wait_for_load_balancer_status(self.load_balancer_id)
        members = self.members_client.list_members(self.pool_id)
        self.assertEqual(3, len(members))
        for member in members:
            self.assertEqual(member["tenant_id"], self.tenant_id)
            self.assertEqual(member["protocol_port"], 80)
            self.assertEqual(member["subnet_id"], self.subnet_id)
        found_member_ips = set([m["address"] for m in members])
        self.assertEqual(found_member_ips, member_ips_exp)
        for member in members:
            self.members_client.delete_member(self.pool_id,
                                              member["id"])

    @test.attr(type='smoke')
    def test_add_member(self):
        """Test that we can add a single member."""
        expect_empty_members = self.members_client.list_members(self.pool_id)
        self.assertEmpty(expect_empty_members)
        member_opts = self.build_member_opts()
        member = self.members_client.create_member(self.pool_id, **member_opts)
        member_id = member.get("id")
        self._wait_for_load_balancer_status(self.load_balancer_id)
        self.assertEqual(member_opts["address"], member["address"])
        self.assertEqual(self.tenant_id, member["tenant_id"])
        self.assertEqual(80, member["protocol_port"])
        self.assertEqual(self.subnet_id, member["subnet_id"])
        # Should have default values for admin_state_up and weight
        self.assertEqual(True, member["admin_state_up"])
        self.assertEqual(1, member["weight"])
        self.members_client.delete_member(self.pool_id, member_id)
        self.assertEmpty(self.members_client.list_members(self.pool_id))

    @test.attr(type='smoke')
    def test_get_member(self):
        """Test that we can fetch a member by id."""
        member_opts = self.build_member_opts()
        member_id = self.members_client.create_member(self.pool_id,
                                                      **member_opts)["id"]
        self._wait_for_load_balancer_status(self.load_balancer_id)
        member = self.members_client.get_member(self.pool_id, member_id)
        self.assertEqual(member_id, member["id"])
        self.assertEqual(member_opts["address"], member["address"])
        self.assertEqual(member_opts["tenant_id"], member["tenant_id"])
        self.assertEqual(member_opts["protocol_port"], member["protocol_port"])
        self.assertEqual(member_opts["subnet_id"], member["subnet_id"])
        self.members_client.delete_member(self.pool_id, member_id)
        self.assertEmpty(self.members_client.list_members(self.pool_id))

    @test.attr(type='smoke')
    def test_raises_BadRequest_when_missing_attrs_during_member_create(self):
        """Test failure on missing attributes on member create."""
        member_opts = {}
        self.assertRaises(ex.BadRequest, self.members_client.create_member,
                          self.pool_id, **member_opts)

    @test.attr(type='smoke')
    def test_delete_member(self):
        """Test that we can delete a member by id."""
        member_opts = self.build_member_opts()
        member_id = self.members_client.create_member(self.pool_id,
                                                      **member_opts)["id"]
        self._wait_for_load_balancer_status(self.load_balancer_id)
        members = self.members_client.list_members(self.pool_id)
        self.assertEqual(1, len(members))
        self.members_client.delete_member(self.pool_id, member_id)
        members = self.members_client.list_members(self.pool_id)
        self.assertEmpty(members)

    @test.attr(ttype='smoke')
    def test_update_member(self):
        """Test that we can update a member."""
        member_opts = self.build_member_opts()
        member = self.members_client.create_member(self.pool_id,
                                                   **member_opts)
        self._wait_for_load_balancer_status(self.load_balancer_id)
        member_id = member["id"]
        # Make sure the defaults are correct
        self.assertEqual(True, member["admin_state_up"])
        self.assertEqual(1, member["weight"])
        # Lets overwrite the defaults
        member_opts = {"weight": 10, "admin_state_up": False}
        member = self.members_client.update_member(self.pool_id, member_id,
                                                   **member_opts)
        self._wait_for_load_balancer_status(self.load_balancer_id)
        # And make sure they stick
        self.assertEqual(False, member["admin_state_up"])
        self.assertEqual(10, member["weight"])

    def test_raises_immutable_when_updating_immutable_attrs_on_member(self):
        """Test failure on immutable attribute on member create."""
        member_opts = self.build_member_opts()
        member_id = self.members_client.create_member(self.pool_id,
                                                      **member_opts)["id"]
        self._wait_for_load_balancer_status(self.load_balancer_id)
        member_opts = {"address": "127.0.0.69"}
        # The following code actually raises a 400 instead of a 422 as expected
        # Will need to consult with blogan as to what to fix
        self.assertRaises(ex.BadRequest, self.members_client.update_member,
                          self.pool_id, member_id, **member_opts)
        self.members_client.delete_member(self.pool_id, member_id)

    def test_raises_exception_on_invalid_attr_on_create(self):
        """Test failure on invalid attribute on member create."""
        member_opts = self.build_member_opts()
        member_opts["invalid_op"] = "should_break_request"
        self.assertRaises(ex.BadRequest, self.members_client.create_member,
                          self.pool_id, **member_opts)

    def test_raises_exception_on_invalid_attr_on_update(self):
        """Test failure on invalid attribute on member update."""
        member_opts = self.build_member_opts()
        member = self.members_client.create_member(self.pool_id, **member_opts)
        member_id = member["id"]
        self._wait_for_load_balancer_status(self.load_balancer_id)
        member_opts["invalid_op"] = "watch_this_break"
        self.assertRaises(ex.BadRequest, self.members_client.update_member,
                          self.pool_id, member_id, **member_opts)
        self.members_client.delete_member(self.pool_id, member_id)

    @classmethod
    def build_member_opts(cls, **kw):
        """Build out default member dictionary """
        opts = {"address": kw.get("address", "127.0.0.1"),
                "tenant_id": kw.get("tenant_id", cls.tenant_id),
                "protocol_port": kw.get("protocol_port", 80),
                "subnet_id": kw.get("subnet_id", cls.subnet_id)}
        return opts
