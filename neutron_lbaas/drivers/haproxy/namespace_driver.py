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

import os
import shutil
import socket

import netaddr
from neutron.agent.linux import external_process
from neutron.agent.linux import ip_lib
from neutron_lib import constants
from neutron_lib import exceptions
from neutron_lib.utils import runtime
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import fileutils

from neutron_lbaas._i18n import _
from neutron_lbaas.agent import agent_device_driver
from neutron_lbaas.drivers.haproxy import jinja_cfg
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models

LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'
STATS_TYPE_BACKEND_REQUEST = 2
STATS_TYPE_BACKEND_RESPONSE = '1'
STATS_TYPE_SERVER_REQUEST = 4
STATS_TYPE_SERVER_RESPONSE = '2'
DRIVER_NAME = 'haproxy_ns'
HAPROXY_SERVICE_NAME = 'lbaas-ns-haproxy'

STATE_PATH_V2_APPEND = 'v2'

STATE_PATH_DEFAULT = '$state_path/lbaas'
USER_GROUP_DEFAULT = 'nogroup'
OPTS = [
    cfg.StrOpt(
        'loadbalancer_state_path',
        default=STATE_PATH_DEFAULT,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Location to store config and state files'),
        deprecated_opts=[cfg.DeprecatedOpt('loadbalancer_state_path',
                                           group='DEFAULT')],
    ),
    cfg.StrOpt(
        'user_group',
        default=USER_GROUP_DEFAULT,
        help=_('The user group'),
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        deprecated_opts=[cfg.DeprecatedOpt('user_group', group='DEFAULT')],
    ),
    cfg.IntOpt(
        'send_gratuitous_arp',
        default=3,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('When delete and re-add the same vip, send this many '
               'gratuitous ARPs to flush the ARP cache in the Router. '
               'Set it below or equal to 0 to disable this feature.'),
    )
]
cfg.CONF.register_opts(OPTS, 'haproxy')


def get_ns_name(namespace_id):
    return NS_PREFIX + namespace_id


