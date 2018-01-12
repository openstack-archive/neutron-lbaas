# Copyright (c) 2013 OpenStack Foundation.
# Copyright 2015 Rackspace
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
from datetime import datetime

import mock
from neutron_lib import context
from neutron_lib.plugins import directory

from neutron.api import extensions
from neutron.db import agents_db
from neutron.tests.common import helpers
from neutron.tests.unit.api import test_extensions
from neutron.tests.unit.db import test_agentschedulers_db
import neutron.tests.unit.extensions
from neutron.tests.unit.extensions import test_agent
from neutron_lib import constants as n_constants
from neutron_lib.plugins import constants as plugin_const
from webob import exc

from neutron_lbaas.drivers.haproxy import plugin_driver
from neutron_lbaas.extensions import lbaas_agentschedulerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.tests import base
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2
from neutron_lbaas.tests.unit.db.loadbalancer import util

LBAAS_HOSTA = 'hosta'
extensions_path = ':'.join(neutron.tests.unit.extensions.__path__)


class AgentSchedulerTestMixIn(test_agentschedulers_db.AgentSchedulerTestMixIn):
    def _list_loadbalancers_hosted_by_agent(
            self, agent_id, expected_code=exc.HTTPOk.code, admin_context=True):
        path = "/agents/%s/%s.%s" % (agent_id,
                                     lbaas_agentschedulerv2.LOADBALANCERS,
                                     self.fmt)
        return self._request_list(path, expected_code=expected_code,
                                  admin_context=admin_context)

    def _get_lbaas_agent_hosting_loadbalancer(self, loadbalancer_id,
                                              expected_code=exc.HTTPOk.code,
                                              admin_context=True):
        path = "/lbaas/loadbalancers/%s/%s.%s" % (loadbalancer_id,
                                                  lbaas_agentschedulerv2
                                                  .LOADBALANCER_AGENT,
                                                  self.fmt)
        return self._request_list(path, expected_code=expected_code,
                                  admin_context=admin_context)


