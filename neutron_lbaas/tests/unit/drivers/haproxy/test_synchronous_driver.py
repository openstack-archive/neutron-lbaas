# Copyright 2014-2015 Rackspace
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
#

import collections
import contextlib

import mock
from neutron.common import exceptions
from neutron.extensions import portbindings
from neutron.plugins.common import constants
import six

from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.drivers.haproxy \
    import synchronous_namespace_driver as sync_driver
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.services.loadbalancer.drivers.haproxy \
    import namespace_driver
from neutron_lbaas.tests import base


class TestHaproxyNSDriver(base.BaseTestCase):
    def setUp(self):
        super(TestHaproxyNSDriver, self).setUp()

        conf = mock.Mock()
        conf.haproxy.loadbalancer_state_path = '/the/path'
        conf.interface_driver = 'intdriver'
        conf.haproxy.user_group = 'test_group'
        conf.haproxy.send_gratuitous_arp = 3
        conf.haproxy.periodic_interval = 10
        conf.host = 'host1'
        self.conf = conf
        self.context_mock = mock.Mock()
        self.plugin_mock = mock.Mock()
        self.plugin_mock.db = mock.Mock()
        self.plugin_mock.db._core_plugin = mock.Mock()
        self.mock_service = mock.patch.object(
            sync_driver, 'SimpleHaproxyStatsService').start()
        with mock.patch(
                'neutron.common.utils.load_class_by_alias_or_classname'):
            self.driver = sync_driver.HaproxyNSDriver(
                self.plugin_mock)
        self.driver.state_path = '/the/path/v2'
        self.vif_driver = mock.Mock()
        self.driver.vif_driver = self.vif_driver

    def test_get_ns_name(self):
        self.assertEqual(namespace_driver.NS_PREFIX + 'ns_id_1',
                         namespace_driver.get_ns_name('ns_id_1'))

    def test_deploy_existing_instance(self):
        dirs = ['lbid1', 'lbid2']
        lbs = [self._sample_in_loadbalancer(), self._sample_in_loadbalancer()]
        with contextlib.nested(
            mock.patch.object(self.driver, '_retrieve_deployed_instance_dirs',
                              return_value=dirs),
            mock.patch.object(self.driver,
                              '_retrieve_db_loadbalancers_from_dirs',
                              return_value=lbs),
            mock.patch.object(self.driver, 'update_instance')
        ) as (rin, rdb, upin):
            self.driver._deploy_existing_instances()
            rin.assert_called_once_with()
            rdb.asert_called_once_with(dirs)
            upin.assert_has_calls([mock.call(lbs[0]), mock.call(lbs[1])])
            self.assertEqual(2, upin.call_count)
            # deployed_loadbalancer_ids is a set
            self.assertEqual(1, len(self.driver.deployed_loadbalancer_ids))
            self.assertIn(self._sample_in_loadbalancer().id,
                          self.driver.deployed_loadbalancer_ids)

    def test_retrieve_deployed_instance_dirs(self):
        with mock.patch('os.path.exists', return_value=True):
            with mock.patch('os.path.isdir', return_value=True):
                with mock.patch('os.listdir', return_value=['lbid1',
                                                            'lbid2']):
                    with mock.patch('os.makedirs') as mkdir:
                        self.assertFalse(mkdir.called)
                        self.assertEqual(
                            ['lbid1',
                             'lbid2'],
                            self.driver._retrieve_deployed_instance_dirs())

    def test_retrieve_db_loadbalancers_from_dirs(self):
        with contextlib.nested(
            mock.patch.object(self.plugin_mock.db, 'get_loadbalancer'),
            mock.patch.object(self.driver, '_delete_instance_from_system'),
            mock.patch.object(self.driver, 'load_balancer'),
        ) as (glb, delin, lb_man):
            dirs = ['lb1', 'lb2']
            gr_return = [self._sample_in_loadbalancer(),
                         loadbalancerv2.EntityNotFound(name='whatever',
                                                       id='1')]
            call1 = mock.call(self.driver.admin_ctx, 'lb1')
            call2 = mock.call(self.driver.admin_ctx, 'lb2')
            glb.side_effect = gr_return
            actual_ret = self.driver._retrieve_db_loadbalancers_from_dirs(dirs)
            glb.assert_has_calls([call1, call2])
            self.assertEqual(2, glb.call_count)
            delin.assert_called_once_with('lb2')
            self.assertEqual([self._sample_in_loadbalancer()], actual_ret)

    def test_plug_vip_port(self):
        ret_port = {'id': '1', 'name': 'port1'}
        built_port = {'admin_state_up': True}
        with contextlib.nested(
            mock.patch.object(self.plugin_mock.db._core_plugin, 'get_port',
                              return_value=ret_port),
            mock.patch.object(self.driver, '_build_port_dict',
                              return_value=built_port),
            mock.patch.object(self.plugin_mock.db._core_plugin, 'update_port')
        ) as (gp, bpd, up):
            mock_ctx = mock.Mock()
            port = data_models.Port(id='1')
            self.driver._plug_vip_port(mock_ctx, port)
            gp.assert_called_once_with(mock_ctx, port.id)
            bpd.assert_called_once_with()
            ret_port.update(built_port)
            up.assert_called_once_with(mock_ctx, port.id,
                                       {'port': ret_port})

    def test_build_port_dict(self):
        self.driver.conf.host = 'host1'
        ret = {'admin_state_up': True,
               portbindings.HOST_ID: self.conf.host}
        self.assertEqual(self.driver._build_port_dict(), ret)

    def test_get_state_file_path(self):
        with mock.patch('os.makedirs') as mkdir:
            path = self.driver._get_state_file_path('loadbalancer_id', 'conf')
            self.assertEqual('/the/path/v2/loadbalancer_id/conf', path)
            mkdir.assert_called_once_with('/the/path/v2/loadbalancer_id',
                                          0o755)

    def test_populate_subnets(self):
        fixed_ips = [mock.Mock(), mock.Mock()]
        port = data_models.Port()
        port.fixed_ips = fixed_ips
        ret_subnet = object()
        with mock.patch.object(self.driver.plugin.db._core_plugin,
                               'get_subnet', return_value=ret_subnet):
            self.driver._populate_subnets(self.context_mock, port)
            for fixed_ip in port.fixed_ips:
                self.assertEqual(fixed_ip.subnet, ret_subnet)

    def test_plug(self):
        fixed_ips = [data_models.IPAllocation(ip_address='10.0.0.2',
                                              subnet_id='subnet_id_1',
                                              network_id='network_id_1')]
        fixed_ips[0].subnet = {'cidr': '10.0.0.0/24', 'gateway_ip': '10.0.0.1'}
        test_port = data_models.Port(id='port_id', network_id='net_id',
                                     mac_address='mac_addr',
                                     fixed_ips=fixed_ips)
        with contextlib.nested(
                mock.patch('neutron.agent.linux.ip_lib.device_exists'),
                mock.patch('netaddr.IPNetwork'),
                mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
                mock.patch.object(self.driver, '_plug_vip_port'),
                mock.patch.object(self.driver, '_populate_subnets')
        ) as (dev_exists, ip_net, ip_wrap, vp_plug, pop_subnets):
            self.vif_driver.get_device_name.return_value = 'test_interface'
            dev_exists.return_value = False
            ip_net.return_value = ip_net
            ip_net.prefixlen = 24

            self.driver._plug(self.context_mock, 'test_ns', test_port)
            vp_plug.assert_called_once_with(
                self.context_mock, test_port)
            self.assertTrue(dev_exists.called)
            self.vif_driver.plug.assert_called_once_with('net_id', 'port_id',
                                                         'test_interface',
                                                         'mac_addr',
                                                         namespace='test_ns')
            self.vif_driver.init_l3.assert_called_once_with(
                'test_interface', ['10.0.0.2/24'], namespace='test_ns')
            cmd = ['route', 'add', 'default', 'gw', '10.0.0.1']
            cmd_arping = ['arping', '-U', '-I',
                          'test_interface', '-c',
                          self.conf.haproxy.send_gratuitous_arp, '10.0.0.2']
            ip_wrap.assert_has_calls([
                mock.call(namespace='test_ns'),
                mock.call().netns.execute(cmd, check_exit_code=False),
                mock.call().netns.execute(cmd_arping, check_exit_code=False),
            ])

            dev_exists.return_value = True
            self.assertRaises(exceptions.PreexistingDeviceFailure,
                              self.driver._plug, self.context_mock,
                              'test_ns', test_port, False)

    def test_plug_not_send_gratuitous_arp(self):
        self.driver.conf.haproxy.send_gratuitous_arp = 0
        fixed_ips = [data_models.IPAllocation(ip_address='10.0.0.2',
                                              subnet_id='subnet_id_1',
                                              network_id='network_id_1')]
        fixed_ips[0].subnet = {'cidr': '10.0.0.0/24', 'gateway_ip': '10.0.0.1'}
        test_port = data_models.Port(id='port_id', network_id='net_id',
                                     mac_address='mac_addr',
                                     fixed_ips=fixed_ips)
        with contextlib.nested(
                mock.patch('neutron.agent.linux.ip_lib.device_exists'),
                mock.patch('netaddr.IPNetwork'),
                mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
                mock.patch.object(self.driver, '_plug_vip_port'),
                mock.patch.object(self.driver, '_populate_subnets')
        ) as (dev_exists, ip_net, ip_wrap, vp_plug, pop_subnets):
            self.vif_driver.get_device_name.return_value = 'test_interface'
            dev_exists.return_value = False
            ip_net.return_value = ip_net
            ip_net.prefixlen = 24

            self.driver._plug(self.context_mock, 'test_ns', test_port)
            cmd = ['route', 'add', 'default', 'gw', '10.0.0.1']
            expected = [
                mock.call(namespace='test_ns'),
                mock.call().netns.execute(cmd, check_exit_code=False)]
            self.assertEqual(expected, ip_wrap.mock_calls)

    def test_plug_no_gw(self):
        fixed_ips = [data_models.IPAllocation(ip_address='10.0.0.2',
                                              subnet_id='subnet_id_1',
                                              network_id='network_id_1')]
        fixed_ips[0].subnet = {'cidr': '10.0.0.0/24'}
        test_port = data_models.Port(id='port_id', network_id='net_id',
                                     mac_address='mac_addr',
                                     fixed_ips=fixed_ips)
        with contextlib.nested(
                mock.patch('neutron.agent.linux.ip_lib.device_exists'),
                mock.patch('netaddr.IPNetwork'),
                mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
                mock.patch.object(self.driver, '_plug_vip_port'),
                mock.patch.object(self.driver, '_populate_subnets')
        ) as (dev_exists, ip_net, ip_wrap, vp_plug, pop_subnets):
            self.vif_driver.get_device_name.return_value = 'test_interface'
            dev_exists.return_value = False
            ip_net.return_value = ip_net
            ip_net.prefixlen = 24

            self.driver._plug(self.context_mock, 'test_ns', test_port)
            self.driver._plug_vip_port.assert_called_once_with(
                self.context_mock, test_port)
            self.assertTrue(dev_exists.called)
            self.vif_driver.plug.assert_called_once_with(
                'net_id', 'port_id', 'test_interface', 'mac_addr',
                namespace='test_ns')
            self.vif_driver.init_l3.assert_called_once_with(
                'test_interface', ['10.0.0.2/24'], namespace='test_ns')
            self.assertFalse(ip_wrap.called)
            dev_exists.return_value = True
            self.assertRaises(exceptions.PreexistingDeviceFailure,
                              self.driver._plug, self.context_mock,
                              'test_ns', test_port, False)

    def test_plug_gw_in_host_routes(self):
        fixed_ips = [data_models.IPAllocation(ip_address='10.0.0.2',
                                              subnet_id='subnet_id_1',
                                              network_id='network_id_1')]
        fixed_ips[0].subnet = {'cidr': '10.0.0.0/24', 'gateway_ip': '10.0.0.1'}
        test_port = data_models.Port(id='port_id', network_id='net_id',
                                     mac_address='mac_addr',
                                     fixed_ips=fixed_ips)
        with contextlib.nested(
                mock.patch('neutron.agent.linux.ip_lib.device_exists'),
                mock.patch('netaddr.IPNetwork'),
                mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
                mock.patch.object(self.driver, '_plug_vip_port'),
                mock.patch.object(self.driver, '_populate_subnets')
        ) as (dev_exists, ip_net, ip_wrap, vp_plug, pop_subnets):
            self.vif_driver.get_device_name.return_value = 'test_interface'
            dev_exists.return_value = False
            ip_net.return_value = ip_net
            ip_net.prefixlen = 24

            self.driver._plug(self.context_mock, 'test_ns', test_port)
            self.driver._plug_vip_port.assert_called_once_with(
                self.context_mock, test_port)
            self.assertTrue(dev_exists.called)
            self.vif_driver.plug.assert_called_once_with(
                'net_id', 'port_id', 'test_interface', 'mac_addr',
                namespace='test_ns')
            self.vif_driver.init_l3.assert_called_once_with(
                'test_interface', ['10.0.0.2/24'], namespace='test_ns')
            cmd = ['route', 'add', 'default', 'gw', '10.0.0.1']
            ip_wrap.assert_has_calls([
                mock.call(namespace='test_ns'),
                mock.call().netns.execute(cmd, check_exit_code=False),
            ])

    def test_unplug(self):
        self.vif_driver.get_device_name.return_value = 'test_interface'

        self.driver._unplug('test_ns', 'port_id')
        self.vif_driver.unplug('test_interface', namespace='test_ns')

    def test_spawn(self):
        with contextlib.nested(
            mock.patch.object(sync_driver.jinja_cfg, 'save_config'),
            mock.patch.object(self.driver, '_get_state_file_path'),
            mock.patch('neutron.agent.linux.ip_lib.IPWrapper')
        ) as (mock_save, gsp, ip_wrap):
            gsp.side_effect = lambda x, y: y

            self.driver._spawn(self._sample_in_loadbalancer())

            mock_save.assert_called_once_with('haproxy.conf',
                                              self._sample_in_loadbalancer(),
                                              'haproxy_stats.sock', 'nogroup',
                                              '')  # state_path is empty
            cmd = ['haproxy', '-f', 'haproxy.conf', '-p', 'haproxy.pid']
            ns_name = ''.join([sync_driver.NS_PREFIX,
                              self._sample_in_loadbalancer().id])
            ip_wrap.assert_has_calls([
                mock.call(namespace=ns_name),
                mock.call().netns.execute(cmd)
            ])

    def test_collect_and_store_stats(self):
        stats = {'members': ['test_members']}
        lbs = [self._sample_in_loadbalancer(), self._sample_in_loadbalancer()]
        with contextlib.nested(
            mock.patch.object(self.driver, 'get_stats', return_value=stats),
            mock.patch.object(self.plugin_mock.db, 'get_loadbalancer',
                              side_effect=lbs),
            mock.patch.object(self.plugin_mock.db,
                              'update_loadbalancer_stats'),
            mock.patch.object(self.driver, '_set_member_status'),
            mock.patch.object(self.driver, 'load_balancer')
        ) as (gs, glb, uls, sms, lb_man):
            self.driver.deployed_loadbalancer_ids = [lbs[0].id, lbs[1].id]
            self.driver._collect_and_store_stats()

            call1 = mock.call(lbs[0])
            call2 = mock.call(lbs[1])
            gs.assert_has_calls([call1, call2])
            self.assertEqual(2, gs.call_count)

            call1 = mock.call(self.driver.admin_ctx, lbs[0].id)
            call2 = mock.call(self.driver.admin_ctx, lbs[1].id)
            glb.assert_has_calls([call1, call2])
            self.assertEqual(2, glb.call_count)

            call1 = mock.call(self.driver.admin_ctx, lbs[0].id, stats)
            call2 = mock.call(self.driver.admin_ctx, lbs[1].id, stats)
            uls.assert_has_calls([call1, call2])
            self.assertEqual(2, uls.call_count)

            call1 = mock.call(self.driver.admin_ctx, lbs[0], stats['members'])
            call2 = mock.call(self.driver.admin_ctx, lbs[1], stats['members'])
            sms.assert_has_calls([call1, call2])
            self.assertEqual(2, sms.call_count)

    def test_collect_and_store_stats_no_members(self):
        stats = {}
        lbs = [self._sample_in_loadbalancer(), self._sample_in_loadbalancer()]
        with contextlib.nested(
            mock.patch.object(self.driver, 'get_stats', return_value=stats),
            mock.patch.object(self.plugin_mock.db, 'get_loadbalancer',
                              side_effect=lbs),
            mock.patch.object(self.plugin_mock.db,
                              'update_loadbalancer_stats'),
            mock.patch.object(self.driver, '_set_member_status'),
            mock.patch.object(self.driver, 'load_balancer')
        ) as (gs, glb, uls, sms, lb_man):
            self.driver.deployed_loadbalancer_ids = [lbs[0].id, lbs[1].id]
            self.driver._collect_and_store_stats()

            call1 = mock.call(lbs[0])
            call2 = mock.call(lbs[1])
            gs.assert_has_calls([call1, call2])
            self.assertEqual(2, gs.call_count)

            call1 = mock.call(self.driver.admin_ctx, lbs[0].id)
            call2 = mock.call(self.driver.admin_ctx, lbs[1].id)
            glb.assert_has_calls([call1, call2])
            self.assertEqual(2, glb.call_count)

            call1 = mock.call(self.driver.admin_ctx, lbs[0].id, stats)
            call2 = mock.call(self.driver.admin_ctx, lbs[1].id, stats)
            uls.assert_has_calls([call1, call2])
            self.assertEqual(2, uls.call_count)

            self.assertFalse(sms.called)

    def test_get_members(self):
        members = [data_models.Member(id='1'), data_models.Member(id='2')]
        pool = data_models.Pool(members=members)
        listener = data_models.Listener(default_pool=pool)
        lb = data_models.LoadBalancer(listeners=[listener])
        ret_members = [member for member in self.driver._get_members(lb)]
        self.assertEqual(len(members), len(ret_members))
        self.assertIn(members[0], ret_members)
        self.assertIn(members[1], ret_members)

    def test_set_member_status(self):
        members = [data_models.Member(id='1'), data_models.Member(id='2')]
        pool = data_models.Pool(members=members)
        listener = data_models.Listener(default_pool=pool)
        lb = data_models.LoadBalancer(listeners=[listener])
        self.driver.member.model_class = models.MemberV2
        member_stats = {members[0].id: {'status': constants.ACTIVE},
                        members[1].id: {'status': constants.ERROR}}
        with mock.patch.object(self.driver.plugin.db, 'update_status') as us:
            self.driver._set_member_status(self.context_mock, lb, member_stats)
            call1 = mock.call(self.context_mock, models.MemberV2,
                              members[0].id, operating_status=lb_const.ONLINE)
            call2 = mock.call(self.context_mock, models.MemberV2,
                              members[1].id, operating_status=lb_const.OFFLINE)
            us.assert_has_calls([call1, call2])

    def test_remove_config_directory(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_get_state_file_path',
                              return_value='/var/lbaas/id'),
            mock.patch('os.path.dirname', return_value='/var/lbaas'),
            mock.patch('os.path.isdir'),
            mock.patch('shutil.rmtree')
        ) as (gsp, dirname, isdir, rmtree):
            self.driver._remove_config_directory(
                self._sample_in_loadbalancer().id)
            gsp.assert_called_once_with(self._sample_in_loadbalancer().id, '')
            dirname.assert_called_once_with(gsp.return_value)
            isdir.assert_called_once_with(dirname.return_value)
            rmtree.assert_called_once_with(dirname.return_value)

    def test_cleanup_namespace(self):
        with contextlib.nested(
            mock.patch.object(sync_driver, 'get_ns_name',
                              return_value='ns-001'),
            mock.patch('neutron.agent.linux.ip_lib.device_exists'),
            mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
            mock.patch.object(self.driver, 'vif_driver')
        ) as (ns_name, device_exists, ip_wrap, vif_driver):
            device = mock.Mock()
            device.name = 'port_device'
            ip_wrap.return_value.get_devices.return_value = [device]
            device_exists.return_value = True
            self.driver._cleanup_namespace(self._sample_in_loadbalancer().id)
            device_exists.assert_called_once_with(device.name)
            vif_driver.unplug.assert_any_call(
                device.name, namespace=ns_name.return_value)
            self.assertEqual(1, vif_driver.unplug.call_count)

    def test_kill_processes(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_get_state_file_path',
                              return_value='/test/path'),
            mock.patch.object(namespace_driver, 'kill_pids_in_file')
        ) as (gsp, kpif):
            lb_id = self._sample_in_loadbalancer().id
            self.driver._kill_processes(lb_id)
            gsp.assert_called_once_with(lb_id, 'haproxy.pid')
            kpif.assert_called_once_with('/test/path')

    def test_unplug_vip_port(self):
        with contextlib.nested(
            mock.patch.object(sync_driver, 'get_ns_name',
                              return_value='ns-001'),
            mock.patch.object(self.driver, '_unplug')
        ) as (gnn, unplug):
            self.driver._unplug_vip_port(self._sample_in_loadbalancer())
            gnn.assert_called_once_with(self._sample_in_loadbalancer().id)
            unplug.assert_called_once_with(
                'ns-001', self._sample_in_loadbalancer().vip_port_id)

    def test_delete_instance_from_system(self):
        lbid = self._sample_in_loadbalancer().id
        self.driver.deployed_loadbalancer_ids.add(lbid)
        with contextlib.nested(
            mock.patch.object(self.driver, '_kill_processes'),
            mock.patch.object(self.driver, '_cleanup_namespace'),
            mock.patch.object(self.driver, '_remove_config_directory')
        ) as (kp, cn, rcd):
            self.driver._delete_instance_from_system(lbid)
            kp.assert_called_once_with(lbid)
            cn.assert_called_once_with(lbid)
            rcd.assert_called_once_with(lbid)

    def test_periodic_task(self):
        with mock.patch.object(self.driver, '_collect_and_store_stats') as pt:
            self.driver.periodic_tasks()
            pt.assert_called_once_with()

    def test_create_instance(self):
        with mock.patch.object(self.driver, '_plug') as plug:
            with mock.patch.object(self.driver, '_spawn') as spawn:
                with mock.patch.object(
                        sync_driver, 'get_ns_name') as ns_name:
                    self.driver.create_instance(self.context_mock,
                                                self._sample_in_loadbalancer())
                    ns_name.assert_called_once_with(
                        self._sample_in_loadbalancer().id)
                    plug.assert_called_once_with(
                        self.context_mock,
                        sync_driver.get_ns_name('test-001'),
                        self._sample_in_loadbalancer().vip_port)
                    spawn.assert_called_once_with(
                        self._sample_in_loadbalancer())

    def test_update_instance(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_get_state_file_path'),
            mock.patch.object(self.driver, '_spawn'),
            mock.patch.object(six.moves.builtins, 'open')
        ) as (gsp, spawn, mock_open):
            mock_open.return_value = ['5']

            self.driver.update_instance(self._sample_in_loadbalancer())

            mock_open.assert_called_once_with(gsp.return_value, 'r')
            spawn.assert_called_once_with(
                self._sample_in_loadbalancer(), ['-sf', '5'])

    def test_delete_instance(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_kill_processes'),
            mock.patch.object(self.driver, '_unplug_vip_port'),
            mock.patch.object(self.driver, '_remove_config_directory')
        ) as (kp, unplug_vip, rcd):
            self.driver.delete_instance(self._sample_in_loadbalancer())
            kp.assert_called_once_with(self._sample_in_loadbalancer().id)
            unplug_vip.assert_called_once_with(self._sample_in_loadbalancer())
            rcd.assert_called_once_with(self._sample_in_loadbalancer().id)

    def test_delete_instance_with_ns_cleanup(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_kill_processes'),
            mock.patch.object(self.driver, '_unplug_vip_port'),
            mock.patch.object(self.driver, '_cleanup_namespace'),
            mock.patch.object(self.driver, '_remove_config_directory')
        ) as (kp, unplug_vip, cn, rcd):
            self.driver.delete_instance(self._sample_in_loadbalancer(),
                                        cleanup_namespace=True)
            kp.assert_called_once_with(self._sample_in_loadbalancer().id)
            unplug_vip.assert_called_once_with(self._sample_in_loadbalancer())
            cn.assert_called_once_with(self._sample_in_loadbalancer().id)
            rcd.assert_called_once_with(self._sample_in_loadbalancer().id)

    def test_exists(self):
        with contextlib.nested(
            mock.patch.object(self.driver, '_get_state_file_path'),
            mock.patch('neutron.agent.linux.ip_lib.IPWrapper'),
            mock.patch('socket.socket'),
            mock.patch('os.path.exists'),
        ) as (gsp, ip_wrap, socket, path_exists):
            gsp.side_effect = lambda x, y, z: '/pool/' + y

            ip_wrap.return_value.netns.exists.return_value = True
            path_exists.return_value = True

            self.driver.exists(self._sample_in_loadbalancer())
            lbns = ''.join(
                [sync_driver.NS_PREFIX,
                 self._sample_in_loadbalancer().id])
            ip_wrap.assert_has_calls([
                mock.call(),
                mock.call().netns.exists(lbns)
            ])

            self.assertTrue(
                self.driver.exists(self._sample_in_loadbalancer()))

    def test_get_stats(self):
        raw_stats = ('# pxname,svname,qcur,qmax,scur,smax,slim,stot,bin,bout,'
                     'dreq,dresp,ereq,econ,eresp,wretr,wredis,status,weight,'
                     'act,bck,chkfail,chkdown,lastchg,downtime,qlimit,pid,iid,'
                     'sid,throttle,lbtot,tracked,type,rate,rate_lim,rate_max,'
                     'check_status,check_code,check_duration,hrsp_1xx,'
                     'hrsp_2xx,hrsp_3xx,hrsp_4xx,hrsp_5xx,hrsp_other,hanafail,'
                     'req_rate,req_rate_max,req_tot,cli_abrt,srv_abrt,\n'
                     '8e271901-69ed-403e-a59b-f53cf77ef208,BACKEND,1,2,3,4,0,'
                     '10,7764,2365,0,0,,0,0,0,0,UP,1,1,0,,0,103780,0,,1,2,0,,0'
                     ',,1,0,,0,,,,0,0,0,0,0,0,,,,,0,0,\n\n'
                     'a557019b-dc07-4688-9af4-f5cf02bb6d4b,'
                     '32a6c2a3-420a-44c3-955d-86bd2fc6871e,0,0,0,1,,7,1120,'
                     '224,,0,,0,0,0,0,UP,1,1,0,0,1,2623,303,,1,2,1,,7,,2,0,,'
                     '1,L7OK,200,98,0,7,0,0,0,0,0,,,,0,0,\n'
                     'a557019b-dc07-4688-9af4-f5cf02bb6d4b,'
                     'd9aea044-8867-4e80-9875-16fb808fa0f9,0,0,0,2,,12,0,0,,'
                     '0,,0,0,8,4,DOWN,1,1,0,9,2,308,675,,1,2,2,,4,,2,0,,2,'
                     'L4CON,,2999,0,0,0,0,0,0,0,,,,0,0,\n')
        raw_stats_empty = ('# pxname,svname,qcur,qmax,scur,smax,slim,stot,bin,'
                           'bout,dreq,dresp,ereq,econ,eresp,wretr,wredis,'
                           'status,weight,act,bck,chkfail,chkdown,lastchg,'
                           'downtime,qlimit,pid,iid,sid,throttle,lbtot,'
                           'tracked,type,rate,rate_lim,rate_max,check_status,'
                           'check_code,check_duration,hrsp_1xx,hrsp_2xx,'
                           'hrsp_3xx,hrsp_4xx,hrsp_5xx,hrsp_other,hanafail,'
                           'req_rate,req_rate_max,req_tot,cli_abrt,srv_abrt,'
                           '\n')
        with contextlib.nested(
                mock.patch.object(self.driver, '_get_state_file_path'),
                mock.patch('socket.socket'),
                mock.patch('os.path.exists'),
        ) as (gsp, socket, path_exists):
            gsp.side_effect = lambda x, y, z: '/lbns/' + y
            path_exists.return_value = True
            socket.return_value = socket
            socket.recv.return_value = raw_stats

            exp_stats = {'connection_errors': '0',
                         'active_connections': '3',
                         'current_sessions': '3',
                         'bytes_in': '7764',
                         'max_connections': '4',
                         'max_sessions': '4',
                         'bytes_out': '2365',
                         'response_errors': '0',
                         'total_sessions': '10',
                         'total_connections': '10',
                         'members': {
                             '32a6c2a3-420a-44c3-955d-86bd2fc6871e': {
                                 'status': 'ACTIVE',
                                 'health': 'L7OK',
                                 'failed_checks': '0'
                             },
                             'd9aea044-8867-4e80-9875-16fb808fa0f9': {
                                 'status': 'INACTIVE',
                                 'health': 'L4CON',
                                 'failed_checks': '9'
                             }
                         }
                         }
            stats = self.driver.get_stats(self._sample_in_loadbalancer())
            self.assertEqual(exp_stats, stats)

            socket.recv.return_value = raw_stats_empty
            self.assertEqual({'members': {}}, self.driver.get_stats(
                self._sample_in_loadbalancer()))

            path_exists.return_value = False
            socket.reset_mock()
            self.assertEqual({}, self.driver.get_stats(
                self._sample_in_loadbalancer()))
            self.assertFalse(socket.called)

    def test_kill_pids_in_file(self):
        with contextlib.nested(
            mock.patch('os.path.exists'),
            mock.patch.object(six.moves.builtins, 'open'),
            mock.patch('neutron.agent.linux.utils.execute'),
            mock.patch.object(namespace_driver.LOG, 'exception'),
        ) as (path_exists, mock_open, mock_execute, mock_log):
            file_mock = mock.MagicMock()
            mock_open.return_value = file_mock
            file_mock.__enter__.return_value = file_mock
            file_mock.__iter__.return_value = iter(['123'])

            path_exists.return_value = False
            namespace_driver.kill_pids_in_file('test_path')
            path_exists.assert_called_once_with('test_path')
            self.assertFalse(mock_open.called)
            self.assertFalse(mock_execute.called)

            path_exists.return_value = True
            mock_execute.side_effect = RuntimeError
            namespace_driver.kill_pids_in_file('test_path')
            self.assertTrue(mock_log.called)
            mock_execute.assert_called_once_with(
                ['kill', '-9', '123'], run_as_root=True)

    # TODO(ptoohill) put samples in reusable location
    def _sample_in_loadbalancer(self):
        in_lb = collections.namedtuple(
            'loadbalancer', 'id, name, vip_address, vip_port_id,'
                            'protocol, vip_port, '
                            'listeners')
        return in_lb(
            id='sample_loadbalancer_id_1',
            name='test-lb',
            vip_address='10.0.0.2',
            vip_port_id='vip_port_id_1',
            protocol='HTTP',
            vip_port=self._sample_in_vip_port(),
            listeners=[self._sample_in_listener()]
        )

    def _sample_in_vip_port(self):
        vip_port = collections.namedtuple('vip_port', 'id, network_id,'
                                                      'mac_address, fixed_ips')
        ip_address = collections.namedtuple('fixed_ips', 'ip_address, subnet')
        subnet = collections.namedtuple('subnet', 'cidr, gateway_ip,')
        in_subnet = subnet(cidr='10.0.0.0/24', gateway_ip='10.0.0.1')
        in_address = ip_address(ip_address='10.0.0.2', subnet=in_subnet)
        return vip_port(id='vip_port_id_1', network_id='nw_id_1',
                        mac_address='mac_address_1', fixed_ips=[in_address])

    def _sample_in_listener(self):
        in_listener = collections.namedtuple(
            'listener', 'id, protocol_port, protocol, default_pool, '
                        'connection_limit')
        return in_listener(
            id='sample_listener_id_1',
            protocol_port='80',
            protocol='HTTP',
            default_pool=self._sample_in_pool(),
            connection_limit='98'
        )

    def _sample_in_pool(self):
        in_pool = collections.namedtuple(
            'pool', 'id, protocol, lb_algorithm, members, health_monitor,'
                    'session_persistence, admin_state_up, status')
        return in_pool(
            id='sample_pool_id_1',
            protocol='HTTP',
            lb_algorithm='ROUND_ROBIN',
            members=[self._sample_in_member()],
            health_monitor=self._sample_in_health_monitor(),
            session_persistence=self._sample_in_session_persistence(),
            admin_state_up='true',
            status='ACTIVE')

    def _sample_in_member(self):
        in_member = collections.namedtuple('member',
                                           'id, address, protocol_port, '
                                           'weight, subnet_id, '
                                           'admin_state_up, status')
        return in_member(
            id='sample_member_id_1',
            address='10.0.0.99',
            protocol_port=82,
            weight=13,
            subnet_id='10.0.0.1/24',
            admin_state_up='true',
            status='ACTIVE')

    def _sample_in_session_persistence(self):
        spersistence = collections.namedtuple('SessionPersistence',
                                              'type, cookie_name')
        return spersistence(type='HTTP_COOKIE',
                            cookie_name='HTTP_COOKIE')

    def _sample_in_health_monitor(self):
        monitor = collections.namedtuple(
            'monitor', 'id, type, delay, timeout, max_retries, http_method, '
                       'url_path, expected_codes, admin_state_up')

        return monitor(id='sample_monitor_id_1', type='HTTP', delay='30',
                       timeout='31', max_retries='3', http_method='GET',
                       url_path='/index.html', expected_codes='500, 405, 404',
                       admin_state_up='true')