class HaproxyNSDriver(agent_device_driver.AgentDeviceDriver):

    def __init__(self, conf, plugin_rpc, process_monitor):
        super(HaproxyNSDriver, self).__init__(conf, plugin_rpc,
                                              process_monitor)
        self.state_path = conf.haproxy.loadbalancer_state_path
        self.state_path = os.path.join(
            self.conf.haproxy.loadbalancer_state_path, STATE_PATH_V2_APPEND)
        try:
            vif_driver_class = runtime.load_class_by_alias_or_classname(
                'neutron.interface_drivers',
                conf.interface_driver)
        except ImportError:
            with excutils.save_and_reraise_exception():
                msg = (_('Error importing interface driver: %s')
                       % conf.interface_driver)
                LOG.error(msg)

        self.vif_driver = vif_driver_class(conf)
        self.deployed_loadbalancers = {}
        self._loadbalancer = LoadBalancerManager(self)
        self._listener = ListenerManager(self)
        self._pool = PoolManager(self)
        self._member = MemberManager(self)
        self._healthmonitor = HealthMonitorManager(self)

    @property
    def loadbalancer(self):
        return self._loadbalancer

    @property
    def listener(self):
        return self._listener

    @property
    def pool(self):
        return self._pool

    @property
    def member(self):
        return self._member

    @property
    def healthmonitor(self):
        return self._healthmonitor

    def get_name(self):
        return DRIVER_NAME

    @runtime.synchronized('haproxy-driver')
    def undeploy_instance(self, loadbalancer_id, **kwargs):
        cleanup_namespace = kwargs.get('cleanup_namespace', False)
        delete_namespace = kwargs.get('delete_namespace', False)
        namespace = get_ns_name(loadbalancer_id)
        pid_data = self._get_state_file_path(loadbalancer_id, 'haproxy.pid')
        pid_path = os.path.split(pid_data)[0]
        self.process_monitor.unregister(uuid=loadbalancer_id,
                                        service_name=HAPROXY_SERVICE_NAME)
        pm = external_process.ProcessManager(uuid=loadbalancer_id,
                                             namespace=namespace,
                                             service=HAPROXY_SERVICE_NAME,
                                             conf=self.conf,
                                             pids_path=pid_path,
                                             pid_file=pid_data)
        pm.disable()
        # unplug the ports
        if loadbalancer_id in self.deployed_loadbalancers:
            self._unplug(namespace,
                         self.deployed_loadbalancers[loadbalancer_id].vip_port)

        # delete all devices from namespace
        # used when deleting orphans and port is not known for a loadbalancer
        if cleanup_namespace:
            ns = ip_lib.IPWrapper(namespace=namespace)
            for device in ns.get_devices(exclude_loopback=True):
                self.vif_driver.unplug(device.name, namespace=namespace)

        # remove the configuration directory
        conf_dir = os.path.dirname(
            self._get_state_file_path(loadbalancer_id, ''))
        if os.path.isdir(conf_dir):
            shutil.rmtree(conf_dir)

        if delete_namespace:
            ns = ip_lib.IPWrapper(namespace=namespace)
            ns.garbage_collect_namespace()

    def remove_orphans(self, known_loadbalancer_ids):
        if not os.path.exists(self.state_path):
            return

        orphans = (lb_id for lb_id in os.listdir(self.state_path)
                   if lb_id not in known_loadbalancer_ids)
        for lb_id in orphans:
            if self.exists(lb_id):
                self.undeploy_instance(lb_id, cleanup_namespace=True)

    def get_stats(self, loadbalancer_id):
        socket_path = self._get_state_file_path(loadbalancer_id,
                                                'haproxy_stats.sock', False)
        if os.path.exists(socket_path):
            parsed_stats = self._get_stats_from_socket(
                socket_path,
                entity_type=(STATS_TYPE_BACKEND_REQUEST |
                             STATS_TYPE_SERVER_REQUEST))
            lb_stats = self._get_backend_stats(parsed_stats)
            lb_stats['members'] = self._get_servers_stats(parsed_stats)
            return lb_stats
        else:
            lb_config = self.plugin_rpc.get_loadbalancer(loadbalancer_id)
            loadbalancer = data_models.LoadBalancer.from_dict(lb_config)
            if self._is_active(loadbalancer):
                LOG.warning('Stats socket not found for loadbalancer %s',
                            loadbalancer_id)
            else:
                LOG.debug('Stats socket not found for loadbalancer %s,'
                          ' but loadbalancer has no VIP in state UP.'
                          ' Perhaps the lbaas-listener is not yet created?',
                          loadbalancer_id)
            return {}

    @runtime.synchronized('haproxy-driver')
    def deploy_instance(self, loadbalancer):
        """Deploys loadbalancer if necessary

        :returns: True if loadbalancer was deployed, False otherwise
        """
        if not self.deployable(loadbalancer):
            LOG.info("Loadbalancer %s is not deployable." %
                     loadbalancer.id)
            return False

        if self.exists(loadbalancer.id):
            self.update(loadbalancer)
        else:
            self.create(loadbalancer)
        return True

    def update(self, loadbalancer):
        pid_path = self._get_state_file_path(loadbalancer.id, 'haproxy.pid')
        extra_args = ['-sf']
        extra_args.extend(p.strip() for p in open(pid_path, 'r'))
        self._spawn(loadbalancer, extra_args)

    def exists(self, loadbalancer_id):
        namespace = get_ns_name(loadbalancer_id)
        root_ns = ip_lib.IPWrapper()

        socket_path = self._get_state_file_path(
            loadbalancer_id, 'haproxy_stats.sock', False)
        if root_ns.netns.exists(namespace) and os.path.exists(socket_path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(socket_path)
                return True
            except socket.error:
                pass
        return False

    def create(self, loadbalancer):
        namespace = get_ns_name(loadbalancer.id)

        self._plug(namespace, loadbalancer.vip_port, loadbalancer.vip_address)
        self._spawn(loadbalancer)

    def deployable(self, loadbalancer):
        """Returns True if loadbalancer is active and has active listeners."""
        if not loadbalancer:
            return False
        acceptable_listeners = [
            listener for listener in loadbalancer.listeners
            if (listener.provisioning_status != constants.PENDING_DELETE and
                listener.admin_state_up)]
        return (bool(acceptable_listeners) and loadbalancer.admin_state_up and
                loadbalancer.provisioning_status != constants.PENDING_DELETE)

    def _get_stats_from_socket(self, socket_path, entity_type):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(socket_path)
            s.send(('show stat -1 %s -1\n' % entity_type).encode('utf-8'))
            raw_stats = ''
            chunk_size = 1024
            while True:
                chunk = s.recv(chunk_size).decode('utf-8')
                raw_stats += chunk
                if len(chunk) < chunk_size:
                    break

            return self._parse_stats(raw_stats)
        except socket.error as e:
            LOG.warning('Error while connecting to stats socket: %s', e)
            return {}

    def _parse_stats(self, raw_stats):
        stat_lines = raw_stats.splitlines()
        if len(stat_lines) < 2:
            return []
        formatted_stat_names = stat_lines[0].lstrip('# ').rstrip(',')
        stat_names = formatted_stat_names.split(',')
        res_stats = []
        for raw_values in stat_lines[1:]:
            if not raw_values:
                continue
            stat_values = [value.strip()
                           for value in raw_values.rstrip(',').split(',')]
            res_stats.append(dict(zip(stat_names, stat_values)))

        return res_stats

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
                    lb_const.OPERATING_STATUS: (lb_const.OFFLINE
                                            if stats['status'] == 'DOWN'
                                            else lb_const.ONLINE),
                    lb_const.STATS_HEALTH: stats['check_status'],
                    lb_const.STATS_FAILED_CHECKS: stats['chkfail']
                }
        return res

    def _get_state_file_path(self, loadbalancer_id, kind,
                             ensure_state_dir=True):
        """Returns the file name for a given kind of config file."""
        confs_dir = os.path.abspath(os.path.normpath(self.state_path))
        conf_dir = os.path.join(confs_dir, loadbalancer_id)
        if ensure_state_dir:
            fileutils.ensure_tree(conf_dir, 0o755)
        return os.path.join(conf_dir, kind)

    def _plug(self, namespace, port, vip_address, reuse_existing=True):
        self.plugin_rpc.plug_vip_port(port.id)

        interface_name = self.vif_driver.get_device_name(port)

        if ip_lib.device_exists(interface_name,
                                namespace=namespace):
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
                namespace=namespace,
                mtu=port.network.mtu
            )

        cidrs = [
            '%s/%s' % (ip.ip_address,
                       netaddr.IPNetwork(ip.subnet.cidr).prefixlen)
            for ip in port.fixed_ips
        ]
        self.vif_driver.init_l3(interface_name, cidrs, namespace=namespace)

        # Haproxy socket binding to IPv6 VIP address will fail if this address
        # is not yet ready(i.e tentative address).
        if netaddr.IPAddress(vip_address).version == 6:
            device = ip_lib.IPDevice(interface_name, namespace=namespace)
            device.addr.wait_until_address_ready(vip_address)

        # Add subnet host routes
        host_routes = port.fixed_ips[0].subnet.host_routes
        for host_route in host_routes:
            if host_route.destination != "0.0.0.0/0":
                cmd = ['route', 'add', '-net', host_route.destination,
                       'gw', host_route.nexthop]
                ip_wrapper = ip_lib.IPWrapper(namespace=namespace)
                ip_wrapper.netns.execute(cmd, check_exit_code=False)

        gw_ip = port.fixed_ips[0].subnet.gateway_ip

        if not gw_ip:
            for host_route in host_routes:
                if host_route.destination == "0.0.0.0/0":
                    gw_ip = host_route.nexthop
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

    def _unplug(self, namespace, port):
        self.plugin_rpc.unplug_vip_port(port.id)
        interface_name = self.vif_driver.get_device_name(port)
        self.vif_driver.unplug(interface_name, namespace=namespace)

    def _spawn(self, loadbalancer, extra_cmd_args=()):
        conf_path = self._get_state_file_path(loadbalancer.id,
                                              'haproxy.conf')
        sock_path = self._get_state_file_path(loadbalancer.id,
                                              'haproxy_stats.sock')
        user_group = self.conf.haproxy.user_group
        haproxy_base_dir = self._get_state_file_path(loadbalancer.id, '')
        jinja_cfg.save_config(conf_path,
                              loadbalancer,
                              sock_path,
                              user_group,
                              haproxy_base_dir)

        def callback(pid_path):
            cmd = ['haproxy', '-f', conf_path, '-p', pid_path]
            cmd.extend(extra_cmd_args)
            return cmd

        pid_data = self._get_state_file_path(loadbalancer.id, 'haproxy.pid')
        pid_path = os.path.split(pid_data)[0]
        namespace = get_ns_name(loadbalancer.id)
        pm = external_process.ProcessManager(
            uuid=loadbalancer.id,
            default_cmd_callback=callback,
            namespace=namespace,
            service=HAPROXY_SERVICE_NAME,
            conf=self.conf,
            pids_path=pid_path,
            pid_file=pid_data,
            custom_reload_callback=callback if extra_cmd_args else None)
        if pm.active:
            pm.reload_cfg()
        else:
            pm.enable()
        self.process_monitor.register(uuid=loadbalancer.id,
                                      service_name=HAPROXY_SERVICE_NAME,
                                      monitored_process=pm)
        # remember deployed loadbalancer id
        self.deployed_loadbalancers[loadbalancer.id] = loadbalancer

    def _is_active(self, loadbalancer):
        # haproxy will be unable to start without any active vip
        if (len(loadbalancer.listeners) == 0 or
                loadbalancer.vip_port.status == constants.DOWN or
                not loadbalancer.vip_port.admin_state_up or
                loadbalancer.operating_status != lb_const.ONLINE):
            return False
        return True


