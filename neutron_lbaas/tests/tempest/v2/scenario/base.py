# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

import tempfile
import time

import six
from six.moves.urllib import error
from six.moves.urllib import request as urllib2

from neutron_lbaas.tests.tempest.lib.common import commands
from neutron_lbaas.tests.tempest.lib import config
from neutron_lbaas.tests.tempest.lib import exceptions
from neutron_lbaas.tests.tempest.lib.services.network import resources as \
    net_resources
from neutron_lbaas.tests.tempest.lib import test
from neutron_lbaas.tests.tempest.v2.scenario import manager

config = config.CONF


class BaseTestCase(manager.NetworkScenarioTest):

    @classmethod
    def skip_checks(cls):
        super(BaseTestCase, cls).skip_checks()
        cfg = config.network
        if not test.is_extension_enabled('lbaasv2', 'network'):
            msg = 'LBaaS Extension is not enabled'
            raise cls.skipException(msg)
        if not (cfg.tenant_networks_reachable or cfg.public_network_id):
            msg = ('Either tenant_networks_reachable must be "true", or '
                   'public_network_id must be defined.')
            raise cls.skipException(msg)

    @classmethod
    def resource_setup(cls):
        super(BaseTestCase, cls).resource_setup()
        cls.servers_keypairs = {}
        cls.servers = {}
        cls.members = []
        cls.floating_ips = {}
        cls.servers_floating_ips = {}
        cls.server_ips = {}
        cls.port1 = 80
        cls.port2 = 88
        cls.num = 50

    @classmethod
    def resource_cleanup(cls):
        super(BaseTestCase, cls).resource_cleanup()

    def _set_net_and_subnet(self):
        """
        Query and set appropriate network and subnet attributes to be used
        for the test. Existing tenant networks are used if they are found.
        The configured private network and associated subnet is used as a
        fallback in absence of tenant networking.
        """
        try:
            tenant_net = self._list_networks(tenant_id=self.tenant_id)[0]
        except IndexError:
            tenant_net = None

        if tenant_net:
            tenant_subnet = self._list_subnets(tenant_id=self.tenant_id)[0]
            self.subnet = net_resources.DeletableSubnet(
                client=self.network_client,
                **tenant_subnet)
            self.network = tenant_net
        else:
            self.network = self._get_network_by_name(
                config.compute.fixed_network_name)
            # We are assuming that the first subnet associated
            # with the fixed network is the one we want.  In the future, we
            # should instead pull a subnet id from config, which is set by
            # devstack/admin/etc.
            subnet = self._list_subnets(network_id=self.network['id'])[0]
            self.subnet = net_resources.AttributeDict(subnet)

    def _create_security_group_for_test(self):
        self.security_group = self._create_security_group(
            tenant_id=self.tenant_id)
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
            tenant_id=self.tenant_id,
            **rule)

    def _create_server(self, name):
        keypair = self.create_keypair()
        security_groups = [{'name': self.security_group['name']}]
        create_kwargs = {
            'networks': [
                {'uuid': self.network['id']},
            ],
            'key_name': keypair['name'],
            'security_groups': security_groups,
        }
        net_name = self.network['name']
        server = self.create_server(name=name, create_kwargs=create_kwargs)
        self.servers_keypairs[server['id']] = keypair
        if (config.network.public_network_id and not
                config.network.tenant_networks_reachable):
            public_network_id = config.network.public_network_id
            floating_ip = self.create_floating_ip(
                server, public_network_id)
            self.floating_ips[floating_ip] = server
            self.server_ips[server['id']] = floating_ip.floating_ip_address
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
        for name, value in six.iteritems(self.servers):
            if name == 'primary':
                self.servers_client.stop(value)
                self.servers_client.wait_for_server_status(value, 'SHUTOFF')

    def _start_server(self):
        for name, value in six.iteritems(self.servers):
            if name == 'primary':
                self.servers_client.start(value)
                self.servers_client.wait_for_server_status(value, 'ACTIVE')

    def _start_servers(self):
        """
        Start two backends
        1. SSH to the instance
        2. Start two http backends listening on ports 80 and 88 respectively
        """
        for server_id, ip in six.iteritems(self.server_ips):
            private_key = self.servers_keypairs[server_id]['private_key']
            server_name = self.servers_client.get_server(server_id)['name']
            username = config.scenario.ssh_user
            ssh_client = self.get_remote_client(
                server_or_ip=ip,
                private_key=private_key)

            # Write a backend's response into a file
            resp = ('echo -ne "HTTP/1.1 200 OK\r\nContent-Length: 7\r\n'
                    'Connection: close\r\nContent-Type: text/html; '
                    'charset=UTF-8\r\n\r\n%s"; cat >/dev/null')

            with tempfile.NamedTemporaryFile() as script:
                script.write(resp % server_name)
                script.flush()
                with tempfile.NamedTemporaryFile() as key:
                    key.write(private_key)
                    key.flush()
                    commands.copy_file_to_host(script.name,
                                               "/tmp/script1",
                                               ip,
                                               username, key.name)

            # Start netcat
            start_server = ('while true; do '
                            'sudo nc -ll -p %(port)s -e sh /tmp/%(script)s; '
                            'done > /dev/null &')
            cmd = start_server % {'port': self.port1,
                                  'script': 'script1'}
            ssh_client.exec_command(cmd)

            if len(self.server_ips) == 1:
                with tempfile.NamedTemporaryFile() as script:
                    script.write(resp % 'server2')
                    script.flush()
                    with tempfile.NamedTemporaryFile() as key:
                        key.write(private_key)
                        key.flush()
                        commands.copy_file_to_host(script.name,
                                                   "/tmp/script2", ip,
                                                   username, key.name)
                cmd = start_server % {'port': self.port2,
                                      'script': 'script2'}
                ssh_client.exec_command(cmd)

    def _check_connection(self, check_ip, port=80):
        def try_connect(ip, port):
            try:
                resp = urllib2.urlopen("http://{0}:{1}/".format(ip, port))
                if resp.getcode() == 200:
                    return True
                return False
            except IOError:
                return False
            except error.HTTPError:
                return False
        timeout = config.compute.ping_timeout
        start = time.time()
        while not try_connect(check_ip, port):
            if (time.time() - start) > timeout:
                message = "Timed out trying to connect to %s" % check_ip
                raise exceptions.TimeoutException(message)

    def _create_listener(self, load_balancer_id):
        """Create a listener with HTTP protocol listening on port 80."""
        self.listener = self.listeners_client.create_listener(
            loadbalancer_id=load_balancer_id,
            protocol='HTTP', protocol_port=80)
        self.assertTrue(self.listener)
        return self.listener

    def _create_health_monitor(self, pool_id):
        """Create a pool with ROUND_ROBIN algorithm."""
        self.hm = self.health_monitors_client.create_health_monitor(
            type='HTTP', max_retries=5, delay=3, timeout=5,
            pool_id=pool_id)
        self.assertTrue(self.hm)
        return self.hm

    def _create_pool(self, listener_id):
        """Create a pool with ROUND_ROBIN algorithm."""
        self.pool = self.pools_client.create_pool(
            protocol='HTTP',
            lb_algorithm='ROUND_ROBIN',
            listener_id=listener_id)
        self.assertTrue(self.pool)
        return self.pool

    def _create_members(self, load_balancer_id=None, pool_id=None,
                        subnet_id=None):
        """
        Create two members.

        In case there is only one server, create both members with the same ip
        but with different ports to listen on.
        """
        for server_id, ip in six.iteritems(self.server_fixed_ips):
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
        port_id = lb.vip_port_id
        floating_ip = self.create_floating_ip(lb, public_network_id,
                                              port_id=port_id)
        self.floating_ips.setdefault(lb.id, [])
        self.floating_ips[lb.id].append(floating_ip)
        # Check for floating ip status before you check load-balancer
        self.check_floating_ip_status(floating_ip, "ACTIVE")

    def _create_load_balancer(self):
        self.create_lb_kwargs = {'tenant_id': self.tenant_id,
                                 'vip_subnet_id': self.subnet['id']}
        self.load_balancer = self.load_balancers_client.create_load_balancer(
            **self.create_lb_kwargs)
        load_balancer_id = self.load_balancer['id']
        self._wait_for_load_balancer_status(load_balancer_id)

        listener = self._create_listener(load_balancer_id=load_balancer_id)
        self._wait_for_load_balancer_status(load_balancer_id)

        self.pool = self._create_pool(listener_id=listener.get('id'))
        self._wait_for_load_balancer_status(load_balancer_id)

        self._create_members(load_balancer_id=load_balancer_id,
                             pool_id=self.pool['id'],
                             subnet_id=self.subnet['id'])

        if (config.network.public_network_id and not
                config.network.tenant_networks_reachable):
            load_balancer = net_resources.AttributeDict(self.load_balancer)
            self._assign_floating_ip_to_lb_vip(load_balancer)
            self.vip_ip = self.floating_ips[
                load_balancer.id][0]['floating_ip_address']

        else:
            self.vip_ip = self.lb.vip_address

        # Currently the ovs-agent is not enforcing security groups on the
        # vip port - see https://bugs.launchpad.net/neutron/+bug/1163569
        # However the linuxbridge-agent does, and it is necessary to add a
        # security group with a rule that allows tcp port 80 to the vip port.
        self.network_client.update_port(
            self.load_balancer.get('vip_port_id'),
            security_groups=[self.security_group.id])

    def _wait_for_load_balancer_status(self, load_balancer_id,
                                       provisioning_status='ACTIVE',
                                       operating_status='ONLINE'):
        interval_time = 10
        timeout = 300
        end_time = time.time() + timeout
        while time.time() < end_time:
            lb = self.load_balancers_client.get_load_balancer(load_balancer_id)
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

    def _check_load_balancing(self):
        """
        1. Send NUM requests on the floating ip associated with the VIP
        2. Check that the requests are shared between the two servers
        """

        self._check_connection(self.vip_ip)
        self._send_requests(self.vip_ip, ["server1", "server2"])

    def _send_requests(self, vip_ip, servers):
        counters = dict.fromkeys(servers, 0)
        for i in range(self.num):
            try:
                server = urllib2.urlopen("http://{0}/".format(vip_ip)).read()
                counters[server] += 1
            # HTTP exception means fail of server, so don't increase counter
            # of success and continue connection tries
            except error.HTTPError:
                continue
        # Assert that each member of the pool gets balanced at least once
        for member, counter in six.iteritems(counters):
            self.assertGreater(counter, 0, 'Member %s never balanced' % member)

    def _check_load_balancing_after_stopping_server(self):
        """
        1. Send NUM requests on the floating ip associated with the VIP
        2. Check that the requests is shared in one ACTIVE server
        """

        self._check_connection(self.vip_ip)
        self._check_requests_after_stopping_server(self.vip_ip,
                                                   ["server1", "server2"])

    def _check_requests_after_stopping_server(self, vip_ip, servers):
        counters = dict.fromkeys(servers, 0)
        for i in range(self.num):
            try:
                server = urllib2.urlopen("http://{0}/".format(vip_ip)).read()
                counters[server] += 1
            # HTTP exception means fail of server, so don't increase counter
            # of success and continue connection tries
            except error.HTTPError:
                continue
        # Assert that each member of the pool gets balanced only once
        for member, counter in six.iteritems(counters):
            if member == 'server1':
                self.assertEqual(counter, 0, 'Member %s not balanced' % member)