class BaseTestManager(base.BaseTestCase):

    def setUp(self):
        super(BaseTestManager, self).setUp()
        self.driver = mock.Mock()
        self.context = mock.Mock()
        self.load_balancer = sync_driver.LoadBalancerManager(
            self.driver)
        self.listener = sync_driver.ListenerManager(self.driver)
        self.pool = sync_driver.PoolManager(self.driver)
        self.member = sync_driver.MemberManager(self.driver)
        self.health_monitor = sync_driver.HealthMonitorManager(
            self.driver)

    def _create_mock_models(self):
        member = data_models.Member(id='1', pool=None,
                                    provisioning_status=constants.ACTIVE,
                                    operating_status=lb_const.ONLINE)
        monitor = data_models.HealthMonitor(id='1', pool=None)
        pool = data_models.Pool(id='1', listener=None, members=[member],
                                provisioning_status=constants.ACTIVE,
                                operating_status=lb_const.ONLINE,
                                healthmonitor=monitor,
                                healthmonitor_id=monitor.id)
        monitor.pool = pool
        member.pool = pool
        listener = data_models.Listener(id='1', loadbalancer=None,
                                        provisioning_status=constants.ACTIVE,
                                        operating_status=lb_const.ONLINE,
                                        default_pool=pool,
                                        default_pool_id=pool.id)
        pool.listener = listener
        loadbalancer = data_models.LoadBalancer(
            id='1', listeners=[listener], provisioning_status=constants.ACTIVE,
            operating_status=lb_const.ONLINE)
        listener.loadbalancer = loadbalancer
        return loadbalancer, listener, pool, member, monitor


