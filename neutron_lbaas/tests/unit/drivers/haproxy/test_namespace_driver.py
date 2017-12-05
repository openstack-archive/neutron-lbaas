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
import socket

import mock
from neutron.agent.linux import external_process
from neutron_lib import constants
from neutron_lib import exceptions

from neutron_lbaas.drivers.haproxy import namespace_driver
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests import base
from oslo_utils import fileutils


class TestHaproxyNSDriver(base.BaseTestCase):

    def setUp(self):
        super(TestHaproxyNSDriver, self).setUp()

        conf = mock.Mock()
        conf.haproxy.loadbalancer_state_path = '/the/path'
        conf.interface_driver = 'intdriver'
        conf.haproxy.user_group = 'test_group'
        conf.haproxy.send_gratuitous_arp = 3
        self.conf = conf
        self.rpc_mock = mock.Mock()
        self.ensure_tree = mock.patch.object(fileutils, 'ensure_tree').start()
        self._process_monitor = mock.Mock()
        with mock.patch(
                'neutron_lib.utils.runtime.load_class_by_alias_or_classname'):
            self.driver = namespace_driver.HaproxyNSDriver(
                conf,
                self.rpc_mock,
                self._process_monitor
            )
        self.vif_driver = mock.Mock()
        self.driver.vif_driver = self.vif_driver
        self._build_mock_data_models()

    def _build_mock_data_models(self):
        host_route = data_models.HostRoute(destination='0.0.0.0/0',
                                           nexthop='192.0.0.1')
        subnet = data_models.Subnet(cidr='10.0.0.1/24',
                                    gateway_ip='10.0.0.2',
                                    host_routes=[host_route])
        fixed_ip = data_models.IPAllocation(ip_address='10.0.0.1')
        setattr(fixed_ip, 'subnet', subnet)
        port = data_models.Port(id='port1', network_id='network1',
                                mac_address='12-34-56-78-9A-BC',
                                fixed_ips=[fixed_ip])
        self.lb = data_models.LoadBalancer(id='lb1', listeners=[],
                                           vip_port=port,
                                           vip_address='10.0.0.1')

    def test_get_name(self):
        self.assertEqual(namespace_driver.DRIVER_NAME, self.driver.get_name())

    @mock.patch('neutron.agent.linux.ip_lib.IPWrapper')
    @mock.patch('os.makedirs')
    @mock.patch('os.path.dirname')
    @mock.patch('os.path.isdir')
    @mock.patch('shutil.rmtree')
    def test_undeploy_instance(self, mock_shutil, mock_isdir, mock_dirname,
                               mock_makedirs, mock_ip_wrap):
        self.driver._get_state_file_path = mock.Mock(return_value='/path')
        self.driver._unplug = mock.Mock()
        mock_dirname.return_value = '/path/' + self.lb.id
        mock_isdir.return_value = False
        self.driver.undeploy_instance(self.lb.id)
        calls = [mock.call(self.lb.id, 'pid'), mock.call(self.lb.id, '')]
        self.driver._get_state_file_path.has_calls(calls)
        self.assertFalse(self.driver._unplug.called)
        self.assertFalse(mock_ip_wrap.called)
        mock_isdir.assert_called_once_with('/path/' + self.lb.id)
        self.assertFalse(mock_shutil.called)

        self.driver.deployed_loadbalancers[self.lb.id] = self.lb
        mock_isdir.return_value = True
        mock_isdir.reset_mock()
        mock_ns = mock_ip_wrap.return_value
        mock_ns.get_devices.return_value = [collections.namedtuple(
            'Device', ['name'])(name='test_device')]
        self.driver.undeploy_instance(self.lb.id, cleanup_namespace=True,
                                      delete_namespace=True)
        ns = namespace_driver.get_ns_name(self.lb.id)
        calls = [mock.call(self.lb.id, 'pid'), mock.call(self.lb.id, '')]
        self.driver._get_state_file_path.has_calls(calls)
        self.driver._unplug.assert_called_once_with(ns, self.lb.vip_port)
        ip_wrap_calls = [mock.call(namespace=ns), mock.call(namespace=ns)]
        mock_ip_wrap.has_calls(ip_wrap_calls)
        mock_ns.get_devices.assert_called_once_with(exclude_loopback=True)
        self.vif_driver.unplug.assert_called_once_with('test_device',
                                                       namespace=ns)
        mock_shutil.assert_called_once_with('/path/' + self.lb.id)
        mock_ns.garbage_collect_namespace.assert_called_once_with()

    @mock.patch('os.makedirs')
    @mock.patch('os.path.dirname')
    def test_undeploy_instance_unregister_usage(self, mock_dirname,
                                                mock_makedirs):
        self.driver._get_state_file_path = mock.Mock(return_value='/path')
        self.driver._unplug = mock.Mock()
        mock_dirname.return_value = '/path/' + self.lb.id
        with mock.patch.object(self._process_monitor,
                               'unregister') as mock_unregister:
            self.driver.undeploy_instance(self.lb.id)
            mock_unregister.assert_called_once_with(
                    uuid=self.lb.id, service_name='lbaas-ns-haproxy')

    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_remove_orphans(self, list_dir, exists):
        lb_ids = [self.lb.id]
        exists.return_value = False
        self.driver.remove_orphans(lb_ids)
        exists.assert_called_once_with(self.driver.state_path)
        self.assertFalse(list_dir.called)

        exists.reset_mock()
        exists.return_value = True
        list_dir.return_value = [self.lb.id, 'lb2']
        self.driver.exists = mock.Mock()
        self.driver.undeploy_instance = mock.Mock()
        self.driver.remove_orphans(lb_ids)
        exists.assert_called_once_with(self.driver.state_path)
        list_dir.assert_called_once_with(self.driver.state_path)
        self.driver.exists.assert_called_once_with('lb2')
        self.driver.undeploy_instance.assert_called_once_with(
            'lb2', cleanup_namespace=True)

    def test_get_stats(self):
        # Shamelessly stolen from v1 namespace driver tests.
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
        with mock.patch.object(self.driver, '_get_state_file_path') as gsp, \
                mock.patch('socket.socket') as mocket, \
                mock.patch('os.path.exists') as path_exists, \
                mock.patch.object(data_models.LoadBalancer, 'from_dict') \
                as lb_from_dict, \
                mock.patch.object(self.driver, '_is_active') as is_active:
            gsp.side_effect = lambda x, y, z: '/pool/' + y
            path_exists.return_value = True
            mocket.return_value = mocket
            mocket.recv.return_value = raw_stats.encode('utf-8')
            is_active.return_value = True

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
                                 'operating_status': 'ONLINE',
                                 'health': 'L7OK',
                                 'failed_checks': '0'
                             },
                             'd9aea044-8867-4e80-9875-16fb808fa0f9': {
                                 'operating_status': 'OFFLINE',
                                 'health': 'L4CON',
                                 'failed_checks': '9'
                             }
                         }
                         }
            stats = self.driver.get_stats(self.lb.id)
            self.assertEqual(exp_stats, stats)

            mocket.recv.return_value = raw_stats_empty.encode('utf-8')
            self.assertEqual({'members': {}},
                             self.driver.get_stats(self.lb.id))

            path_exists.return_value = False
            is_active.return_value = True
            listener = data_models.Listener(
                provisioning_status=constants.PENDING_CREATE,
                admin_state_up=True)
            self.lb.listeners.append(listener)
            lb_from_dict.return_value = \
                data_models.LoadBalancer.from_dict(self.lb)

            self.lb.listeners.append(listener)
            self.assertEqual({}, self.driver.get_stats(self.lb.id))

            path_exists.return_value = False
            mocket.reset_mock()
            is_active.return_value = False
            self.assertEqual({}, self.driver.get_stats(self.lb.id))
            self.assertFalse(mocket.called)

    def test_is_active(self):
        # test no listeners
        ret_val = self.driver._is_active(self.lb)
        self.assertFalse(ret_val)

        # test bad VIP status
        listener = data_models.Listener(
            provisioning_status=constants.PENDING_CREATE,
            admin_state_up=True)
        self.lb.listeners.append(listener)
        self.lb.vip_port.status = constants.DOWN
        ret_val = self.driver._is_active(self.lb)
        self.assertFalse(ret_val)
        self.lb.vip_port.status = constants.PENDING_CREATE
        self.lb.vip_port.admin_state_up = False
        ret_val = self.driver._is_active(self.lb)
        self.assertFalse(ret_val)

        # test bad LB status
        self.lb.vip_port.admin_state_up = True
        self.lb.operating_status = 'OFFLINE'
        ret_val = self.driver._is_active(self.lb)
        self.assertFalse(ret_val)

        # test everything good
        self.lb.operating_status = 'ONLINE'
        ret_val = self.driver._is_active(self.lb)
        self.assertTrue(ret_val)

    def test_deploy_instance(self):
        self.driver.deployable = mock.Mock(return_value=False)
        self.driver.exists = mock.Mock(return_value=True)
        self.driver.update = mock.Mock()
        self.driver.create = mock.Mock()

        def reset():
            self.driver.deployable.reset_mock()
            self.driver.exists.reset_mock()
            self.driver.update.reset_mock()
            self.driver.create.reset_mock()

        deployed = self.driver.deploy_instance(self.lb)
        self.assertFalse(deployed)
        self.assertFalse(self.driver.exists.called)
        self.assertFalse(self.driver.create.called)
        self.assertFalse(self.driver.update.called)

        reset()
        self.driver.deployable.return_value = True
        deployed = self.driver.deploy_instance(self.lb)
        self.assertTrue(deployed)
        self.driver.exists.assert_called_once_with(self.lb.id)
        self.driver.update.assert_called_once_with(self.lb)
        self.assertFalse(self.driver.create.called)

        reset()
        self.driver.exists.return_value = False
        deployed = self.driver.deploy_instance(self.lb)
        self.assertTrue(deployed)
        self.driver.exists.assert_called_once_with(self.lb.id)
        self.driver.create.assert_called_once_with(self.lb)
        self.assertFalse(self.driver.update.called)

    def test_update(self):
        self.driver._get_state_file_path = mock.Mock(return_value='/path')
        self.driver._spawn = mock.Mock()
        with mock.patch('six.moves.builtins.open') as m_open:
            file_mock = mock.MagicMock()
            m_open.return_value = file_mock
            file_mock.__enter__.return_value = file_mock
            file_mock.__iter__.return_value = iter(['123'])
            self.driver.update(self.lb)
            self.driver._spawn.assert_called_once_with(self.lb,
                                                       ['-sf', '123'])

    @mock.patch('socket.socket')
    @mock.patch('os.path.exists')
    @mock.patch('neutron.agent.linux.ip_lib.IPWrapper')
    def test_exists(self, ip_wrap, exists, mocket):
        socket_path = '/path/haproxy_stats.sock'
        mock_ns = ip_wrap.return_value
        mock_socket = mocket.return_value
        self.driver._get_state_file_path = mock.Mock(return_value=socket_path)
        mock_ns.netns.exists.return_value = False
        exists.return_value = False

        def reset():
            ip_wrap.reset_mock()
            self.driver._get_state_file_path.reset_mock()
            mock_ns.reset_mock()
            exists.reset_mock()
            mocket.reset_mock()
            mock_socket.reset_mock()

        ret_exists = self.driver.exists(self.lb.id)
        ip_wrap.assert_called_once_with()
        self.driver._get_state_file_path.assert_called_once_with(
            self.lb.id, 'haproxy_stats.sock', False)
        mock_ns.netns.exists.assert_called_once_with(
            namespace_driver.get_ns_name(self.lb.id))
        self.assertFalse(exists.called)
        self.assertFalse(mocket.called)
        self.assertFalse(mock_socket.connect.called)
        self.assertFalse(ret_exists)

        reset()
        mock_ns.netns.exists.return_value = True
        exists.return_value = False
        ret_exists = self.driver.exists(self.lb.id)
        ip_wrap.assert_called_once_with()
        self.driver._get_state_file_path.assert_called_once_with(
            self.lb.id, 'haproxy_stats.sock', False)
        mock_ns.netns.exists.assert_called_once_with(
            namespace_driver.get_ns_name(self.lb.id))
        exists.assert_called_once_with(socket_path)
        self.assertFalse(mocket.called)
        self.assertFalse(mock_socket.connect.called)
        self.assertFalse(ret_exists)

        reset()
        mock_ns.netns.exists.return_value = True
        exists.return_value = True
        ret_exists = self.driver.exists(self.lb.id)
        ip_wrap.assert_called_once_with()
        self.driver._get_state_file_path.assert_called_once_with(
            self.lb.id, 'haproxy_stats.sock', False)
        mock_ns.netns.exists.assert_called_once_with(
            namespace_driver.get_ns_name(self.lb.id))
        exists.assert_called_once_with(socket_path)
        mocket.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(socket_path)
        self.assertTrue(ret_exists)

    def test_create(self):
        self.driver._plug = mock.Mock()
        self.driver._spawn = mock.Mock()
        self.driver.create(self.lb)
        self.driver._plug.assert_called_once_with(
            namespace_driver.get_ns_name(self.lb.id),
            self.lb.vip_port, self.lb.vip_address)
        self.driver._spawn.assert_called_once_with(self.lb)

    def test_deployable(self):
        # test None
        ret_val = self.driver.deployable(None)
        self.assertFalse(ret_val)

        # test no listeners
        ret_val = self.driver.deployable(self.lb)
        self.assertFalse(ret_val)

        # test no acceptable listeners
        listener = data_models.Listener(
            provisioning_status=constants.PENDING_DELETE,
            admin_state_up=True)
        self.lb.listeners.append(listener)
        ret_val = self.driver.deployable(self.lb)
        self.assertFalse(ret_val)
        listener.provisioning_status = constants.PENDING_CREATE
        listener.admin_state_up = False
        ret_val = self.driver.deployable(self.lb)
        self.assertFalse(ret_val)

        # test bad lb status
        listener.admin_state_up = True
        self.lb.provisioning_status = constants.PENDING_DELETE
        self.lb.admin_state_up = True
        ret_val = self.driver.deployable(self.lb)
        self.assertFalse(ret_val)
        self.lb.provisioning_status = constants.PENDING_UPDATE
        self.lb.admin_state_up = False
        ret_val = self.driver.deployable(self.lb)
        self.assertFalse(ret_val)

        # test everything good
        self.lb.admin_state_up = True
        ret_val = self.driver.deployable(self.lb)
        self.assertTrue(ret_val)

    @mock.patch('oslo_utils.fileutils.ensure_tree')
    def test_get_state_file_path(self, ensure_tree):
        path = self.driver._get_state_file_path(self.lb.id, 'conf',
                                                ensure_state_dir=False)
        self.assertEqual('/the/path/v2/lb1/conf', path)
        self.assertFalse(ensure_tree.called)
        path = self.driver._get_state_file_path(self.lb.id, 'conf')
        self.assertEqual('/the/path/v2/lb1/conf', path)
        self.assertTrue(ensure_tree.called)

    @mock.patch('neutron.agent.linux.ip_lib.device_exists')
    @mock.patch('neutron.agent.linux.ip_lib.IPWrapper')
    def test_plug(self, ip_wrap, device_exists):
        device_exists.return_value = True
        interface_name = 'tap-d4nc3'
        self.vif_driver.get_device_name.return_value = interface_name
        self.assertRaises(exceptions.PreexistingDeviceFailure,
                          self.driver._plug, 'ns1', self.lb.vip_port,
                          self.lb.vip_address, reuse_existing=False)
        device_exists.assert_called_once_with(interface_name,
                                              namespace='ns1')
        self.rpc_mock.plug_vip_port.assert_called_once_with(
            self.lb.vip_port.id)

        device_exists.reset_mock()
        self.rpc_mock.plug_vip_port.reset_mock()
        mock_ns = ip_wrap.return_value
        self.driver._plug('ns1', self.lb.vip_port, self.lb.vip_address)
        self.rpc_mock.plug_vip_port.assert_called_once_with(
            self.lb.vip_port.id)
        device_exists.assert_called_once_with(interface_name,
                                              namespace='ns1')
        self.assertFalse(self.vif_driver.plug.called)
        expected_cidrs = ['10.0.0.1/24']
        self.vif_driver.init_l3.assert_called_once_with(
            interface_name, expected_cidrs, namespace='ns1')
        calls = [mock.call(['route', 'add', 'default', 'gw', '192.0.0.1'],
                           check_exit_code=False),
                 mock.call(['arping', '-U', '-I', interface_name,
                            '-c', 3, '10.0.0.1'],
                           check_exit_code=False)]
        mock_ns.netns.execute.has_calls(calls)
        self.assertEqual(2, mock_ns.netns.execute.call_count)

    def test_unplug(self):
        interface_name = 'tap-d4nc3'
        self.vif_driver.get_device_name.return_value = interface_name
        self.driver._unplug('ns1', self.lb.vip_port)
        self.rpc_mock.unplug_vip_port.assert_called_once_with(
            self.lb.vip_port.id)
        self.vif_driver.get_device_name.assert_called_once_with(
            self.lb.vip_port)
        self.vif_driver.unplug.assert_called_once_with(interface_name,
                                                       namespace='ns1')

    @mock.patch('oslo_utils.fileutils.ensure_tree')
    @mock.patch('neutron_lbaas.drivers.haproxy.jinja_cfg.save_config')
    @mock.patch('neutron.agent.linux.ip_lib.IPWrapper')
    def test_spawn(self, ip_wrap, jinja_save, ensure_tree):
        mock_ns = ip_wrap.return_value
        self.driver._spawn(self.lb)
        conf_dir = self.driver.state_path + '/' + self.lb.id + '/%s'
        jinja_save.assert_called_once_with(
            conf_dir % 'haproxy.conf',
            self.lb,
            conf_dir % 'haproxy_stats.sock',
            'test_group',
            conf_dir % '')
        ip_wrap.assert_called_once_with(
            namespace=namespace_driver.get_ns_name(self.lb.id))
        mock_ns.netns.execute.assert_called_once_with(
            ['haproxy', '-f', conf_dir % 'haproxy.conf', '-p',
             conf_dir % 'haproxy.pid'], addl_env=None, run_as_root=True)
        self.assertIn(self.lb.id, self.driver.deployed_loadbalancers)
        self.assertEqual(self.lb,
                         self.driver.deployed_loadbalancers[self.lb.id])

    @mock.patch('oslo_utils.fileutils.ensure_tree')
    @mock.patch('neutron_lbaas.drivers.haproxy.jinja_cfg.save_config')
    def test_spawn_enable_usage(self, jinja_save, ensure_tree):
        with mock.patch.object(external_process.ProcessManager,
                               'enable') as mock_enable:
            self.driver._spawn(self.lb)
            mock_enable.assert_called_once_with()

    @mock.patch('oslo_utils.fileutils.ensure_tree')
    @mock.patch('neutron_lbaas.drivers.haproxy.jinja_cfg.save_config')
    def test_spawn_reload_cfg_usage(self, jinja_save, ensure_tree):
        with mock.patch.object(external_process.ProcessManager, 'active',
                               return_value=True):
            with mock.patch.object(external_process.ProcessManager,
                                   'reload_cfg') as mock_reload_cfg:
                extra_cmd_args = ['-sf', '123']
                self.driver._spawn(self.lb, extra_cmd_args=extra_cmd_args)
                mock_reload_cfg.assert_called_once_with()


