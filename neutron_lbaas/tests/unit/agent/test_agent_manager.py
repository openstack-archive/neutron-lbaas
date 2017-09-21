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

import collections

import mock
from neutron_lib import constants

from neutron_lbaas.agent import agent_manager as manager
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests import base


class TestManager(base.BaseTestCase):
    def setUp(self):
        super(TestManager, self).setUp()

        mock_conf = mock.Mock()
        mock_conf.device_driver = ['devdriver']

        self.mock_importer = mock.patch.object(manager, 'importutils').start()

        rpc_mock_cls = mock.patch(
            'neutron_lbaas.agent.agent_api.LbaasAgentApi'
        ).start()

        # disable setting up periodic state reporting
        mock_conf.AGENT.report_interval = 0

        self.mgr = manager.LbaasAgentManager(mock_conf)
        self.rpc_mock = rpc_mock_cls.return_value
        self.log = mock.patch.object(manager, 'LOG').start()
        self.driver_mock = mock.Mock()
        self.mgr.device_drivers = {'devdriver': self.driver_mock}
        instance_mapping = [('1', 'devdriver'), ('2', 'devdriver')]
        self.mgr.instance_mapping = collections.OrderedDict(instance_mapping)
        self.mgr.needs_resync = False
        self.update_statuses_patcher = mock.patch.object(
            self.mgr, '_update_statuses')
        self.update_statuses = self.update_statuses_patcher.start()

    def test_initialize_service_hook(self):
        with mock.patch.object(self.mgr, 'sync_state') as sync:
            self.mgr.initialize_service_hook(mock.Mock())
            sync.assert_called_once_with()

    def test_periodic_resync_needs_sync(self):
        with mock.patch.object(self.mgr, 'sync_state') as sync:
            self.mgr.needs_resync = True
            self.mgr.periodic_resync(mock.Mock())
            sync.assert_called_once_with()

    def test_periodic_resync_no_sync(self):
        with mock.patch.object(self.mgr, 'sync_state') as sync:
            self.mgr.needs_resync = False
            self.mgr.periodic_resync(mock.Mock())
            self.assertFalse(sync.called)

    def test_collect_stats(self):
        self.mgr.collect_stats(mock.Mock())
        self.rpc_mock.update_loadbalancer_stats.assert_has_calls([
            mock.call('1', mock.ANY),
            mock.call('2', mock.ANY)
        ], any_order=True)

    def test_collect_stats_exception(self):
        self.driver_mock.loadbalancer.get_stats.side_effect = Exception

        self.mgr.collect_stats(mock.Mock())

        self.assertFalse(self.rpc_mock.called)
        self.assertTrue(self.mgr.needs_resync)
        self.assertTrue(self.log.exception.called)

    def _sync_state_helper(self, ready, reloaded, destroyed):
        with mock.patch.object(self.mgr, '_reload_loadbalancer') as reload, \
                mock.patch.object(self.mgr, '_destroy_loadbalancer') as \
                destroy:
            self.rpc_mock.get_ready_devices.return_value = ready

            self.mgr.sync_state()

            self.assertEqual(len(reloaded), len(reload.mock_calls))
            self.assertEqual(len(destroyed), len(destroy.mock_calls))

            reload.assert_has_calls([mock.call(i) for i in reloaded],
                                    any_order=True)
            destroy.assert_has_calls([mock.call(i) for i in destroyed],
                                     any_order=True)
            self.assertFalse(self.mgr.needs_resync)

    def test_sync_state_all_known(self):
        self._sync_state_helper(['1', '2'], ['1', '2'], [])

    def test_sync_state_all_unknown(self):
        self.mgr.instance_mapping = {}
        self._sync_state_helper(['1', '2'], ['1', '2'], [])

    def test_sync_state_destroy_all(self):
        self._sync_state_helper([], [], ['1', '2'])

    def test_sync_state_both(self):
        self.mgr.instance_mapping = {'1': 'devdriver'}
        self._sync_state_helper(['2'], ['2'], ['1'])

    def test_sync_state_exception(self):
        self.rpc_mock.get_ready_devices.side_effect = Exception

        self.mgr.sync_state()

        self.assertTrue(self.log.exception.called)
        self.assertTrue(self.mgr.needs_resync)

    def test_reload_loadbalancer(self):
        lb = data_models.LoadBalancer(id='1').to_dict()
        lb['provider'] = {'device_driver': 'devdriver'}
        self.rpc_mock.get_loadbalancer.return_value = lb
        lb_id = 'new_id'
        self.assertNotIn(lb_id, self.mgr.instance_mapping)

        self.mgr._reload_loadbalancer(lb_id)

        calls = self.driver_mock.deploy_instance.call_args_list
        self.assertEqual(1, len(calls))
        called_lb = calls[0][0][0]
        self.assertEqual(lb['id'], called_lb.id)
        self.assertIn(lb['id'], self.mgr.instance_mapping)
        self.rpc_mock.loadbalancer_deployed.assert_called_once_with(lb_id)

    def test_reload_loadbalancer_driver_not_found(self):
        lb = data_models.LoadBalancer(id='1').to_dict()
        lb['provider'] = {'device_driver': 'unknowndriver'}
        self.rpc_mock.get_loadbalancer.return_value = lb
        lb_id = 'new_id'
        self.assertNotIn(lb_id, self.mgr.instance_mapping)

        self.mgr._reload_loadbalancer(lb_id)

        self.assertTrue(self.log.error.called)
        self.assertFalse(self.driver_mock.deploy_instance.called)
        self.assertNotIn(lb_id, self.mgr.instance_mapping)
        self.assertFalse(self.rpc_mock.loadbalancer_deployed.called)

    def test_reload_loadbalancer_exception_on_driver(self):
        lb = data_models.LoadBalancer(id='3').to_dict()
        lb['provider'] = {'device_driver': 'devdriver'}
        self.rpc_mock.get_loadbalancer.return_value = lb
        self.driver_mock.deploy_instance.side_effect = Exception
        lb_id = 'new_id'
        self.assertNotIn(lb_id, self.mgr.instance_mapping)

        self.mgr._reload_loadbalancer(lb_id)

        calls = self.driver_mock.deploy_instance.call_args_list
        self.assertEqual(1, len(calls))
        called_lb = calls[0][0][0]
        self.assertEqual(lb['id'], called_lb.id)
        self.assertNotIn(lb['id'], self.mgr.instance_mapping)
        self.assertFalse(self.rpc_mock.loadbalancer_deployed.called)
        self.assertTrue(self.log.exception.called)
        self.assertTrue(self.mgr.needs_resync)

    def test_destroy_loadbalancer(self):
        lb_id = '1'
        self.assertIn(lb_id, self.mgr.instance_mapping)

        self.mgr._destroy_loadbalancer(lb_id)

        self.driver_mock.undeploy_instance.assert_called_once_with(
            lb_id, delete_namespace=True)
        self.assertNotIn(lb_id, self.mgr.instance_mapping)
        self.rpc_mock.loadbalancer_destroyed.assert_called_once_with(lb_id)
        self.assertFalse(self.mgr.needs_resync)

    def test_destroy_loadbalancer_exception_on_driver(self):
        lb_id = '1'
        self.assertIn(lb_id, self.mgr.instance_mapping)
        self.driver_mock.undeploy_instance.side_effect = Exception

        self.mgr._destroy_loadbalancer(lb_id)

        self.driver_mock.undeploy_instance.assert_called_once_with(
            lb_id, delete_namespace=True)
        self.assertIn(lb_id, self.mgr.instance_mapping)
        self.assertFalse(self.rpc_mock.loadbalancer_destroyed.called)
        self.assertTrue(self.log.exception.called)
        self.assertTrue(self.mgr.needs_resync)

    def test_get_driver_unknown_device(self):
        self.assertRaises(manager.DeviceNotFoundOnAgent,
                          self.mgr._get_driver, 'unknown')

    def test_remove_orphans(self):
        self.mgr.remove_orphans()
        self.driver_mock.remove_orphans.assert_called_once_with(['1', '2'])

    def test_agent_disabled(self):
        payload = {'admin_state_up': False}
        self.mgr.agent_updated(mock.Mock(), payload)
        self.driver_mock.undeploy_instance.assert_has_calls(
            [mock.call('1', delete_namespace=True),
             mock.call('2', delete_namespace=True)],
            any_order=True
        )

    def test_update_statuses_loadbalancer(self):
        self.update_statuses_patcher.stop()
        lb = data_models.LoadBalancer(id='1')
        self.mgr._update_statuses(lb)
        self.rpc_mock.update_status.assert_called_once_with(
            'loadbalancer', lb.id, provisioning_status=constants.ACTIVE,
            operating_status=lb_const.ONLINE)

        self.rpc_mock.update_status.reset_mock()
        self.mgr._update_statuses(lb, error=True)
        self.rpc_mock.update_status.assert_called_once_with(
            'loadbalancer', lb.id, provisioning_status=constants.ERROR,
            operating_status=lb_const.OFFLINE)

    def test_update_statuses_listener(self):
        self.update_statuses_patcher.stop()
        listener = data_models.Listener(id='1')
        lb = data_models.LoadBalancer(id='1', listeners=[listener])
        listener.loadbalancer = lb
        self.mgr._update_statuses(listener)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('listener', listener.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=lb_const.ONLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

        self.rpc_mock.update_status.reset_mock()
        self.mgr._update_statuses(listener, error=True)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('listener', listener.id,
                           provisioning_status=constants.ERROR,
                           operating_status=lb_const.OFFLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

    def test_update_statuses_pool(self):
        self.update_statuses_patcher.stop()
        pool = data_models.Pool(id='1')
        listener = data_models.Listener(id='1', default_pool=pool)
        lb = data_models.LoadBalancer(id='1', listeners=[listener])
        listener.loadbalancer = lb
        pool.loadbalancer = lb
        self.mgr._update_statuses(pool)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('pool', pool.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=lb_const.ONLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

        self.rpc_mock.update_status.reset_mock()
        self.mgr._update_statuses(pool, error=True)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('pool', pool.id,
                           provisioning_status=constants.ERROR,
                           operating_status=lb_const.OFFLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

    def test_update_statuses_member(self):
        self.update_statuses_patcher.stop()
        member = data_models.Member(id='1')
        pool = data_models.Pool(id='1', members=[member])
        member.pool = pool
        listener = data_models.Listener(id='1', default_pool=pool)
        lb = data_models.LoadBalancer(id='1', listeners=[listener])
        listener.loadbalancer = lb
        pool.loadbalancer = lb
        self.mgr._update_statuses(member)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('member', member.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=lb_const.ONLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

        self.rpc_mock.update_status.reset_mock()
        self.mgr._update_statuses(member, error=True)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('member', member.id,
                           provisioning_status=constants.ERROR,
                           operating_status=lb_const.OFFLINE),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

    def test_update_statuses_healthmonitor(self):
        self.update_statuses_patcher.stop()
        hm = data_models.HealthMonitor(id='1')
        pool = data_models.Pool(id='1', healthmonitor=hm)
        hm.pool = pool
        listener = data_models.Listener(id='1', default_pool=pool)
        lb = data_models.LoadBalancer(id='1', listeners=[listener])
        listener.loadbalancer = lb
        pool.loadbalancer = lb
        self.mgr._update_statuses(hm)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('healthmonitor', hm.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

        self.rpc_mock.update_status.reset_mock()
        self.mgr._update_statuses(hm, error=True)
        self.assertEqual(2, self.rpc_mock.update_status.call_count)
        calls = [mock.call('healthmonitor', hm.id,
                           provisioning_status=constants.ERROR,
                           operating_status=None),
                 mock.call('loadbalancer', lb.id,
                           provisioning_status=constants.ACTIVE,
                           operating_status=None)]
        self.rpc_mock.update_status.assert_has_calls(calls)

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_create_loadbalancer(self, mlb):
        loadbalancer = data_models.LoadBalancer(id='1')

        self.assertIn(loadbalancer.id, self.mgr.instance_mapping)
        mlb.return_value = loadbalancer
        self.mgr.create_loadbalancer(mock.Mock(), loadbalancer.to_dict(),
                                     'devdriver')
        self.driver_mock.loadbalancer.create.assert_called_once_with(
            loadbalancer)
        self.update_statuses.assert_called_once_with(loadbalancer)

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_create_loadbalancer_failed(self, mlb):
        loadbalancer = data_models.LoadBalancer(id='1')

        self.assertIn(loadbalancer.id, self.mgr.instance_mapping)
        self.driver_mock.loadbalancer.create.side_effect = Exception
        mlb.return_value = loadbalancer
        self.mgr.create_loadbalancer(mock.Mock(), loadbalancer.to_dict(),
                                     'devdriver')
        self.driver_mock.loadbalancer.create.assert_called_once_with(
            loadbalancer)
        self.update_statuses.assert_called_once_with(loadbalancer, error=True)

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_update_loadbalancer(self, mlb):

        loadbalancer = data_models.LoadBalancer(id='1',
                                                vip_address='10.0.0.1')
        old_loadbalancer = data_models.LoadBalancer(id='1',
                                                    vip_address='10.0.0.2')

        mlb.side_effect = [loadbalancer, old_loadbalancer]
        self.mgr.update_loadbalancer(mock.Mock(), old_loadbalancer.to_dict(),
                                     loadbalancer.to_dict())
        self.driver_mock.loadbalancer.update.assert_called_once_with(
            old_loadbalancer, loadbalancer)
        self.update_statuses.assert_called_once_with(loadbalancer)

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_update_loadbalancer_failed(self, mlb):
        loadbalancer = data_models.LoadBalancer(id='1',
                                                vip_address='10.0.0.1')
        old_loadbalancer = data_models.LoadBalancer(id='1',
                                                    vip_address='10.0.0.2')

        mlb.side_effect = [loadbalancer, old_loadbalancer]
        self.driver_mock.loadbalancer.update.side_effect = Exception
        self.mgr.update_loadbalancer(mock.Mock(), old_loadbalancer,
                                     loadbalancer)
        self.driver_mock.loadbalancer.update.assert_called_once_with(
            old_loadbalancer, loadbalancer)
        self.update_statuses.assert_called_once_with(loadbalancer, error=True)

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_delete_loadbalancer(self, mlb):
        loadbalancer = data_models.LoadBalancer(id='1')
        mlb.return_value = loadbalancer
        self.assertIn(loadbalancer.id, self.mgr.instance_mapping)
        self.mgr.delete_loadbalancer(mock.Mock(), loadbalancer.to_dict())
        self.driver_mock.loadbalancer.delete.assert_called_once_with(
            loadbalancer)
        self.assertNotIn(loadbalancer.id, self.mgr.instance_mapping)

    @mock.patch.object(data_models.Listener, 'from_dict')
    def test_create_listener(self, mlistener):
        loadbalancer = data_models.LoadBalancer(id='1')
        listener = data_models.Listener(id=1, loadbalancer_id='1',
                                        loadbalancer=loadbalancer)

        self.assertIn(loadbalancer.id, self.mgr.instance_mapping)
        mlistener.return_value = listener
        self.mgr.create_listener(mock.Mock(), listener.to_dict())
        self.driver_mock.listener.create.assert_called_once_with(listener)
        self.update_statuses.assert_called_once_with(listener)

    @mock.patch.object(data_models.Listener, 'from_dict')
    def test_create_listener_failed(self, mlistener):
        loadbalancer = data_models.LoadBalancer(id='1')
        listener = data_models.Listener(id=1, loadbalancer_id='1',
                                        loadbalancer=loadbalancer)

        self.assertIn(loadbalancer.id, self.mgr.instance_mapping)
        self.driver_mock.listener.create.side_effect = Exception
        mlistener.return_value = listener
        self.mgr.create_listener(mock.Mock(), listener.to_dict())
        self.driver_mock.listener.create.assert_called_once_with(listener)
        self.update_statuses.assert_called_once_with(listener, error=True)

    @mock.patch.object(data_models.Listener, 'from_dict')
    def test_update_listener(self, mlistener):
        loadbalancer = data_models.LoadBalancer(id='1')
        old_listener = data_models.Listener(id=1, loadbalancer_id='1',
                                            loadbalancer=loadbalancer,
                                            protocol_port=80)
        listener = data_models.Listener(id=1, loadbalancer_id='1',
                                        loadbalancer=loadbalancer,
                                        protocol_port=81)

        mlistener.side_effect = [listener, old_listener]
        self.mgr.update_listener(mock.Mock(), old_listener.to_dict(),
                                 listener.to_dict())
        self.driver_mock.listener.update.assert_called_once_with(
            old_listener, listener)
        self.update_statuses.assert_called_once_with(listener)

    @mock.patch.object(data_models.Listener, 'from_dict')
    def test_update_listener_failed(self, mlistener):
        loadbalancer = data_models.LoadBalancer(id='1')
        old_listener = data_models.Listener(id=1, loadbalancer_id='1',
                                            loadbalancer=loadbalancer,
                                            protocol_port=80)
        listener = data_models.Listener(id=1, loadbalancer_id='1',
                                        loadbalancer=loadbalancer,
                                        protocol_port=81)
        mlistener.side_effect = [listener, old_listener]
        self.driver_mock.listener.update.side_effect = Exception
        self.mgr.update_listener(mock.Mock(), old_listener, listener)
        self.driver_mock.listener.update.assert_called_once_with(old_listener,
                                                                 listener)
        self.update_statuses.assert_called_once_with(listener, error=True)

    @mock.patch.object(data_models.Listener, 'from_dict')
    def test_delete_listener(self, mlistener):
        loadbalancer = data_models.LoadBalancer(id='1')
        listener = data_models.Listener(id=1, loadbalancer_id='1',
                                        loadbalancer=loadbalancer,
                                        protocol_port=80)
        mlistener.return_value = listener
        self.mgr.delete_listener(mock.Mock(), listener.to_dict())
        self.driver_mock.listener.delete.assert_called_once_with(listener)

    @mock.patch.object(data_models.Pool, 'from_dict')
    def test_create_pool(self, mpool):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer)

        mpool.return_value = pool
        self.mgr.create_pool(mock.Mock(), pool.to_dict())
        self.driver_mock.pool.create.assert_called_once_with(pool)
        self.update_statuses.assert_called_once_with(pool)

    @mock.patch.object(data_models.Pool, 'from_dict')
    def test_create_pool_failed(self, mpool):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer)

        mpool.return_value = pool
        self.driver_mock.pool.create.side_effect = Exception
        self.mgr.create_pool(mock.Mock(), pool)
        self.driver_mock.pool.create.assert_called_once_with(pool)
        self.update_statuses.assert_called_once_with(pool, error=True)

    @mock.patch.object(data_models.Pool, 'from_dict')
    def test_update_pool(self, mpool):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        old_pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                    protocol='HTTP')
        mpool.side_effect = [pool, old_pool]
        self.mgr.update_pool(mock.Mock(), old_pool.to_dict(), pool.to_dict())
        self.driver_mock.pool.update.assert_called_once_with(old_pool, pool)
        self.update_statuses.assert_called_once_with(pool)

    @mock.patch.object(data_models.Pool, 'from_dict')
    def test_update_pool_failed(self, mpool):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        old_pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                    protocol='HTTP')
        mpool.side_effect = [pool, old_pool]
        self.driver_mock.pool.update.side_effect = Exception
        self.mgr.update_pool(mock.Mock(), old_pool.to_dict(), pool.to_dict())
        self.driver_mock.pool.update.assert_called_once_with(old_pool, pool)
        self.update_statuses.assert_called_once_with(pool, error=True)

    @mock.patch.object(data_models.Pool, 'from_dict')
    def test_delete_pool(self, mpool):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        mpool.return_value = pool
        self.mgr.delete_pool(mock.Mock(), pool.to_dict())
        self.driver_mock.pool.delete.assert_called_once_with(pool)

    @mock.patch.object(data_models.Member, 'from_dict')
    def test_create_member(self, mmember):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        member = data_models.Member(id='1', pool=pool)
        mmember.return_value = member
        self.mgr.create_member(mock.Mock(), member.to_dict())
        self.driver_mock.member.create.assert_called_once_with(member)
        self.update_statuses.assert_called_once_with(member)

    @mock.patch.object(data_models.Member, 'from_dict')
    def test_create_member_failed(self, mmember):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        member = data_models.Member(id='1', pool=pool)
        mmember.return_value = member
        self.driver_mock.member.create.side_effect = Exception
        self.mgr.create_member(mock.Mock(), member.to_dict())
        self.driver_mock.member.create.assert_called_once_with(member)
        self.update_statuses.assert_called_once_with(member, error=True)

    @mock.patch.object(data_models.Member, 'from_dict')
    def test_update_member(self, mmember):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        member = data_models.Member(id='1', pool=pool, weight=1)
        old_member = data_models.Member(id='1', pool=pool, weight=2)
        mmember.side_effect = [member, old_member]
        self.mgr.update_member(mock.Mock(), old_member.to_dict(),
                               member.to_dict())
        self.driver_mock.member.update.assert_called_once_with(old_member,
                                                               member)
        self.update_statuses.assert_called_once_with(member)

    @mock.patch.object(data_models.Member, 'from_dict')
    def test_update_member_failed(self, mmember):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        member = data_models.Member(id='1', pool=pool, weight=1)
        old_member = data_models.Member(id='1', pool=pool, weight=2)
        mmember.side_effect = [member, old_member]
        self.driver_mock.member.update.side_effect = Exception
        self.mgr.update_member(mock.Mock(), old_member.to_dict(),
                               member.to_dict())
        self.driver_mock.member.update.assert_called_once_with(old_member,
                                                               member)
        self.update_statuses.assert_called_once_with(member, error=True)

    @mock.patch.object(data_models.Member, 'from_dict')
    def test_delete_member(self, mmember):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        member = data_models.Member(id='1', pool=pool, weight=1)
        mmember.return_value = member
        self.mgr.delete_member(mock.Mock(), member.to_dict())
        self.driver_mock.member.delete.assert_called_once_with(member)

    @mock.patch.object(data_models.HealthMonitor, 'from_dict')
    def test_create_monitor(self, mmonitor):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        monitor = data_models.HealthMonitor(id='1', pool=pool)
        mmonitor.return_value = monitor
        self.mgr.create_healthmonitor(mock.Mock(), monitor.to_dict())
        self.driver_mock.healthmonitor.create.assert_called_once_with(
            monitor)
        self.update_statuses.assert_called_once_with(monitor)

    @mock.patch.object(data_models.HealthMonitor, 'from_dict')
    def test_create_monitor_failed(self, mmonitor):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        monitor = data_models.HealthMonitor(id='1', pool=pool)
        mmonitor.return_value = monitor
        self.driver_mock.healthmonitor.create.side_effect = Exception
        self.mgr.create_healthmonitor(mock.Mock(), monitor.to_dict())
        self.driver_mock.healthmonitor.create.assert_called_once_with(monitor)
        self.update_statuses.assert_called_once_with(monitor, error=True)

    @mock.patch.object(data_models.HealthMonitor, 'from_dict')
    def test_update_monitor(self, mmonitor):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        monitor = data_models.HealthMonitor(id='1', pool=pool, delay=1)
        old_monitor = data_models.HealthMonitor(id='1', pool=pool, delay=2)
        mmonitor.side_effect = [monitor, old_monitor]
        self.mgr.update_healthmonitor(mock.Mock(), old_monitor.to_dict(),
                                      monitor.to_dict())
        self.driver_mock.healthmonitor.update.assert_called_once_with(
            old_monitor, monitor)
        self.update_statuses.assert_called_once_with(monitor)

    @mock.patch.object(data_models.HealthMonitor, 'from_dict')
    def test_update_monitor_failed(self, mmonitor):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        monitor = data_models.HealthMonitor(id='1', pool=pool, delay=1)
        old_monitor = data_models.HealthMonitor(id='1', pool=pool, delay=2)
        mmonitor.side_effect = [monitor, old_monitor]
        self.driver_mock.healthmonitor.update.side_effect = Exception
        self.mgr.update_healthmonitor(mock.Mock(), monitor.to_dict(),
                                      monitor.to_dict())
        self.driver_mock.healthmonitor.update.assert_called_once_with(
            old_monitor, monitor)
        self.update_statuses.assert_called_once_with(monitor, error=True)

    @mock.patch.object(data_models.HealthMonitor, 'from_dict')
    def test_delete_monitor(self, mmonitor):
        loadbalancer = data_models.LoadBalancer(id='1')
        pool = data_models.Pool(id='1', loadbalancer=loadbalancer,
                                protocol='HTTPS')
        monitor = data_models.HealthMonitor(id='1', pool=pool)
        mmonitor.return_value = monitor
        self.mgr.delete_healthmonitor(mock.Mock(), monitor.to_dict())
        self.driver_mock.healthmonitor.delete.assert_called_once_with(
            monitor)