class TestLoadBalancerManager(BaseTestManager):

    def test_refresh_update(self):
        (loadbalancer, listener,
         pool, member, monitor) = self._create_mock_models()
        with contextlib.nested(
                mock.patch.object(self.load_balancer, 'deployable'),
                mock.patch.object(self.driver, 'exists'),
                mock.patch.object(self.driver, 'update_instance'),
                mock.patch.object(self.driver, 'create_instance')
        ) as (dep, exists, up_instance, create_instance):
            exists.return_value = True
            dep.return_value = True

            self.load_balancer.refresh(self.context, loadbalancer)
            up_instance.assert_called_once_with(loadbalancer)
            self.assertFalse(create_instance.called)
            self.assertTrue(dep.called)

    def test_refresh_create(self):
        (loadbalancer, listener,
         pool, member, monitor) = self._create_mock_models()
        with contextlib.nested(
                mock.patch.object(self.load_balancer, 'deployable'),
                mock.patch.object(self.driver, 'exists'),
                mock.patch.object(self.driver, 'update_instance'),
                mock.patch.object(self.driver, 'create_instance'),
        ) as (dep, de, up_instance, create_instance):
            de.return_value = False
            dep.return_value = True
            self.load_balancer.refresh(self.context, loadbalancer)
            create_instance.assert_called_once_with(self.context, loadbalancer)
            self.assertFalse(up_instance.called)
            self.assertTrue(dep.called)

    def test_refresh_non_deployable(self):
        (loadbalancer, listener,
         pool, member, monitor) = self._create_mock_models()
        with contextlib.nested(
                mock.patch.object(self.load_balancer, 'deployable'),
                mock.patch.object(self.driver, 'exists'),
                mock.patch.object(self.driver, 'update_instance'),
                mock.patch.object(self.driver, 'create_instance'),
        ) as (dep, de, up_instance, create_instance):
            de.return_value = True
            dep.return_value = False
            self.load_balancer.refresh(self.context, loadbalancer)
            self.assertFalse(up_instance.called)
            self.assertFalse(create_instance.called)
            self.assertTrue(dep.called)

    def test_delete(self):
        loadbalancer = self._create_mock_models()[0]
        with mock.patch.object(self.driver, 'delete_instance') as del_instance:
            with mock.patch.object(self.load_balancer,
                                   'successful_completion') as succ:
                self.load_balancer.delete(self.context, loadbalancer)
                del_instance.assert_called_once_with(loadbalancer)
                succ.assert_called_once_with(self.context, loadbalancer,
                                             delete=True)

    def test_create_no_listeners(self):
        loadbalancer = self._create_mock_models()[0]
        loadbalancer.listeners = []
        with mock.patch.object(self.load_balancer,
                               'successful_completion') as successful:
            with mock.patch.object(self.load_balancer, 'refresh') as refresh:
                self.load_balancer.create(self.context, loadbalancer)
                successful.assert_called_once_with(self.context, loadbalancer)
                self.assertFalse(refresh.called)

    def test_create(self):
        loadbalancer = self._create_mock_models()[0]
        with mock.patch.object(self.load_balancer, 'refresh') as refresh:
            with mock.patch.object(self.load_balancer,
                                   'successful_completion') as successful:
                self.load_balancer.create(self.context, loadbalancer)
                refresh.assert_called_once_with(self.context,
                                                loadbalancer)
                successful.assert_called_once_with(self.context,
                                                   loadbalancer)

    def test_stats(self):
        loadbalancer = self._create_mock_models()[0]
        with mock.patch.object(self.driver, 'get_stats') as get_stats:
            self.load_balancer.stats(self.context, loadbalancer)
            get_stats.assert_called_once_with(loadbalancer)

    def test_update(self):
        loadbalancer = self._create_mock_models()[0]
        old_loadbalancer = self._create_mock_models()[0]
        with mock.patch.object(self.load_balancer, 'refresh') as refresh:
            with mock.patch.object(self.load_balancer,
                                   'successful_completion') as success:
                self.load_balancer.update(
                    self.context, old_loadbalancer, loadbalancer)
                refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, loadbalancer)

    def test_deployable_all_acceptable(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        listener.admin_state_up = True
        loadbalancer.admin_state_up = True

        self.assertTrue(self.load_balancer.deployable(loadbalancer))

    def test_deployable_lb_not_acceptable(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        listener.admin_state_up = True
        loadbalancer.admin_state_up = False

        self.assertFalse(self.load_balancer.deployable(loadbalancer))

        loadbalancer.admin_state_up = True
        loadbalancer.provisioning_status = constants.PENDING_DELETE
        self.assertFalse(self.load_balancer.deployable(loadbalancer))

    def test_deployable_listener_not_acceptable(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        listener.admin_state_up = False
        loadbalancer.admin_state_up = True
        self.assertFalse(self.load_balancer.deployable(loadbalancer))

        loadbalancer, listener, _, _, _ = self._create_mock_models()
        listener.admin_state_up = True
        listener.provisioning_status = constants.ACTIVE
        self.assertFalse(self.load_balancer.deployable(loadbalancer))


class TestListenerManager(BaseTestManager):

    def test_remove_listener(self):
        loadbalancer = self._create_mock_models()[0]
        loadbalancer.listeners.append(data_models.Listener(id='2'))

        self.listener._remove_listener(loadbalancer, '1')
        self.assertEqual(1, len(loadbalancer.listeners))
        self.assertEqual('2', loadbalancer.listeners[0].id)

    def test_create(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.listener,
                                   'successful_completion') as success:
                self.listener.create(self.context, listener)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, listener)

    def test_fail_create(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.listener,
                                   'successful_completion') as success:
                with mock.patch.object(self.listener,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.listener.create(self.context, listener)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       listener.loadbalancer)
                    fail.assert_called_once_with(self.context, listener)
                    self.assertFalse(success.called)

    def test_delete_no_listeners_left(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        with contextlib.nested(
            mock.patch.object(self.driver.load_balancer, 'refresh'),
            mock.patch.object(self.driver, 'delete_instance'),
            mock.patch.object(self.listener, 'successful_completion')
        ) as (refresh_instance, del_instance, success):
            self.listener.delete(self.context, listener)
            self.assertFalse(
                refresh_instance.called,
                'Attempting to refresh device with no listeners')
            del_instance.assert_called_once_with(loadbalancer)
            success.assert_called_once_with(self.context, listener,
                                            delete=True)

    def test_delete_with_listeners_left(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        loadbalancer.listeners.append(data_models.Listener(id='2'))
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as refresh_instance:
            with mock.patch.object(self.driver,
                                   'delete_instance') as del_instance:
                with mock.patch.object(self.listener,
                                       'successful_completion') as success:
                    self.listener.delete(self.context, listener)
                    refresh_instance.assert_called_once_with(self.context,
                                                             loadbalancer)
                    self.assertFalse(
                        del_instance.called,
                        'delete_instance called with listeners attached')
                    success.assert_called_once_with(self.context, listener,
                                                    delete=True)

    def test_fail_delete(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        loadbalancer.listeners.append(data_models.Listener(id='2'))
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.listener,
                                   'successful_completion') as success:
                with mock.patch.object(self.listener,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.listener.delete(self.context, listener)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       listener.loadbalancer)
                    fail.assert_called_once_with(self.context, listener)
                    self.assertFalse(success.called)

    def test_update(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        old_listener = data_models.Listener(id=listener.id)
        old_listener.loadbalancer = loadbalancer
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.listener,
                                   'successful_completion') as success:
                self.listener.update(self.context, old_listener, listener)
                lb_refresh.assert_called_once_with(self.context,
                                                   listener.loadbalancer)
                success.assert_called_once_with(self.context, listener)

    def test_fail_update(self):
        loadbalancer, listener, _, _, _ = self._create_mock_models()
        old_listener = data_models.Listener(id=listener.id)
        old_listener.loadbalancer = loadbalancer
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.listener,
                                   'successful_completion') as success:
                with mock.patch.object(self.listener,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.listener.update(self.context, old_listener,
                                             listener)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       listener.loadbalancer)
                    fail.assert_called_once_with(self.context, listener)
                    self.assertFalse(success.called)


class TestPoolManager(BaseTestManager):

    def test_create(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                self.pool.create(self.context, pool)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, pool)

    def test_fail_create(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                with mock.patch.object(self.pool,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.pool.create(self.context, pool)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, pool)
                    self.assertFalse(success.called)

    def test_update(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        old_pool = data_models.Pool(id='2')
        old_pool.listener = listener
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                self.pool.update(self.context, old_pool, pool)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, pool)

    def test_fail_update(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        old_pool = data_models.Pool(id='2')
        old_pool.listener = listener
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                with mock.patch.object(self.pool,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.pool.update(self.context, old_pool, pool)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, pool)
                    self.assertFalse(success.called)

    def test_delete(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as refresh_instance:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                self.pool.delete(self.context, pool)
                refresh_instance.assert_called_once_with(self.context,
                                                         loadbalancer)
                self.assertIsNone(listener.default_pool)
                success.assert_called_once_with(self.context, pool,
                                                delete=True)

    def test_fail_delete(self):
        loadbalancer, listener, pool, _, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.pool,
                                   'successful_completion') as success:
                with mock.patch.object(self.pool,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.pool.delete(self.context, pool)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, pool)
                    self.assertFalse(success.called)


class TestMemberManager(BaseTestManager):

    def test_remove_member(self):
        _, _, pool, member, _ = self._create_mock_models()
        pool.members.append(data_models.Member(id='2'))
        self.member._remove_member(pool, '1')
        self.assertTrue(len(pool.members), 1)
        self.assertEqual('2', pool.members[0].id)

    def test_update(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        old_member = data_models.Member(id='2')
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.member,
                                   'successful_completion') as success:
                self.member.update(self.context, old_member, member)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, member)

    def test_fail_update(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        old_member = data_models.Member(id='2')
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.member,
                                   'successful_completion') as success:
                with mock.patch.object(self.member,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.member.update(self.context, old_member, member)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, member)
                    self.assertFalse(success.called)

    def test_create(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.member,
                                   'successful_completion') as success:
                self.member.create(self.context, member)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, member)

    def test_fail_create(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.member,
                                   'successful_completion') as success:
                with mock.patch.object(self.member,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.member.create(self.context, member)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, member)
                    self.assertFalse(success.called)

    def test_delete(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        with contextlib.nested(
            mock.patch.object(self.driver.load_balancer, 'refresh'),
            mock.patch.object(self.member, 'successful_completion')
        ) as (refresh, success):
            self.member.delete(self.context, member)
            self.assertEqual(0, len(pool.members))
            refresh.assert_called_once_with(self.context, loadbalancer)
            success.assert_called_once_with(self.context, member, delete=True)

    def test_fail_delete(self):
        loadbalancer, listener, pool, member, _ = self._create_mock_models()
        with contextlib.nested(
            mock.patch.object(self.driver.load_balancer, 'refresh'),
            mock.patch.object(self.member, 'successful_completion'),
            mock.patch.object(self.member, 'failed_completion')
        ) as (refresh, success, fail):
            refresh.side_effect = Exception()
            try:
                self.member.delete(self.context, member)
            except Exception:
                pass
            self.assertEqual(0, len(pool.members))
            refresh.assert_called_once_with(self.context, loadbalancer)
            fail.assert_called_once_with(self.context, member)
            self.assertFalse(success.called)


class TestHealthMonitorManager(BaseTestManager):

    def test_update(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        old_monitor = data_models.HealthMonitor(id=monitor.id, pool=pool)
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                self.health_monitor.update(self.context, old_monitor, monitor)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, monitor)

    def test_fail_update(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        old_monitor = data_models.HealthMonitor(id=monitor.id, pool=pool)
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                with mock.patch.object(self.health_monitor,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.health_monitor.update(self.context, old_monitor,
                                                   monitor)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, monitor)
                    self.assertFalse(success.called)

    def test_create(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                self.health_monitor.create(self.context, monitor)
                lb_refresh.assert_called_once_with(self.context, loadbalancer)
                success.assert_called_once_with(self.context, monitor)

    def test_fail_create(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as lb_refresh:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                with mock.patch.object(self.health_monitor,
                                       'failed_completion') as fail:
                    lb_refresh.side_effect = Exception()
                    try:
                        self.health_monitor.create(self.context, monitor)
                    except Exception:
                        pass
                    lb_refresh.assert_called_once_with(self.context,
                                                       loadbalancer)
                    fail.assert_called_once_with(self.context, monitor)
                    self.assertFalse(success.called)

    def test_delete(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as refresh_instance:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                self.health_monitor.delete(self.context, monitor)
                refresh_instance.assert_called_once_with(self.context,
                                                         loadbalancer)
                success.assert_called_once_with(self.context, monitor,
                                                delete=True)

    def test_fail_delete(self):
        loadbalancer, listener, pool, _, monitor = self._create_mock_models()
        with mock.patch.object(self.driver.load_balancer,
                               'refresh') as refresh_instance:
            with mock.patch.object(self.health_monitor,
                                   'successful_completion') as success:
                with mock.patch.object(self.health_monitor,
                                       'failed_completion') as fail:
                    refresh_instance.side_effect = Exception()
                    try:
                        self.health_monitor.delete(self.context, monitor)
                    except Exception:
                        pass
                    refresh_instance.assert_called_once_with(self.context,
                                                             loadbalancer)
                    fail.assert_called_once_with(self.context, monitor)
                    self.assertFalse(success.called)
