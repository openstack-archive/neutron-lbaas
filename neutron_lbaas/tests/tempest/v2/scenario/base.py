# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Rackspace Inc.
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

import shlex
import socket
import subprocess
import tempfile
import time

from oslo_log import log as logging
from six.moves import http_cookiejar
from six.moves.urllib import error
from six.moves.urllib import request as urllib2
from tempest.common import utils
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions as lib_exc

from neutron_lbaas._i18n import _
from neutron_lbaas.tests.tempest.v2.clients import health_monitors_client
from neutron_lbaas.tests.tempest.v2.clients import listeners_client
from neutron_lbaas.tests.tempest.v2.clients import load_balancers_client
from neutron_lbaas.tests.tempest.v2.clients import members_client
from neutron_lbaas.tests.tempest.v2.clients import pools_client
from neutron_lbaas.tests.tempest.v2.scenario import manager

config = config.CONF

LOG = logging.getLogger(__name__)


def _setup_config_args(auth_provider):
    """Set up ServiceClient arguments using config settings. """
    service = config.network.catalog_type
    region = config.network.region or config.identity.region
    endpoint_type = config.network.endpoint_type
    build_interval = config.network.build_interval
    build_timeout = config.network.build_timeout

    # The disable_ssl appears in identity
    disable_ssl_certificate_validation = (
        config.identity.disable_ssl_certificate_validation)
    ca_certs = None

    # Trace in debug section
    trace_requests = config.debug.trace_requests

    return [auth_provider, service, region, endpoint_type, build_interval,
            build_timeout, disable_ssl_certificate_validation, ca_certs,
            trace_requests]


