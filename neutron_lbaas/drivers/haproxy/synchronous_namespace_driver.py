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

import os
import shutil
import socket

import netaddr
from neutron.agent.common import config
from neutron.agent.linux import interface
from neutron.agent.linux import ip_lib
from neutron.common import exceptions
from neutron.common import utils as n_utils
from neutron import context as ncontext
from neutron.extensions import portbindings
from neutron.plugins.common import constants
from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_service import service
from oslo_utils import excutils

from neutron_lbaas._i18n import _LE, _LW
from neutron_lbaas.drivers import driver_base
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer.agent import agent as lb_agent
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer.drivers.haproxy import jinja_cfg
from neutron_lbaas.services.loadbalancer.drivers.haproxy \
    import namespace_driver

LOG = logging.getLogger(__name__)
NS_PREFIX = 'nlbaas-'
STATS_TYPE_BACKEND_REQUEST = 2
STATS_TYPE_BACKEND_RESPONSE = '1'
STATS_TYPE_SERVER_REQUEST = 4
STATS_TYPE_SERVER_RESPONSE = '2'
# Do not want v1 instances to be in same directory as v2
STATE_PATH_V2_APPEND = 'v2'
DEFAULT_INTERFACE_DRIVER = 'neutron.agent.linux.interface.OVSInterfaceDriver'
cfg.CONF.register_opts(namespace_driver.OPTS, 'haproxy')
cfg.CONF.register_opts(lb_agent.OPTS, 'haproxy')
cfg.CONF.register_opts(interface.OPTS)
cfg.CONF.register_opts(config.INTERFACE_DRIVER_OPTS, 'haproxy')


def get_ns_name(namespace_id):
    return NS_PREFIX + namespace_id


class SimpleHaproxyStatsService(service.Service):

    def __init__(self, driver):
        super(SimpleHaproxyStatsService, self).__init__()
        self.driver = driver

    def start(self):
        super(SimpleHaproxyStatsService, self).start()
        self.tg.add_timer(self.driver.conf.haproxy.periodic_interval,
                          self.driver.periodic_tasks,
                          None,
                          None)


class HaproxyNSDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(HaproxyNSDriver, self).__init__(plugin)
        self.conf = cfg.CONF
        self.state_path = os.path.join(
            self.conf.haproxy.loadbalancer_state_path, STATE_PATH_V2_APPEND)
        if not self.conf.haproxy.interface_driver:
            self.conf.haproxy.interface_driver = DEFAULT_INTERFACE_DRIVER
        try:
            vif_driver_class = n_utils.load_class_by_alias_or_classname(
                'neutron.interface_drivers',
                self.conf.haproxy.interface_driver)

        except ImportError:
            with excutils.save_and_reraise_exception():
                msg = (_LE('Error importing interface driver: %s')
                       % self.conf.haproxy.interface_driver)
                LOG.exception(msg)
        self.vif_driver = vif_driver_class(self.conf)

        # instantiate managers here
        self.load_balancer = LoadBalancerManager(self)
        self.listener = ListenerManager(self)
        self.pool = PoolManager(self)
        self.member = MemberManager(self)
        self.health_monitor = HealthMonitorManager(self)

        self.admin_ctx = ncontext.get_admin_context()
        self.deployed_loadbalancer_ids = set()
        self._deploy_existing_instances()

        SimpleHaproxyStatsService(self).start()

    def _deploy_existing_instances(self):
        dirs = self._retrieve_deployed_instance_dirs()
        loadbalancers = self._retrieve_db_loadbalancers_from_dirs(dirs)
        loadbalancer_ids = [loadbalancer.id for loadbalancer in loadbalancers]
        self.deployed_loadbalancer_ids.update(loadbalancer_ids)
        for loadbalancer in loadbalancers:
            try:
                self.update_instance(loadbalancer)
            except RuntimeError:
                # do not stop anything this is a minor error
                LOG.warning(_LW("Existing load balancer %s could not be "
                                "deployed on the system."), loadbalancer.id)

    def _retrieve_deployed_instance_dirs(self):
        if not os.path.exists(self.state_path):
            os.makedirs(self.state_path)
        return [dir for dir in os.listdir(self.state_path)
                if os.path.isdir(os.path.join(self.state_path, dir))]

    def _retrieve_db_loadbalancers_from_dirs(self, dirs):
        loadbalancers = []
        for dir in dirs:
            try:
                db_lb = self.plugin.db.get_loadbalancer(self.admin_ctx, dir)
                loadbalancers.append(db_lb)
            except loadbalancerv2.EntityNotFound:
                # Doesn't exist in database so clean up
                self._delete_instance_from_system(dir)
                continue
        return loadbalancers

    def _plug_vip_port(self, context, port):
        port_dict = self.plugin.db._core_plugin.get_port(context, port.id)
        port_dict.update(self._build_port_dict())
        self.plugin.db._core_plugin.update_port(
            context,
            port.id,
            {'port': port_dict}
        )

    def _build_port_dict(self):
        return {'admin_state_up': True,
                portbindings.HOST_ID: self.conf.host}

    def _get_state_file_path(self, loadbalancer_id, kind,
                             ensure_state_dir=True):
        """Returns the file name for a given kind of config file."""
        confs_dir = os.path.abspath(os.path.normpath(self.state_path))
        conf_dir = os.path.join(confs_dir, loadbalancer_id)
        if ensure_state_dir:
            if not os.path.isdir(conf_dir):
                os.makedirs(conf_dir, 0o755)
        return os.path.join(conf_dir, kind)

    def _populate_subnets(self, context, port):
        for fixed_ip in port.fixed_ips:
            fixed_ip.subnet = self.plugin.db._core_plugin.get_subnet(
                context, fixed_ip.subnet_id)

    def _plug(self, context, namespace, port, reuse_existing=True):
        self._plug_vip_port(context, port)

        interface_name = self.vif_driver.get_device_name(port)

        if ip_lib.device_exists(interface_name, namespace):
            if not reuse_existing:
                raise exceptions.PreexistingDeviceFailure(
                    dev_name=interface_name
                )
        else:
            self.vif_driver.plug(
                port.network_id,
                port.id,
                interface_name,
                port.mac_address,
                namespace=namespace
            )

        self._populate_subnets(context, port)

        cidrs = [
            '%s/%s' % (ip.ip_address,
                       netaddr.IPNetwork(ip.subnet['cidr']).prefixlen)
            for ip in port.fixed_ips
        ]
        self.vif_driver.init_l3(interface_name, cidrs,
                                namespace=namespace)

        gw_ip = port.fixed_ips[0].subnet.get('gateway_ip')

        if not gw_ip:
            host_routes = port.fixed_ips[0].subnet.get('host_routes', [])
            for host_route in host_routes:
                if host_route['destination'] == "0.0.0.0/0":
                    gw_ip = host_route['nexthop']
                    break
        else:
            cmd = ['route', 'add', 'default', 'gw', gw_ip]
            ip_wrapper = ip_lib.IPWrapper(namespace=namespace)
            ip_wrapper.netns.execute(cmd, check_exit_code=False)
            # When delete and re-add the same vip, we need to
            # send gratuitous ARP to flush the ARP cache in the Router.
            gratuitous_arp = self.conf.haproxy.send_gratuitous_arp
            if gratuitous_arp > 0:
                for ip in port.fixed_ips:
                    cmd_arping = ['arping', '-U',
                                  '-I', interface_name,
                                  '-c', gratuitous_arp,
                                  ip.ip_address]
                    ip_wrapper.netns.execute(cmd_arping, check_exit_code=False)

    def _unplug(self, namespace, port_id):
        port_stub = {'id': port_id}
        interface_name = self.vif_driver.get_device_name(
            namespace_driver.Wrap(port_stub))
        self.vif_driver.unplug(interface_name, namespace=namespace)

    def _spawn(self, loadbalancer, extra_cmd_args=()):
        namespace = get_ns_name(loadbalancer.id)
        conf_path = self._get_state_file_path(loadbalancer.id, 'haproxy.conf')
        pid_path = self._get_state_file_path(loadbalancer.id,
                                             'haproxy.pid')
        sock_path = self._get_state_file_path(loadbalancer.id,
                                              'haproxy_stats.sock')
        user_group = self.conf.haproxy.user_group
        state_path = self._get_state_file_path(loadbalancer.id, '')

        jinja_cfg.save_config(conf_path, loadbalancer, sock_path, user_group,
                              state_path)
        cmd = ['haproxy', '-f', conf_path, '-p', pid_path]
        cmd.extend(extra_cmd_args)

        ns = ip_lib.IPWrapper(namespace=namespace)
        ns.netns.execute(cmd)

        # remember deployed loadbalancer id
        self.deployed_loadbalancer_ids.add(loadbalancer.id)

    def _get_backend_stats(self, parsed_stats):
        for stats in parsed_stats:
            if stats.get('type') == STATS_TYPE_BACKEND_RESPONSE:
                unified_stats = dict((k, stats.get(v, ''))
                                     for k, v in jinja_cfg.STATS_MAP.items())
                return unified_stats

        return {}

    def _get_servers_stats(self, parsed_stats):
        res = {}
        for stats in parsed_stats:
            if stats.get('type') == STATS_TYPE_SERVER_RESPONSE:
                res[stats['svname']] = {
                    lb_const.STATS_STATUS: (constants.INACTIVE
                                            if stats['status'] == 'DOWN'
                                            else constants.ACTIVE),
                    lb_const.STATS_HEALTH: stats['check_status'],
                    lb_const.STATS_FAILED_CHECKS: stats['chkfail']
                }
        return res

    def _get_stats_from_socket(self, socket_path, entity_type):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(socket_path)
            s.send('show stat -1 %s -1\n' % entity_type)
            raw_stats = ''
            chunk_size = 1024
            while True:
                chunk = s.recv(chunk_size)
                raw_stats += chunk
                if len(chunk) < chunk_size:
                    break

            return self._parse_stats(raw_stats)
        except socket.error as e:
            LOG.warning(_LW('Error while connecting to stats socket: %s'), e)
            return {}

    def _parse_stats(self, raw_stats):
        stat_lines = raw_stats.splitlines()
        if len(stat_lines) < 2:
            return []
        stat_names = [name.strip('# ') for name in stat_lines[0].split(',')]
        res_stats = []
        for raw_values in stat_lines[1:]:
            if not raw_values:
                continue
            stat_values = [value.strip() for value in raw_values.split(',')]
            res_stats.append(dict(zip(stat_names, stat_values)))

        return res_stats

    def _collect_and_store_stats(self):
        for loadbalancer_id in self.deployed_loadbalancer_ids:
            loadbalancer = self.plugin.db.get_loadbalancer(self.admin_ctx,
                                                           loadbalancer_id)
            stats = self.get_stats(loadbalancer)
            self.plugin.db.update_loadbalancer_stats(
                self.admin_ctx, loadbalancer.id, stats)
            if 'members' in stats:
                self._set_member_status(self.admin_ctx, loadbalancer,
                                        stats['members'])

    def _get_members(self, loadbalancer):
        for listener in loadbalancer.listeners:
            if listener.default_pool:
                for member in listener.default_pool.members:
                    yield member

    def _set_member_status(self, context, loadbalancer, members_stats):
        for member in self._get_members(loadbalancer):
            if member.id in members_stats:
                status = members_stats[member.id].get('status')
                if status and status == constants.ACTIVE:
                    self.plugin.db.update_status(
                        context, self.member.model_class, member.id,
                        operating_status=lb_const.ONLINE)
                elif status and status == lb_const.NO_CHECK:
                    self.plugin.db.update_status(
                        context, self.member.model_class, member.id,
                        operating_status=lb_const.NO_MONITOR)
                else:
                    self.plugin.db.update_status(
                        context, self.member.model_class, member.id,
                        operating_status=lb_const.OFFLINE)

    def _remove_config_directory(self, loadbalancer_id):
        conf_dir = os.path.dirname(
            self._get_state_file_path(loadbalancer_id, ''))
        if os.path.isdir(conf_dir):
            shutil.rmtree(conf_dir)
        if loadbalancer_id in self.deployed_loadbalancer_ids:
            # If it doesn't exist then didn't need to remove in the first place
            self.deployed_loadbalancer_ids.remove(loadbalancer_id)

    def _cleanup_namespace(self, loadbalancer_id):
        namespace = get_ns_name(loadbalancer_id)
        ns = ip_lib.IPWrapper(namespace=namespace)
        try:
            for device in ns.get_devices(exclude_loopback=True):
                if ip_lib.device_exists(device.name):
                    self.vif_driver.unplug(device.name, namespace=namespace)
        except RuntimeError as re:
            LOG.warning(_LW('An error happened on namespace cleanup: '
                            '%s'), re.message)
        ns.garbage_collect_namespace()

    def _kill_processes(self, loadbalancer_id):
        pid_path = self._get_state_file_path(loadbalancer_id, 'haproxy.pid')
        # kill the process
        namespace_driver.kill_pids_in_file(pid_path)

    def _unplug_vip_port(self, loadbalancer):
        namespace = get_ns_name(loadbalancer.id)
        if loadbalancer.vip_port_id:
            self._unplug(namespace, loadbalancer.vip_port_id)

    def _delete_instance_from_system(self, loadbalancer_id):
        self._kill_processes(loadbalancer_id)
        self._cleanup_namespace(loadbalancer_id)
        self._remove_config_directory(loadbalancer_id)

    @log_helpers.log_method_call
    def periodic_tasks(self, *args):
        try:
            self._collect_and_store_stats()
        except Exception:
            LOG.exception(_LE("Periodic task failed."))

    def create_instance(self, context, loadbalancer):
        namespace = get_ns_name(loadbalancer.id)

        self._plug(context, namespace, loadbalancer.vip_port)
        self._spawn(loadbalancer)

    def update_instance(self, loadbalancer):
        pid_path = self._get_state_file_path(loadbalancer.id,
                                             'haproxy.pid')

        extra_args = ['-sf']
        extra_args.extend(p.strip() for p in open(pid_path, 'r'))
        self._spawn(loadbalancer, extra_args)

    def delete_instance(self, loadbalancer, cleanup_namespace=False):
        self._kill_processes(loadbalancer.id)
        # unplug the ports
        self._unplug_vip_port(loadbalancer)
        # delete all devices from namespace;
        # used when deleting orphans and vip_port_id is not known for
        # loadbalancer_id
        if cleanup_namespace:
            self._cleanup_namespace(loadbalancer.id)
        self._remove_config_directory(loadbalancer.id)

    def exists(self, loadbalancer):
        namespace = get_ns_name(loadbalancer.id)
        root_ns = ip_lib.IPWrapper()

        socket_path = self._get_state_file_path(
            loadbalancer.id, 'haproxy_stats.sock', False)
        if root_ns.netns.exists(namespace) and os.path.exists(socket_path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(socket_path)
                return True
            except socket.error:
                pass
        return False

    def get_stats(self, loadbalancer):
        socket_path = self._get_state_file_path(loadbalancer.id,
                                                'haproxy_stats.sock',
                                                False)
        if os.path.exists(socket_path):
            parsed_stats = self._get_stats_from_socket(
                socket_path,
                entity_type=(STATS_TYPE_BACKEND_REQUEST |
                             STATS_TYPE_SERVER_REQUEST))
            lb_stats = self._get_backend_stats(parsed_stats)
            lb_stats['members'] = self._get_servers_stats(parsed_stats)
            return lb_stats
        else:
            LOG.warning(_LW('Stats socket not found for load balancer %s'),
                        loadbalancer.id)
            return {}


class LoadBalancerManager(driver_base.BaseLoadBalancerManager):

    def refresh(self, context, loadbalancer):
        super(LoadBalancerManager, self).refresh(context, loadbalancer)
        if not self.deployable(loadbalancer):
            #TODO(brandon-logan): Ensure there is a way to sync the change
            #later.  Periodic task perhaps.
            return

        if self.driver.exists(loadbalancer):
            self.driver.update_instance(loadbalancer)
        else:
            self.driver.create_instance(context, loadbalancer)

    def delete(self, context, loadbalancer):
        super(LoadBalancerManager, self).delete(context, loadbalancer)
        try:
            self.driver.delete_instance(loadbalancer)
            self.successful_completion(context, loadbalancer, delete=True)
        except Exception as e:
            self.failed_completion(context, loadbalancer)
            raise e

    def create(self, context, loadbalancer):
        super(LoadBalancerManager, self).create(context, loadbalancer)
        # loadbalancer has no listeners then do nothing because haproxy will
        # not start without a tcp port.  Consider this successful anyway.
        if not loadbalancer.listeners:
            self.successful_completion(context, loadbalancer)
            return

        try:
            self.refresh(context, loadbalancer)
        except Exception as e:
            self.failed_completion(context, loadbalancer)
            raise e

        self.successful_completion(context, loadbalancer)

    def stats(self, context, loadbalancer):
        super(LoadBalancerManager, self).stats(context, loadbalancer)
        return self.driver.get_stats(loadbalancer)

    def update(self, context, old_loadbalancer, loadbalancer):
        super(LoadBalancerManager, self).update(context, old_loadbalancer,
                                                loadbalancer)
        try:
            self.refresh(context, loadbalancer)
        except Exception as e:
            self.failed_completion(context, loadbalancer)
            raise e

        self.successful_completion(context, loadbalancer)

    def deployable(self, loadbalancer):
        if not loadbalancer:
            return False
        acceptable_listeners = [
            listener for listener in loadbalancer.listeners
            if (listener.provisioning_status != constants.PENDING_DELETE and
                listener.admin_state_up)]
        return (bool(acceptable_listeners) and loadbalancer.admin_state_up and
                loadbalancer.provisioning_status != constants.PENDING_DELETE)


class ListenerManager(driver_base.BaseListenerManager):

    def _remove_listener(self, loadbalancer, listener_id):
        index_to_remove = None
        for index, listener in enumerate(loadbalancer.listeners):
            if listener.id == listener_id:
                index_to_remove = index
        loadbalancer.listeners.pop(index_to_remove)

    def update(self, context, old_listener, new_listener):
        super(ListenerManager, self).update(context, old_listener,
                                            new_listener)
        try:
            self.driver.load_balancer.refresh(context,
                                              new_listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, new_listener)
            raise e

        self.successful_completion(context, new_listener)

    def create(self, context, listener):
        super(ListenerManager, self).create(context, listener)
        try:
            self.driver.load_balancer.refresh(context, listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, listener)
            raise e

        self.successful_completion(context, listener)

    def delete(self, context, listener):
        super(ListenerManager, self).delete(context, listener)
        loadbalancer = listener.loadbalancer
        self._remove_listener(loadbalancer, listener.id)
        try:
            if len(loadbalancer.listeners) > 0:
                self.driver.load_balancer.refresh(context, loadbalancer)
            else:
                # delete instance because haproxy will throw error if port is
                # missing in frontend
                self.driver.delete_instance(loadbalancer)
        except Exception as e:
            self.failed_completion(context, listener)
            raise e

        self.successful_completion(context, listener, delete=True)


class PoolManager(driver_base.BasePoolManager):

    def update(self, context, old_pool, new_pool):
        super(PoolManager, self).update(context, old_pool, new_pool)
        try:
            self.driver.load_balancer.refresh(context,
                                              new_pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, new_pool)
            raise e

        self.successful_completion(context, new_pool)

    def create(self, context, pool):
        super(PoolManager, self).delete(context, pool)
        try:
            self.driver.load_balancer.refresh(context,
                                              pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, pool)
            raise e

        self.successful_completion(context, pool)

    def delete(self, context, pool):
        super(PoolManager, self).delete(context, pool)
        loadbalancer = pool.listener.loadbalancer
        pool.listener.default_pool = None
        try:
            # just refresh because haproxy is fine if only frontend is listed
            self.driver.load_balancer.refresh(context, loadbalancer)
        except Exception as e:
            self.failed_completion(context, pool)
            raise e

        self.successful_completion(context, pool, delete=True)


class MemberManager(driver_base.BaseMemberManager):

    def _remove_member(self, pool, member_id):
        index_to_remove = None
        for index, member in enumerate(pool.members):
            if member.id == member_id:
                index_to_remove = index
        pool.members.pop(index_to_remove)

    def update(self, context, old_member, new_member):
        super(MemberManager, self).update(context, old_member, new_member)
        try:
            self.driver.load_balancer.refresh(
                context, new_member.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, new_member)
            raise e

        self.successful_completion(context, new_member)

    def create(self, context, member):
        super(MemberManager, self).create(context, member)
        try:
            self.driver.load_balancer.refresh(
                context, member.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, member)
            raise e

        self.successful_completion(context, member)

    def delete(self, context, member):
        super(MemberManager, self).delete(context, member)
        self._remove_member(member.pool, member.id)
        try:
            self.driver.load_balancer.refresh(
                context, member.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, member)
            raise e

        self.successful_completion(context, member, delete=True)


class HealthMonitorManager(driver_base.BaseHealthMonitorManager):

    def update(self, context, old_hm, new_hm):
        super(HealthMonitorManager, self).update(context, old_hm, new_hm)
        try:
            self.driver.load_balancer.refresh(
                context, new_hm.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, new_hm)
            raise e

        self.successful_completion(context, new_hm)

    def create(self, context, hm):
        super(HealthMonitorManager, self).create(context, hm)
        try:
            self.driver.load_balancer.refresh(
                context, hm.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, hm)
            raise e

        self.successful_completion(context, hm)

    def delete(self, context, hm):
        super(HealthMonitorManager, self).delete(context, hm)
        hm.pool.healthmonitor = None
        try:
            self.driver.load_balancer.refresh(context,
                                              hm.pool.listener.loadbalancer)
        except Exception as e:
            self.failed_completion(context, hm)
            raise e

        self.successful_completion(context, hm, delete=True)
