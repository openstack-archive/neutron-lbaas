# Copyright 2013 New Dream Network, LLC (DreamHost)
# Copyright 2015 Rackspace
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

import mock

from neutron.tests.unit import testlib_api
from neutron_lib.api.definitions import portbindings
from neutron_lib import constants
from neutron_lib import context
from neutron_lib.plugins import constants as n_constants
from oslo_utils import uuidutils
from six import moves

from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2 as ldb
from neutron_lbaas.db.loadbalancer import models as db_models
from neutron_lbaas.drivers.common import agent_callbacks
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.drivers.common import test_agent_driver_base


class TestLoadBalancerCallbacks(
        test_agent_driver_base.TestLoadBalancerPluginBase):

    def setUp(self):
        super(TestLoadBalancerCallbacks, self).setUp()

        self.callbacks = agent_callbacks.LoadBalancerCallbacks(
            self.plugin_instance
        )
        get_lbaas_agents_patcher = mock.patch(
            'neutron_lbaas.agent_scheduler.LbaasAgentSchedulerDbMixin.'
            'get_lbaas_agents')
        get_lbaas_agents_patcher.start()

    def test_get_ready_devices(self):
        with self.loadbalancer() as loadbalancer:
            lb_id = loadbalancer['loadbalancer']['id']
            self.plugin_instance.db.update_loadbalancer_provisioning_status(
                context.get_admin_context(),
                loadbalancer['loadbalancer']['id'])
            with mock.patch(
                    'neutron_lbaas.agent_scheduler.LbaasAgentSchedulerDbMixin.'
                    'list_loadbalancers_on_lbaas_agent') as mock_agent_lbs:
                mock_agent_lbs.return_value = [
                    data_models.LoadBalancer(id=lb_id)]
                ready = self.callbacks.get_ready_devices(
                    context.get_admin_context(),
                )
                self.assertEqual([lb_id], ready)

    def test_get_ready_devices_multiple_listeners_and_loadbalancers(self):
        ctx = context.get_admin_context()

        # add 3 load balancers and 2 listeners directly to DB
        # to create 2 "ready" devices and one load balancer without listener
        loadbalancers = []
        for i in moves.range(3):
            loadbalancers.append(ldb.models.LoadBalancer(
                id=uuidutils.generate_uuid(), vip_subnet_id=self._subnet_id,
                provisioning_status=constants.ACTIVE, admin_state_up=True,
                operating_status=constants.ACTIVE))
            ctx.session.add(loadbalancers[i])

        listener0 = ldb.models.Listener(
            id=uuidutils.generate_uuid(), protocol="HTTP",
            loadbalancer_id=loadbalancers[0].id,
            provisioning_status=constants.ACTIVE, admin_state_up=True,
            connection_limit=3, protocol_port=80,
            operating_status=constants.ACTIVE)
        ctx.session.add(listener0)
        loadbalancers[0].listener_id = listener0.id

        listener1 = ldb.models.Listener(
            id=uuidutils.generate_uuid(), protocol="HTTP",
            loadbalancer_id=loadbalancers[1].id,
            provisioning_status=constants.ACTIVE, admin_state_up=True,
            connection_limit=3, protocol_port=80,
            operating_status=constants.ACTIVE)
        ctx.session.add(listener1)
        loadbalancers[1].listener_id = listener1.id

        ctx.session.flush()

        self.assertEqual(3, ctx.session.query(ldb.models.LoadBalancer).count())
        self.assertEqual(2, ctx.session.query(ldb.models.Listener).count())
        with mock.patch(
                'neutron_lbaas.agent_scheduler.LbaasAgentSchedulerDbMixin'
                '.list_loadbalancers_on_lbaas_agent') as mock_agent_lbs:
            mock_agent_lbs.return_value = loadbalancers
            ready = self.callbacks.get_ready_devices(ctx)
            self.assertEqual(3, len(ready))
            self.assertIn(loadbalancers[0].id, ready)
            self.assertIn(loadbalancers[1].id, ready)
            self.assertIn(loadbalancers[2].id, ready)
        # cleanup
        ctx.session.query(ldb.models.Listener).delete()
        ctx.session.query(ldb.models.LoadBalancer).delete()

    def test_get_ready_devices_inactive_loadbalancer(self):
        with self.loadbalancer() as loadbalancer:
            lb_id = loadbalancer['loadbalancer']['id']
            self.plugin_instance.db.update_loadbalancer_provisioning_status(
                context.get_admin_context(),
                loadbalancer['loadbalancer']['id'])
            # set the loadbalancer inactive need to use plugin directly since
            # status is not tenant mutable
            self.plugin_instance.db.update_loadbalancer(
                context.get_admin_context(),
                loadbalancer['loadbalancer']['id'],
                {'loadbalancer': {'provisioning_status': constants.INACTIVE}}
            )
            with mock.patch(
                    'neutron_lbaas.agent_scheduler.LbaasAgentSchedulerDbMixin.'
                    'list_loadbalancers_on_lbaas_agent') as mock_agent_lbs:
                mock_agent_lbs.return_value = [
                    data_models.LoadBalancer(id=lb_id)]
                ready = self.callbacks.get_ready_devices(
                    context.get_admin_context(),
                )
                self.assertEqual([loadbalancer['loadbalancer']['id']],
                                 ready)

    def test_get_loadbalancer_active(self):
        with self.loadbalancer() as loadbalancer:
            ctx = context.get_admin_context()
            # activate objects
            self.plugin_instance.db.update_status(
                ctx, db_models.LoadBalancer,
                loadbalancer['loadbalancer']['id'], 'ACTIVE')

            lb = self.plugin_instance.db.get_loadbalancer(
                ctx, loadbalancer['loadbalancer']['id']
            )

            load_balancer = self.callbacks.get_loadbalancer(
                ctx, loadbalancer['loadbalancer']['id']
            )
            expected_lb = lb.to_dict()
            expected_lb['provider']['device_driver'] = 'dummy'
            subnet = self.plugin_instance.db._core_plugin.get_subnet(
                ctx, expected_lb['vip_subnet_id'])
            subnet = data_models.Subnet.from_dict(subnet).to_dict()
            expected_lb['vip_port']['fixed_ips'][0]['subnet'] = subnet
            network = self.plugin_instance.db._core_plugin.get_network(
                ctx, expected_lb['vip_port']['network_id']
            )
            expected_lb['vip_port']['network'] = {}
            for key in ('id', 'name', 'description', 'mtu'):
                expected_lb['vip_port']['network'][key] = network[key]
            del expected_lb['stats']
            self.assertEqual(expected_lb, load_balancer)

    def _update_port_test_helper(self, expected, func, **kwargs):
        core = self.plugin_instance.db._core_plugin

        with self.loadbalancer() as loadbalancer:
            lb_id = loadbalancer['loadbalancer']['id']
            if 'device_id' not in expected:
                expected['device_id'] = lb_id
            self.plugin_instance.db.update_loadbalancer_provisioning_status(
                context.get_admin_context(),
                loadbalancer['loadbalancer']['id'])
            ctx = context.get_admin_context()
            db_lb = self.plugin_instance.db.get_loadbalancer(ctx, lb_id)
            func(ctx, port_id=db_lb.vip_port_id, **kwargs)
            db_port = core.get_port(ctx, db_lb.vip_port_id)
            for k, v in expected.items():
                self.assertEqual(v, db_port[k])

    def test_plug_vip_port(self):
        exp = {
            'device_owner': 'neutron:' + n_constants.LOADBALANCERV2,
            'admin_state_up': True
        }
        self._update_port_test_helper(
            exp,
            self.callbacks.plug_vip_port,
            host='host'
        )

    def test_plug_vip_port_mock_with_host(self):
        exp = {
            'device_owner': 'neutron:' + n_constants.LOADBALANCERV2,
            'admin_state_up': True,
            portbindings.HOST_ID: 'host'
        }
        with mock.patch.object(
                self.plugin.db._core_plugin,
                'update_port') as mock_update_port:
            with self.loadbalancer() as loadbalancer:
                lb_id = loadbalancer['loadbalancer']['id']
                ctx = context.get_admin_context()
                self.callbacks.update_status(ctx, 'loadbalancer', lb_id,
                    constants.ACTIVE)
                (self.plugin_instance.db
                 .update_loadbalancer_provisioning_status(ctx, lb_id))
                db_lb = self.plugin_instance.db.get_loadbalancer(ctx, lb_id)
                self.callbacks.plug_vip_port(ctx, port_id=db_lb.vip_port_id,
                                             host='host')
            mock_update_port.assert_called_once_with(
                ctx, db_lb.vip_port_id,
                {'port': testlib_api.SubDictMatch(exp)})

    def test_unplug_vip_port(self):
        exp = {
            'device_owner': '',
            'device_id': '',
            'admin_state_up': False
        }
        self._update_port_test_helper(
            exp,
            self.callbacks.unplug_vip_port,
            host='host'
        )

    def test_loadbalancer_deployed(self):
        with self.loadbalancer() as loadbalancer:
            ctx = context.get_admin_context()

            l = self.plugin_instance.db.get_loadbalancer(
                ctx, loadbalancer['loadbalancer']['id'])
            self.assertEqual('PENDING_CREATE', l.provisioning_status)

            self.callbacks.loadbalancer_deployed(
                ctx, loadbalancer['loadbalancer']['id'])

            l = self.plugin_instance.db.get_loadbalancer(
                ctx, loadbalancer['loadbalancer']['id'])
            self.assertEqual('ACTIVE', l.provisioning_status)

    def test_listener_deployed(self):
        with self.loadbalancer(no_delete=True) as loadbalancer:
            self.plugin_instance.db.update_loadbalancer_provisioning_status(
                context.get_admin_context(),
                loadbalancer['loadbalancer']['id'])
            with self.listener(
                    loadbalancer_id=loadbalancer[
                        'loadbalancer']['id']) as listener:
                ctx = context.get_admin_context()

                l = self.plugin_instance.db.get_loadbalancer(
                    ctx, loadbalancer['loadbalancer']['id'])
                self.assertEqual('PENDING_UPDATE', l.provisioning_status)

                ll = self.plugin_instance.db.get_listener(
                    ctx, listener['listener']['id'])
                self.assertEqual('PENDING_CREATE', ll.provisioning_status)

                self.callbacks.loadbalancer_deployed(
                    ctx, loadbalancer['loadbalancer']['id'])

                l = self.plugin_instance.db.get_loadbalancer(
                    ctx, loadbalancer['loadbalancer']['id'])
                self.assertEqual('ACTIVE', l.provisioning_status)
                ll = self.plugin_instance.db.get_listener(
                    ctx, listener['listener']['id'])
                self.assertEqual('ACTIVE', ll.provisioning_status)

    def test_update_status_loadbalancer(self):
        with self.loadbalancer() as loadbalancer:
            loadbalancer_id = loadbalancer['loadbalancer']['id']
            ctx = context.get_admin_context()
            l = self.plugin_instance.db.get_loadbalancer(ctx, loadbalancer_id)
            self.assertEqual('PENDING_CREATE', l.provisioning_status)
            self.callbacks.update_status(ctx, 'loadbalancer',
                                         loadbalancer_id,
                                         provisioning_status=constants.ACTIVE,
                                         operating_status=lb_const.ONLINE)
            l = self.plugin_instance.db.get_loadbalancer(ctx, loadbalancer_id)
            self.assertEqual(constants.ACTIVE, l.provisioning_status)
            self.assertEqual(lb_const.ONLINE, l.operating_status)

    def test_update_status_loadbalancer_deleted_already(self):
        with mock.patch.object(agent_callbacks, 'LOG') as mock_log:
            loadbalancer_id = 'deleted_lb'
            ctx = context.get_admin_context()
            self.assertRaises(loadbalancerv2.EntityNotFound,
                              self.plugin_instance.get_loadbalancer, ctx,
                              loadbalancer_id)
            self.callbacks.update_status(ctx, 'loadbalancer',
                                         loadbalancer_id,
                                         provisioning_status=constants.ACTIVE)
            self.assertTrue(mock_log.warning.called)