class LBaaSAgentSchedulerTestCase(test_agent.AgentDBTestMixIn,
                                  AgentSchedulerTestMixIn,
                                  util.LbaasTestMixin,
                                  base.NeutronDbPluginV2TestCase):
    fmt = 'json'
    plugin_str = 'neutron.plugins.ml2.plugin.Ml2Plugin'

    def _register_agent_states(self, lbaas_agents=False):
        res = super(LBaaSAgentSchedulerTestCase, self)._register_agent_states(
            lbaas_agents=lbaas_agents)
        if lbaas_agents:
            lbaas_hosta = {
                'binary': 'neutron-loadbalancer-agent',
                'host': test_agent.LBAAS_HOSTA,
                'topic': 'LOADBALANCER_AGENT',
                'configurations': {'device_drivers': [
                    plugin_driver.HaproxyOnHostPluginDriver.device_driver]},
                'agent_type': lb_const.AGENT_TYPE_LOADBALANCERV2}
            lbaas_hostb = copy.deepcopy(lbaas_hosta)
            lbaas_hostb['host'] = test_agent.LBAAS_HOSTB
            callback = agents_db.AgentExtRpcCallback()
            callback.report_state(self.adminContext,
                                  agent_state={'agent_state': lbaas_hosta},
                                  time=datetime.utcnow().isoformat())
            callback.report_state(self.adminContext,
                                  agent_state={'agent_state': lbaas_hostb},
                                  time=datetime.utcnow().isoformat())
            res += [lbaas_hosta, lbaas_hostb]
        return res

    def setUp(self):
        service_plugins = {
            'lb_plugin_name': test_db_loadbalancerv2.DB_LB_PLUGIN_CLASS}

        # default provider should support agent scheduling
        self.set_override(
            [('LOADBALANCERV2:lbaas:neutron_lbaas.drivers.haproxy.'
              'plugin_driver.HaproxyOnHostPluginDriver:default')])

        super(LBaaSAgentSchedulerTestCase, self).setUp(
            self.plugin_str, service_plugins=service_plugins)
        ext_mgr = extensions.PluginAwareExtensionManager.get_instance()
        self.ext_api = test_extensions.setup_extensions_middleware(ext_mgr)
        self.adminContext = context.get_admin_context()
        self.lbaas_plugin = directory.get_plugin(plugin_const.LOADBALANCERV2)
        self.core_plugin = directory.get_plugin()

    def test_report_states(self):
        self._register_agent_states(lbaas_agents=True)
        agents = self._list_agents()
        self.assertEqual(8, len(agents['agents']))

    def test_loadbalancer_scheduling_on_loadbalancer_creation(self):
        self._register_agent_states(lbaas_agents=True)
        with self.loadbalancer() as loadbalancer:
            lbaas_agent = self._get_lbaas_agent_hosting_loadbalancer(
                loadbalancer['loadbalancer']['id'])
            self.assertIsNotNone(lbaas_agent)
            self.assertEqual(lb_const.AGENT_TYPE_LOADBALANCERV2,
                             lbaas_agent['agent']['agent_type'])
            loadbalancers = self._list_loadbalancers_hosted_by_agent(
                lbaas_agent['agent']['id'])
            self.assertEqual(1, len(loadbalancers['loadbalancers']))
            self.assertEqual(loadbalancer['loadbalancer'],
                             loadbalancers['loadbalancers'][0])
            self.lbaas_plugin.db.update_loadbalancer_provisioning_status(
                self.adminContext, loadbalancer['loadbalancer']['id']
            )

    def test_schedule_loadbalancer_with_disabled_agent(self):
        lbaas_hosta = {
            'binary': 'neutron-loadbalancer-agent',
            'host': LBAAS_HOSTA,
            'topic': 'LOADBALANCER_AGENT',
            'configurations': {'device_drivers': [
                plugin_driver.HaproxyOnHostPluginDriver.device_driver
            ]},
            'agent_type': lb_const.AGENT_TYPE_LOADBALANCERV2}
        helpers._register_agent(lbaas_hosta)
        with self.loadbalancer() as loadbalancer:
            lbaas_agent = self._get_lbaas_agent_hosting_loadbalancer(
                loadbalancer['loadbalancer']['id'])
            self.assertIsNotNone(lbaas_agent)
            self.lbaas_plugin.db.update_loadbalancer_provisioning_status(
                self.adminContext, loadbalancer['loadbalancer']['id']
            )
        agents = self._list_agents()
        self._disable_agent(agents['agents'][0]['id'])
        subnet = self.core_plugin.get_subnets(self.adminContext)[0]
        lb = {
            'loadbalancer': {
                'vip_subnet_id': subnet['id'],
                'provider': 'lbaas',
                'flavor_id': n_constants.ATTR_NOT_SPECIFIED,
                'vip_address': n_constants.ATTR_NOT_SPECIFIED,
                'admin_state_up': True,
                'tenant_id': self._tenant_id,
                'listeners': []}}
        self.assertRaises(lbaas_agentschedulerv2.NoEligibleLbaasAgent,
                          self.lbaas_plugin.create_loadbalancer,
                          self.adminContext, lb)

    def test_schedule_loadbalancer_with_down_agent(self):
        lbaas_hosta = {
            'binary': 'neutron-loadbalancer-agent',
            'host': LBAAS_HOSTA,
            'topic': 'LOADBALANCER_AGENT',
            'configurations': {'device_drivers': [
                plugin_driver.HaproxyOnHostPluginDriver.device_driver
            ]},
            'agent_type': lb_const.AGENT_TYPE_LOADBALANCERV2}
        helpers._register_agent(lbaas_hosta)
        is_agent_down_str = 'neutron.agent.common.utils.is_agent_down'
        with mock.patch(is_agent_down_str) as mock_is_agent_down:
            mock_is_agent_down.return_value = False
            with self.loadbalancer() as loadbalancer:
                lbaas_agent = self._get_lbaas_agent_hosting_loadbalancer(
                    loadbalancer['loadbalancer']['id'])
                self.lbaas_plugin.db.update_loadbalancer_provisioning_status(
                    self.adminContext, loadbalancer['loadbalancer']['id']
                )
            self.assertIsNotNone(lbaas_agent)
        with mock.patch(is_agent_down_str) as mock_is_agent_down:
            mock_is_agent_down.return_value = True
            subnet = self.core_plugin.get_subnets(self.adminContext)[0]
            lb = {
                'loadbalancer': {
                    'vip_subnet_id': subnet['id'],
                    'provider': 'lbaas',
                    'flavor_id': n_constants.ATTR_NOT_SPECIFIED,
                    'vip_address': n_constants.ATTR_NOT_SPECIFIED,
                    'admin_state_up': True,
                    'tenant_id': self._tenant_id,
                    'listeners': []}}
            self.assertRaises(lbaas_agentschedulerv2.NoEligibleLbaasAgent,
                              self.lbaas_plugin.create_loadbalancer,
                              self.adminContext, lb)

    def test_loadbalancer_unscheduling_on_loadbalancer_deletion(self):
        self._register_agent_states(lbaas_agents=True)
        with self.loadbalancer(no_delete=True) as loadbalancer:
            lb_id = loadbalancer['loadbalancer']['id']
            lbaas_agent = self._get_lbaas_agent_hosting_loadbalancer(lb_id)
            self.assertIsNotNone(lbaas_agent)
            self.assertEqual(lb_const.AGENT_TYPE_LOADBALANCERV2,
                             lbaas_agent['agent']['agent_type'])
            loadbalancers = self._list_loadbalancers_hosted_by_agent(
                lbaas_agent['agent']['id'])
            self.assertEqual(1, len(loadbalancers['loadbalancers']))
            self.assertEqual(loadbalancer['loadbalancer'],
                             loadbalancers['loadbalancers'][0])

            self.lbaas_plugin.db.update_loadbalancer_provisioning_status(
                self.adminContext, lb_id
            )

            req = self.new_delete_request('loadbalancers', lb_id)
            res = req.get_response(self.ext_api)
            self.assertEqual(exc.HTTPNoContent.code, res.status_int)
            loadbalancers = self._list_loadbalancers_hosted_by_agent(
                lbaas_agent['agent']['id'])
            self.assertEqual(0, len(loadbalancers['loadbalancers']))

    def test_loadbalancer_scheduling_non_admin_access(self):
        self._register_agent_states(lbaas_agents=True)
        with self.loadbalancer() as loadbalancer:
            self._get_lbaas_agent_hosting_loadbalancer(
                loadbalancer['loadbalancer']['id'],
                expected_code=exc.HTTPForbidden.code,
                admin_context=False)
            self._list_loadbalancers_hosted_by_agent(
                'fake_id',
                expected_code=exc.HTTPForbidden.code,
                admin_context=False)
            self.lbaas_plugin.db.update_loadbalancer_provisioning_status(
                self.adminContext, loadbalancer['loadbalancer']['id']
            )