class LoadBalancerManager(agent_device_driver.BaseLoadBalancerManager):

    def refresh(self, loadbalancer):
        loadbalancer_dict = self.driver.plugin_rpc.get_loadbalancer(
            loadbalancer.id)
        loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer_dict)
        if (not self.driver.deploy_instance(loadbalancer) and
                self.driver.exists(loadbalancer.id)):
            self.driver.undeploy_instance(loadbalancer.id)

    def delete(self, loadbalancer):
        if self.driver.exists(loadbalancer.id):
            self.driver.undeploy_instance(loadbalancer.id,
                                          delete_namespace=True)

    def create(self, loadbalancer):
        # loadbalancer has no listeners then do nothing because haproxy will
        # not start without a tcp port.  Consider this successful anyway.
        if not loadbalancer.listeners:
            return
        self.refresh(loadbalancer)

    def get_stats(self, loadbalancer_id):
        stats = self.driver.get_stats(loadbalancer_id)

        # NOTE(cgoncalves): haproxy stats include member status which maps to
        # MemberV2.operating_status. Take the opportunty to update member
        # operating status.
        members = stats.get('members')
        if members:
            for member_id, value in members.items():
                if lb_const.OPERATING_STATUS in value:
                    self.driver.plugin_rpc.update_status(
                        'member', member_id,
                        operating_status=value[lb_const.OPERATING_STATUS])

        return stats

    def update(self, old_loadbalancer, loadbalancer):
        self.refresh(loadbalancer)