class BaseTestManager(base.BaseTestCase):

    def setUp(self):
        super(BaseTestManager, self).setUp()
        self.driver = mock.Mock()
        self.lb_manager = namespace_driver.LoadBalancerManager(self.driver)
        self.listener_manager = namespace_driver.ListenerManager(self.driver)
        self.pool_manager = namespace_driver.PoolManager(self.driver)
        self.member_manager = namespace_driver.MemberManager(self.driver)
        self.hm_manager = namespace_driver.HealthMonitorManager(self.driver)
        self.refresh = self.driver.loadbalancer.refresh


class BaseTestLoadBalancerManager(BaseTestManager):

    def setUp(self):
        super(BaseTestLoadBalancerManager, self).setUp()
        self.in_lb = data_models.LoadBalancer(id='lb1', listeners=[])


class TestLoadBalancerManager(BaseTestLoadBalancerManager):

    @mock.patch.object(data_models.LoadBalancer, 'from_dict')
    def test_refresh(self, lb_from_dict):
        rpc_return = {'id': self.in_lb.id}
        self.driver.plugin_rpc.get_loadbalancer.return_value = rpc_return
        from_dict_return = data_models.LoadBalancer(id=self.in_lb.id)
        lb_from_dict.return_value = from_dict_return
        self.driver.deploy_instance.return_value = True
        self.driver.exists.return_value = True
        self.lb_manager.refresh(self.in_lb)
        self.driver.plugin_rpc.get_loadbalancer.assert_called_once_with(
            self.in_lb.id)
        lb_from_dict.assert_called_once_with(rpc_return)
        self.driver.deploy_instance.assert_called_once_with(from_dict_return)
        self.assertFalse(self.driver.exists.called)
        self.assertFalse(self.driver.undeploy_instance.called)

        self.driver.reset_mock()
        lb_from_dict.reset_mock()
        self.driver.deploy_instance.return_value = False
        self.driver.exists.return_value = False
        self.lb_manager.refresh(self.in_lb)
        self.driver.plugin_rpc.get_loadbalancer.assert_called_once_with(
            self.in_lb.id)
        lb_from_dict.assert_called_once_with(rpc_return)
        self.driver.deploy_instance.assert_called_once_with(from_dict_return)
        self.driver.exists.assert_called_once_with(self.in_lb.id)
        self.assertFalse(self.driver.undeploy_instance.called)

        self.driver.reset_mock()
        lb_from_dict.reset_mock()
        self.driver.deploy_instance.return_value = False
        self.driver.exists.return_value = True
        self.lb_manager.refresh(self.in_lb)
        self.driver.plugin_rpc.get_loadbalancer.assert_called_once_with(
            self.in_lb.id)
        lb_from_dict.assert_called_once_with(rpc_return)
        self.driver.deploy_instance.assert_called_once_with(from_dict_return)
        self.driver.exists.assert_called_once_with(from_dict_return.id)
        self.driver.undeploy_instance.assert_called_once_with(self.in_lb.id)

    def test_delete(self):
        self.driver.exists.return_value = False
        self.lb_manager.delete(self.in_lb)
        self.driver.exists.assert_called_once_with(self.in_lb.id)
        self.assertFalse(self.driver.undeploy_instance.called)

        self.driver.reset_mock()
        self.driver.exists.return_value = True
        self.lb_manager.delete(self.in_lb)
        self.driver.exists.assert_called_once_with(self.in_lb.id)
        self.driver.undeploy_instance.assert_called_once_with(
            self.in_lb.id, delete_namespace=True)

    def test_create(self):
        self.lb_manager.refresh = mock.Mock()
        self.lb_manager.create(self.in_lb)
        self.assertFalse(self.lb_manager.refresh.called)

        self.lb_manager.refresh.reset_mock()
        self.in_lb.listeners.append(data_models.Listener(id='listener1'))
        self.lb_manager.create(self.in_lb)
        self.lb_manager.refresh.assert_called_once_with(self.in_lb)

    def test_get_stats(self):
        self.driver.get_stats.return_value = {'members': {}}
        self.lb_manager.get_stats(self.in_lb.id)
        self.driver.get_stats.assert_called_once_with(self.in_lb.id)

    def test_update(self):
        old_lb = data_models.LoadBalancer(id='lb0')
        self.lb_manager.refresh = mock.Mock()
        self.lb_manager.update(old_lb, self.in_lb)
        self.lb_manager.refresh.assert_called_once_with(self.in_lb)