class BaseTestCase(manager.NetworkScenarioTest):

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.servers_keypairs = {}
        self.servers = {}
        self.members = []
        self.floating_ips = {}
        self.servers_floating_ips = {}
        self.server_ips = {}
        self.port1 = 80
        self.port2 = 88
        self.num = 50
        self.server_fixed_ips = {}

        self.listener_protocol = config.lbaas.default_listener_protocol
        self.pool_protocol = config.lbaas.default_pool_protocol
        self.hm_protocol = config.lbaas.default_health_monitor_protocol

        self._create_security_group_for_test()
        self._set_net_and_subnet()

        mgr = self.get_client_manager()
        auth_provider = mgr.auth_provider
        self.client_args = _setup_config_args(auth_provider)

        self.load_balancers_client = (
            load_balancers_client.LoadBalancersClientJSON(*self.client_args))
        self.listeners_client = (
            listeners_client.ListenersClientJSON(*self.client_args))
        self.pools_client = pools_client.PoolsClientJSON(*self.client_args)
        self.members_client = members_client.MembersClientJSON(
            *self.client_args)
        self.health_monitors_client = (
            health_monitors_client.HealthMonitorsClientJSON(
                *self.client_args))

    @classmethod
    def skip_checks(cls):
        super(BaseTestCase, cls).skip_checks()
        cfg = config.network
        if not utils.is_extension_enabled('lbaasv2', 'network'):
            msg = 'LBaaS Extension is not enabled'
            raise cls.skipException(msg)
        if not (cfg.project_networks_reachable or cfg.public_network_id):
            msg = ('Either tenant_networks_reachable must be "true", or '
                   'public_network_id must be defined.')
            raise cls.skipException(msg)

    def _set_net_and_subnet(self):
        """
        Query and set appropriate network and subnet attributes to be used
        for the test. Existing tenant networks are used if they are found.
        The configured private network and associated subnet is used as a
        fallback in absence of tenant networking.
        """
        tenant_id = self.networks_client.tenant_id
        try:
            tenant_net = self.os_admin.networks_client.list_networks(
                tenant_id=tenant_id)['networks'][0]
        except IndexError:
            tenant_net = None

        if tenant_net:
            self.subnet = self.os_admin.subnets_client.list_subnets(
                tenant_id=tenant_id)['subnets'][0]
            self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                            self.networks_client.delete_network,
                            self.subnet['id'])
            self.network = tenant_net
        else:
            self.network = self._get_network_by_name(
                config.compute.fixed_network_name)
            # We are assuming that the first subnet associated
            # with the fixed network is the one we want.  In the future, we
            # should instead pull a subnet id from config, which is set by
            # devstack/admin/etc.
            subnet = self.os_admin.subnets_client.list_subnets(
                network_id=self.network['id'])['subnets'][0]
            self.subnet = subnet

    def _create_security_group_for_test(self):
        self.security_group = self._create_security_group(
            tenant_id=self.networks_client.tenant_id)
        self._create_security_group_rules_for_port(self.port1)
        self._create_security_group_rules_for_port(self.port2)

    def _create_security_group_rules_for_port(self, port):
        rule = {
            'direction': 'ingress',
            'protocol': 'tcp',
            'port_range_min': port,
            'port_range_max': port,
        }
        self._create_security_group_rule(
            secgroup=self.security_group,
            tenant_id=self.networks_client.tenant_id,
            **rule)

    def _ipv6_subnet(self, address6_mode):
        tenant_id = self.networks_client.tenant_id
        router = self._get_router(tenant_id=tenant_id)
        self.network = self._create_network(tenant_id=tenant_id)
        self.subnet = self._create_subnet(network=self.network,
                                          namestart='sub6',
                                          ip_version=6,
                                          ipv6_ra_mode=address6_mode,
                                          ipv6_address_mode=address6_mode)
        self.subnet.add_to_router(router_id=router['id'])
        self.addCleanup(self.subnet.delete)

    def _create_server(self, name):
        keypair = self.create_keypair()
        security_groups = [{'name': self.security_group['name']}]
        create_kwargs = {
            'networks': [
                {'uuid': self.network['id']},
            ],
            'key_name': keypair['name'],
            'security_groups': security_groups,
            'name': name
        }
        net_name = self.network['name']
        server = self.create_server(**create_kwargs)
        waiters.wait_for_server_status(self.servers_client,
                                       server['id'], 'ACTIVE')
        server = self.servers_client.show_server(server['id'])
        server = server['server']
        self.servers_keypairs[server['id']] = keypair
        if (config.network.public_network_id and not
                config.network.project_networks_reachable):
            public_network_id = config.network.public_network_id
            floating_ip = self.create_floating_ip(
                server, public_network_id)
            self.floating_ips[floating_ip['id']] = server
            self.server_ips[server['id']] = floating_ip['floating_ip_address']
        else:
            self.server_ips[server['id']] =\
                server['addresses'][net_name][0]['addr']
        self.server_fixed_ips[server['id']] =\
            server['addresses'][net_name][0]['addr']
        self.assertTrue(self.servers_keypairs)
        return server

    def _create_servers(self):
        for count in range(2):
            self.server = self._create_server(name=("server%s" % (count + 1)))
            if count == 0:
                self.servers['primary'] = self.server['id']
            else:
                self.servers['secondary'] = self.server['id']
        self.assertEqual(len(self.servers_keypairs), 2)

    def _stop_server(self):
        for name, value in self.servers.items():
            if name == 'primary':
                self.servers_client.stop_server(value)
                waiters.wait_for_server_status(self.servers_client,
                                               value, 'SHUTOFF')

    def _start_server(self):
        for name, value in self.servers.items():
            if name == 'primary':
                self.servers_client.start(value)
                waiters.wait_for_server_status(self.servers_client,
                                               value, 'ACTIVE')

    def _start_servers(self):
        """
        Start two backends
        1. SSH to the instance
        2. Start two http backends listening on ports 80 and 88 respectively
        """
        for server_id, ip in self.server_ips.items():
            private_key = self.servers_keypairs[server_id]['private_key']
            server = self.servers_client.show_server(server_id)['server']
            server_name = server['name']
            username = config.validation.image_ssh_user
            ssh_client = self.get_remote_client(
                ip_address=ip,
                private_key=private_key)

            # Write a backend's response into a file
            resp = ('#!/bin/sh\n'
                    'echo -ne "HTTP/1.1 200 OK\r\nContent-Length: 7\r\n'
                    'Set-Cookie:JSESSIONID=%(s_id)s\r\nConnection: close\r\n'
                    'Content-Type: text/html; '
                    'charset=UTF-8\r\n\r\n%(server)s"; cat >/dev/null')

            with tempfile.NamedTemporaryFile(mode='w+') as script:
                script.write(resp % {'s_id': server_name[-1],
                                     'server': server_name})
                script.flush()
                with tempfile.NamedTemporaryFile(mode='w+') as key:
                    key.write(private_key)
                    key.flush()
                    self.copy_file_to_host(script.name,
                                           "/tmp/script1",
                                           ip,
                                           username, key.name)

            # Start netcat
            start_server = ('chmod a+x /tmp/%(script)s; '
                            'while true; do '
                            'sudo nc -ll -p %(port)s -e /tmp/%(script)s; '
                            'done > /dev/null &')
            cmd = start_server % {'port': self.port1,
                                  'script': 'script1'}
            ssh_client.exec_command(cmd)

            if len(self.server_ips) == 1:
                with tempfile.NamedTemporaryFile(mode='w+') as script:
                    script.write(resp % {'s_id': 2,
                                         'server': 'server2'})
                    script.flush()
                    with tempfile.NamedTemporaryFile(mode='w+') as key:
                        key.write(private_key)
                        key.flush()
                        self.copy_file_to_host(script.name,
                                               "/tmp/script2", ip,
                                               username, key.name)
                cmd = start_server % {'port': self.port2,
                                      'script': 'script2'}
                ssh_client.exec_command(cmd)

    def _create_listener(self, load_balancer_id, port=80, **kwargs):
        """Create a listener with HTTP protocol listening on port 80."""
        self.listener = self.listeners_client.create_listener(
            loadbalancer_id=load_balancer_id, protocol=self.listener_protocol,
            protocol_port=port, **kwargs)
        self.assertTrue(self.listener)
        self.addCleanup(self._cleanup_listener, self.listener.get('id'))
        return self.listener

    def _create_health_monitor(self):
        """Create a pool with ROUND_ROBIN algorithm."""
        self.hm = self.health_monitors_client.create_health_monitor(
            type=self.hm_protocol, max_retries=5, delay=3, timeout=5,
            pool_id=self.pool['id'])
        self.assertTrue(self.hm)
        self.addCleanup(self._cleanup_health_monitor, self.hm.get('id'))

    def _create_pool(self, listener_id, persistence_type=None,
                     cookie_name=None):
        """Create a pool with ROUND_ROBIN algorithm."""
        pool = {
            "listener_id": listener_id,
            "lb_algorithm": "ROUND_ROBIN",
            "protocol": self.pool_protocol
        }
        if persistence_type:
            pool.update({'session_persistence': {'type': persistence_type}})
        if cookie_name:
            pool.update({'session_persistence': {"cookie_name": cookie_name}})
        self.pool = self.pools_client.create_pool(**pool)
        self.assertTrue(self.pool)
        self.addCleanup(self._cleanup_pool, self.pool['id'])
        return self.pool

    def _cleanup_load_balancer(self, load_balancer_id):
        test_utils.call_and_ignore_notfound_exc(
            self.load_balancers_client.delete_load_balancer, load_balancer_id)
        self._wait_for_load_balancer_deletion(load_balancer_id)

    def _cleanup_listener(self, listener_id):
        test_utils.call_and_ignore_notfound_exc(
            self.listeners_client.delete_listener, listener_id)
        self._wait_for_listener_deletion(listener_id)

    def _cleanup_pool(self, pool_id):
        test_utils.call_and_ignore_notfound_exc(
            self.pools_client.delete_pool, pool_id)
        self._wait_for_pool_deletion(pool_id)

    def _cleanup_health_monitor(self, hm_id):
        test_utils.call_and_ignore_notfound_exc(
            self.health_monitors_client.delete_health_monitor, hm_id)
        self._wait_for_health_monitor_deletion(hm_id)

    def _create_members(self, load_balancer_id=None, pool_id=None,
                        subnet_id=None):
        """
        Create two members.

        In case there is only one server, create both members with the same ip
        but with different ports to listen on.
        """
        for server_id, ip in self.server_fixed_ips.items():
            if len(self.server_fixed_ips) == 1:
                member1 = self.members_client.create_member(
                    pool_id=pool_id,
                    address=ip,
                    protocol_port=self.port1,
                    subnet_id=subnet_id)
                self._wait_for_load_balancer_status(load_balancer_id)
                member2 = self.members_client.create_member(
                    pool_id=pool_id,
                    address=ip,
                    protocol_port=self.port2,
                    subnet_id=subnet_id)
                self._wait_for_load_balancer_status(load_balancer_id)
                self.members.extend([member1, member2])
            else:
                member = self.members_client.create_member(
                    pool_id=pool_id,
                    address=ip,
                    protocol_port=self.port1,
                    subnet_id=subnet_id)
                self._wait_for_load_balancer_status(load_balancer_id)
                self.members.append(member)
        self.assertTrue(self.members)

    def _assign_floating_ip_to_lb_vip(self, lb):
        public_network_id = config.network.public_network_id
        port_id = lb['vip_port_id']
        floating_ip = self.create_floating_ip(lb, public_network_id,
                                              port_id=port_id)
        self.floating_ips.setdefault(lb['id'], [])
        self.floating_ips[lb['id']].append(floating_ip)
        # Check for floating ip status before you check load-balancer
        self.check_floating_ip_status(floating_ip, "ACTIVE")

    def _create_load_balancer(self, ip_version=4, persistence_type=None):
        tenant_id = self.networks_client.tenant_id
        self.create_lb_kwargs = {'tenant_id': tenant_id,
                                 'vip_subnet_id': self.subnet['id']}
        self.load_balancer = self.load_balancers_client.create_load_balancer(
            **self.create_lb_kwargs)
        load_balancer_id = self.load_balancer['id']
        self.addCleanup(self._cleanup_load_balancer, load_balancer_id)
        self._wait_for_load_balancer_status(load_balancer_id)

        listener = self._create_listener(load_balancer_id=load_balancer_id)
        self._wait_for_load_balancer_status(load_balancer_id)

        self.pool = self._create_pool(listener_id=listener.get('id'),
                                      persistence_type=persistence_type)
        self._wait_for_load_balancer_status(load_balancer_id)

        self._create_members(load_balancer_id=load_balancer_id,
                             pool_id=self.pool['id'],
                             subnet_id=self.subnet['id'])

        self.vip_ip = self.load_balancer.get('vip_address')

        # if the ipv4 is used for lb, then fetch the right values from
        # tempest.conf file
        if ip_version == 4:
            if (config.network.public_network_id and not
                    config.network.project_networks_reachable):
                self._assign_floating_ip_to_lb_vip(self.load_balancer)
                self.vip_ip = self.floating_ips[
                    self.load_balancer['id']][0]['floating_ip_address']

        # Currently the ovs-agent is not enforcing security groups on the
        # vip port - see https://bugs.launchpad.net/neutron/+bug/1163569
        # However the linuxbridge-agent does, and it is necessary to add a
        # security group with a rule that allows tcp port 80 to the vip port.
        self.ports_client.update_port(
            self.load_balancer.get('vip_port_id'),
            security_groups=[self.security_group['id']])

    def _wait_for_load_balancer_status(self, load_balancer_id,
                                       provisioning_status='ACTIVE',
                                       operating_status='ONLINE'):
        interval_time = 1
        timeout = 600
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                lb = self.load_balancers_client.get_load_balancer(
                    load_balancer_id)
            except lib_exc.NotFound:
                    raise
            if (lb.get('provisioning_status') == provisioning_status and
                    lb.get('operating_status') == operating_status):
                break
            elif (lb.get('provisioning_status') == 'ERROR' or
                    lb.get('operating_status') == 'ERROR'):
                raise Exception(
                    _("Wait for load balancer for load balancer: {lb_id} "
                      "ran for {timeout} seconds and an ERROR was encountered "
                      "with provisioning status: {provisioning_status} and "
                      "operating status: {operating_status}").format(
                          timeout=timeout,
                          lb_id=lb.get('id'),
                          provisioning_status=provisioning_status,
                          operating_status=operating_status))
            time.sleep(interval_time)
        else:
            raise Exception(
                _("Wait for load balancer ran for {timeout} seconds and did "
                  "not observe {lb_id} reach {provisioning_status} "
                  "provisioning status and {operating_status} "
                  "operating status.").format(
                      timeout=timeout,
                      lb_id=lb.get('id'),
                      provisioning_status=provisioning_status,
                      operating_status=operating_status))
        return lb

    def _wait_for_resource_deletion(self, resource_type_name,
                                    resource_get_method,
                                    resource_id):
        interval_time = 1
        timeout = 600
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                resource_get_method(resource_id)
            except lib_exc.NotFound:
                return
            time.sleep(interval_time)
        else:
            raise Exception(
                _("Wait for {res_name} ran for {timeout} seconds and did "
                  "not observe {res_id} deletion processes ended").format(
                      res_name=resource_type_name,
                      timeout=timeout,
                      res_id=resource_id))

    def _wait_for_load_balancer_deletion(self, load_balancer_id):
        return self._wait_for_resource_deletion(
            'load balancer',
            self.load_balancers_client.get_load_balancer,
            load_balancer_id)

    def _wait_for_pool_deletion(self, pool_id):
        return self._wait_for_resource_deletion(
            'pool',
            self.pools_client.get_pool,
            pool_id)

    def _wait_for_listener_deletion(self, listener_id):
        return self._wait_for_resource_deletion(
            'listener',
            self.listeners_client.get_listener,
            listener_id)

    def _wait_for_health_monitor_deletion(self, health_monitor_id):
        return self._wait_for_resource_deletion(
            'health monitor',
            self.health_monitors_client.get_health_monitor,
            health_monitor_id)

    def _wait_for_pool_session_persistence(self, pool_id, sp_type=None):
        interval_time = 1
        timeout = 10
        end_time = time.time() + timeout
        while time.time() < end_time:
            pool = self.pools_client.get_pool(pool_id)
            sp = pool.get('session_persistence', None)
            if (not (sp_type or sp) or
                    pool['session_persistence']['type'] == sp_type):
                return pool
            time.sleep(interval_time)
        raise Exception(
            _("Wait for pool ran for {timeout} seconds and did "
              "not observe {pool_id} update session persistence type "
              "to {type}.").format(
                  timeout=timeout,
                  pool_id=pool_id,
                  type=sp_type))

    def _check_load_balancing(self, port=80):
        """
        1. Send NUM requests on the floating ip associated with the VIP
        2. Check that the requests are shared between the two servers
        """

        self._check_connection(self.vip_ip, port=port)
        counters = self._send_requests(self.vip_ip, ["server1", "server2"])
        for member, counter in counters.items():
            self.assertGreater(counter, 0, 'Member %s never balanced' % member)

    def _check_connection(self, check_ip, port=80):
        def try_connect(check_ip, port):
            try:
                resp = urllib2.urlopen("http://{0}:{1}/".format(check_ip,
                                                                port))
                if resp.getcode() == 200:
                    return True
                return False
            except IOError:
                return False
            except error.HTTPError:
                return False
        timeout = config.validation.ping_timeout
        start = time.time()
        while not try_connect(check_ip, port):
            if (time.time() - start) > timeout:
                message = ("Timed out trying to connect to {0}:{1} after "
                           "{2} seconds".format(check_ip, port, timeout))
                raise lib_exc.TimeoutException(message)

    def _send_requests(self, vip_ip, servers):
        counters = dict.fromkeys(servers, 0)
        for i in range(self.num):
            try:
                server = urllib2.urlopen("http://{0}/".format(vip_ip),
                                         None, 2).read().decode('utf8')
                counters[server] += 1
            # HTTP exception means fail of server, so don't increase counter
            # of success and continue connection tries
            except (error.HTTPError, error.URLError,
                    socket.timeout, socket.error):
                continue
        return counters

    def _traffic_validation_after_stopping_server(self):
        """Check that the requests are sent to the only ACTIVE server."""
        counters = self._send_requests(self.vip_ip, ["server1", "server2"])

        # Assert that no traffic is sent to server1.
        for member, counter in counters.items():
            if member == 'server1':
                self.assertEqual(counter, 0,
                                 'Member %s is not balanced' % member)

    def _check_load_balancing_after_deleting_resources(self):
        """
        Check that the requests are not sent to any servers
        Assert that no traffic is sent to any servers
        """
        counters = self._send_requests(self.vip_ip, ["server1", "server2"])
        for member, counter in counters.items():
            self.assertEqual(counter, 0, 'Member %s is balanced' % member)

    def _check_source_ip_persistence(self):
        """Check source ip session persistence.

        Verify that all requests from our ip are answered by the same server
        that handled it the first time.
        """
        # Check that backends are reachable
        self._check_connection(self.vip_ip)

        resp = []
        for count in range(10):
            resp.append(
                urllib2.urlopen("http://{0}/".format(self.vip_ip)).read())
        self.assertEqual(len(set(resp)), 1)

    def _update_pool_session_persistence(self, persistence_type=None,
                                         cookie_name=None):
        """Update a pool with new session persistence type and cookie name."""

        update_data = {'session_persistence': None}
        if persistence_type:
            update_data = {"session_persistence": {
                "type": persistence_type}}
        if cookie_name:
            update_data['session_persistence'].update(
                {"cookie_name": cookie_name})
        self.pools_client.update_pool(self.pool['id'], **update_data)
        self.pool = self._wait_for_pool_session_persistence(self.pool['id'],
                                                            persistence_type)
        self._wait_for_load_balancer_status(self.load_balancer['id'])
        if persistence_type:
            self.assertEqual(persistence_type,
                             self.pool['session_persistence']['type'])
        if cookie_name:
            self.assertEqual(cookie_name,
                             self.pool['session_persistence']['cookie_name'])

    def _check_cookie_session_persistence(self):
        """Check cookie persistence types by injecting cookies in requests."""

        # Send first request and get cookie from the server's response
        cj = http_cookiejar.CookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        opener.open("http://{0}/".format(self.vip_ip))
        resp = []
        # Send 10 subsequent requests with the cookie inserted in the headers.
        for count in range(10):
            request = urllib2.Request("http://{0}/".format(self.vip_ip))
            cj.add_cookie_header(request)
            response = urllib2.urlopen(request)
            resp.append(response.read())
        self.assertEqual(len(set(resp)), 1, message=resp)

    def copy_file_to_host(self, file_from, dest, host, username, pkey):
        dest = "%s@%s:%s" % (username, host, dest)
        cmd = ("scp -v -o UserKnownHostsFile=/dev/null "
               "-o StrictHostKeyChecking=no "
               "-i %(pkey)s %(file1)s %(dest)s" % {'pkey': pkey,
                                                   'file1': file_from,
                                                   'dest': dest})
        args = shlex.split(cmd)
        subprocess_args = {'stdout': subprocess.PIPE,
                           'stderr': subprocess.STDOUT}
        proc = subprocess.Popen(args, **subprocess_args)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            LOG.error(("Command {0} returned with exit status {1},"
                      "output {2}, error {3}").format(cmd, proc.returncode,
                                                      stdout, stderr))
        return stdout