class ListenerManager(agent_device_driver.BaseListenerManager):

    def _remove_listener(self, loadbalancer, listener_id):
        index_to_remove = None
        for index, listener in enumerate(loadbalancer.listeners):
            if listener.id == listener_id:
                index_to_remove = index
        loadbalancer.listeners.pop(index_to_remove)

    def update(self, old_listener, new_listener):
        self.driver.loadbalancer.refresh(new_listener.loadbalancer)

    def create(self, listener):
        self.driver.loadbalancer.refresh(listener.loadbalancer)

    def delete(self, listener):
        loadbalancer = listener.loadbalancer
        self._remove_listener(loadbalancer, listener.id)
        if len(loadbalancer.listeners) > 0:
            self.driver.loadbalancer.refresh(loadbalancer)
        else:
            # undeploy instance because haproxy will throw error if port is
            # missing in frontend
            self.driver.undeploy_instance(loadbalancer.id,
                                          delete_namespace=True)


class PoolManager(agent_device_driver.BasePoolManager):

    def update(self, old_pool, new_pool):
        self.driver.loadbalancer.refresh(new_pool.loadbalancer)

    def create(self, pool):
        self.driver.loadbalancer.refresh(pool.loadbalancer)

    def delete(self, pool):
        loadbalancer = pool.loadbalancer
        for l in loadbalancer.listeners:
            if l.default_pool == pool:
                l.default_pool = None
        # TODO(sbalukoff): Will need to do this or L7Policies as well
        # just refresh because haproxy is fine if only frontend is listed
        self.driver.loadbalancer.refresh(loadbalancer)


class MemberManager(agent_device_driver.BaseMemberManager):

    def _remove_member(self, pool, member_id):
        index_to_remove = None
        for index, member in enumerate(pool.members):
            if member.id == member_id:
                index_to_remove = index
        pool.members.pop(index_to_remove)

    def update(self, old_member, new_member):
        self.driver.loadbalancer.refresh(new_member.pool.loadbalancer)

    def create(self, member):
        self.driver.loadbalancer.refresh(member.pool.loadbalancer)

    def delete(self, member):
        self._remove_member(member.pool, member.id)
        self.driver.loadbalancer.refresh(member.pool.loadbalancer)


class HealthMonitorManager(agent_device_driver.BaseHealthMonitorManager):

    def update(self, old_hm, new_hm):
        self.driver.loadbalancer.refresh(new_hm.pool.loadbalancer)

    def create(self, hm):
        self.driver.loadbalancer.refresh(hm.pool.loadbalancer)

    def delete(self, hm):
        hm.pool.healthmonitor = None
        self.driver.loadbalancer.refresh(hm.pool.loadbalancer)