class BaseTestListenerManager(BaseTestLoadBalancerManager):

    def setUp(self):
        super(BaseTestListenerManager, self).setUp()
        self.in_listener = data_models.Listener(id='listener1')
        self.listener2 = data_models.Listener(id='listener2')
        self.in_listener.loadbalancer = self.in_lb
        self.listener2.loadbalancer = self.in_lb
        self.in_lb.listeners = [self.in_listener, self.listener2]
        self.refresh = self.driver.loadbalancer.refresh


class TestListenerManager(BaseTestListenerManager):

    def setUp(self):
        super(TestListenerManager, self).setUp()
        self.in_listener = data_models.Listener(id='listener1')
        self.listener2 = data_models.Listener(id='listener2')
        self.in_lb.listeners = [self.in_listener, self.listener2]
        self.in_listener.loadbalancer = self.in_lb
        self.listener2.loadbalancer = self.in_lb

    def test_remove_listener(self):
        self.listener_manager._remove_listener(self.in_lb, self.in_listener.id)
        self.assertEqual(1, len(self.in_lb.listeners))
        self.assertEqual(self.listener2.id, self.in_lb.listeners[0].id)

    def test_update(self):
        old_listener = data_models.Listener(id='listener1', name='bleh')
        self.listener_manager.update(old_listener, self.in_listener)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_create(self):
        self.listener_manager.create(self.in_listener)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_delete(self):
        self.listener_manager.delete(self.in_listener)
        self.refresh.assert_called_once_with(self.in_lb)
        self.assertFalse(self.driver.undeploy_instance.called)

        self.refresh.reset_mock()
        self.driver.reset_mock()
        self.listener_manager.delete(self.listener2)
        self.assertFalse(self.refresh.called)
        self.driver.undeploy_instance.assert_called_once_with(
            self.in_lb.id, delete_namespace=True)


class BaseTestPoolManager(BaseTestListenerManager):

    def setUp(self):
        super(BaseTestPoolManager, self).setUp()
        self.in_pool = data_models.Pool(id='pool1')
        self.in_listener.default_pool = self.in_pool
        self.in_pool.loadbalancer = self.in_lb
        self.in_pool.listeners = [self.in_listener]
        self.in_lb.pools = [self.in_pool]


class TestPoolManager(BaseTestPoolManager):

    def test_update(self):
        old_pool = data_models.Pool(id=self.in_pool.id, name='bleh')
        self.pool_manager.update(old_pool, self.in_pool)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_create(self):
        self.pool_manager.create(self.in_pool)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_delete(self):
        self.pool_manager.delete(self.in_pool)
        self.assertIsNone(self.in_listener.default_pool)
        self.refresh.assert_called_once_with(self.in_lb)


class BaseTestMemberManager(BaseTestPoolManager):

    def setUp(self):
        super(BaseTestMemberManager, self).setUp()
        self.in_member = data_models.Member(id='member1')
        self.member2 = data_models.Member(id='member2')
        self.in_pool.members = [self.in_member, self.member2]
        self.in_member.pool = self.in_pool
        self.member2.pool = self.in_pool


class TestMemberManager(BaseTestMemberManager):

    def test_remove_member(self):
        self.member_manager._remove_member(self.in_pool, self.in_member.id)
        self.assertEqual(1, len(self.in_pool.members))
        self.assertEqual(self.member2.id, self.in_pool.members[0].id)

    def test_update(self):
        old_member = data_models.Member(id=self.in_member.id,
                                        address='0.0.0.0')
        self.member_manager.update(old_member, self.in_member)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_create(self):
        self.member_manager.create(self.in_member)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_delete(self):
        self.member_manager.delete(self.in_member)
        self.refresh.assert_called_once_with(self.in_lb)


class BaseTestHealthMonitorManager(BaseTestPoolManager):

    def setUp(self):
        super(BaseTestHealthMonitorManager, self).setUp()
        self.in_hm = data_models.HealthMonitor(id='hm1')
        self.in_pool.healthmonitor = self.in_hm
        self.in_hm.pool = self.in_pool


class TestHealthMonitorManager(BaseTestHealthMonitorManager):

    def test_update(self):
        old_hm = data_models.HealthMonitor(id=self.in_hm.id, timeout=2)
        self.hm_manager.update(old_hm, self.in_hm)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_create(self):
        self.hm_manager.create(self.in_hm)
        self.refresh.assert_called_once_with(self.in_lb)

    def test_delete(self):
        self.hm_manager.delete(self.in_hm)
        self.assertIsNone(self.in_pool.healthmonitor)
        self.refresh.assert_called_once_with(self.in_lb)


class TestNamespaceDriverModule(base.BaseTestCase):

    def test_get_ns_name(self):
        ns_name = namespace_driver.get_ns_name('woohoo')
        self.assertEqual(namespace_driver.NS_PREFIX + 'woohoo', ns_name)
