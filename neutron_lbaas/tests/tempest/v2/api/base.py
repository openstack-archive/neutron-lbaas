# Copyright 2015, 2016 Rackspace Inc.
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

import time

from neutron_lib import constants as n_constants
from oslo_log import log as logging
from tempest.api.network import base
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions

from neutron_lbaas._i18n import _
from neutron_lbaas.tests.tempest.v2.clients import health_monitors_client
from neutron_lbaas.tests.tempest.v2.clients import listeners_client
from neutron_lbaas.tests.tempest.v2.clients import load_balancers_client
from neutron_lbaas.tests.tempest.v2.clients import members_client
from neutron_lbaas.tests.tempest.v2.clients import pools_client

CONF = config.CONF

LOG = logging.getLogger(__name__)


def _setup_client_args(auth_provider):
    """Set up ServiceClient arguments using config settings. """
    service = CONF.network.catalog_type or 'network'
    region = CONF.network.region or 'regionOne'
    endpoint_type = CONF.network.endpoint_type
    build_interval = CONF.network.build_interval
    build_timeout = CONF.network.build_timeout

    # The disable_ssl appears in identity
    disable_ssl_certificate_validation = (
        CONF.identity.disable_ssl_certificate_validation)
    ca_certs = None

    # Trace in debug section
    trace_requests = CONF.debug.trace_requests

    return [auth_provider, service, region, endpoint_type,
            build_interval, build_timeout,
            disable_ssl_certificate_validation, ca_certs,
            trace_requests]


class BaseTestCase(base.BaseNetworkTest):

    # This class picks non-admin credentials and run the tempest tests

    _lbs_to_delete = []

    @classmethod
    def resource_setup(cls):
        super(BaseTestCase, cls).resource_setup()

        cls.listener_protocol = CONF.lbaas.default_listener_protocol
        cls.pool_protocol = CONF.lbaas.default_pool_protocol
        cls.hm_protocol = CONF.lbaas.default_health_monitor_protocol

        mgr = cls.get_client_manager()
        auth_provider = mgr.auth_provider
        client_args = _setup_client_args(auth_provider)

        cls.load_balancers_client = (
            load_balancers_client.LoadBalancersClientJSON(*client_args))
        cls.listeners_client = (
            listeners_client.ListenersClientJSON(*client_args))
        cls.pools_client = pools_client.PoolsClientJSON(*client_args)
        cls.members_client = members_client.MembersClientJSON(*client_args)
        cls.health_monitors_client = (
            health_monitors_client.HealthMonitorsClientJSON(*client_args))

    @classmethod
    def resource_cleanup(cls):

        for lb_id in cls._lbs_to_delete:
            try:
                lb = cls.load_balancers_client.get_load_balancer_status_tree(
                    lb_id).get('loadbalancer')
            except exceptions.NotFound:
                continue
            for listener in lb.get('listeners'):
                for pool in listener.get('pools'):
                    # delete pool's health-monitor
                    hm = pool.get('healthmonitor')
                    if hm:
                        test_utils.call_and_ignore_notfound_exc(
                            cls.health_monitors_client.delete_health_monitor,
                            pool.get('healthmonitor').get('id'))
                        cls._wait_for_load_balancer_status(lb_id)
                    test_utils.call_and_ignore_notfound_exc(
                        cls.pools_client.delete_pool,
                        pool.get('id'))
                    cls._wait_for_load_balancer_status(lb_id)
                    # delete pool's members
                    members = pool.get('members', [])
                    for member in members:
                        test_utils.call_and_ignore_notfound_exc(
                            cls.members_client.delete_member,
                            pool.get('id'), member.get('id'))
                        cls._wait_for_load_balancer_status(lb_id)
                    # delete pool
                    test_utils.call_and_ignore_notfound_exc(
                        cls.pools_client.delete_pool, pool.get('id'))
                    cls._wait_for_load_balancer_status(lb_id)
                # delete listener
                test_utils.call_and_ignore_notfound_exc(
                    cls.listeners_client.delete_listener,
                    listener.get('id'))
                cls._wait_for_load_balancer_status(lb_id)
            # delete load-balancer
            test_utils.call_and_ignore_notfound_exc(
                cls._delete_load_balancer, lb_id)

        # Wait for all LBs to be fully deleted
        for lb_id in cls._lbs_to_delete:
            cls._wait_for_load_balancer_status(
                lb_id, provisioning_status='DELETED', operating_status=None,
                delete=True)

        # Wait for straggling port deletes to finish (neutron will sometimes
        # claim they are deleted before they are totally finished deleting)
        remaining_ports = cls.ports_client.list_ports(
            network_id=cls.network['id']).get('ports')
        tries = 1
        while remaining_ports and tries <= 10:
            LOG.warning("Ports still exist on network %s (try #%s): %s",
                        cls.network['id'], tries, remaining_ports)
            time.sleep(10)
            remaining_ports = cls.ports_client.list_ports(
                network_id=cls.network['id']).get('ports')
            tries += 1

        if remaining_ports:
            LOG.error("Failed to remove all remaining ports on network %s. "
                      "Subnet deletion will probably fail.", cls.network['id'])

        super(BaseTestCase, cls).resource_cleanup()

    @classmethod
    def setUpClass(cls):
        cls.LOG = logging.getLogger(cls._get_full_case_name())
        super(BaseTestCase, cls).setUpClass()

    def setUp(cls):
        cls.LOG.info('Starting: {0}'.format(cls._testMethodName))
        super(BaseTestCase, cls).setUp()

    def tearDown(cls):
        super(BaseTestCase, cls).tearDown()
        cls.LOG.info('Finished: {0}\n'.format(cls._testMethodName))

    @classmethod
    def _create_load_balancer(cls, wait=True, **lb_kwargs):
        lb = cls.load_balancers_client.create_load_balancer(**lb_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(lb.get('id'))

        cls._lbs_to_delete.append(lb.get('id'))
        return lb

    @classmethod
    def _create_active_load_balancer(cls, **kwargs):
        lb = cls._create_load_balancer(**kwargs)
        lb = cls._wait_for_load_balancer_status(lb.get('id'))
        return lb

    @classmethod
    def _delete_load_balancer(cls, load_balancer_id, wait=True):
        cls.load_balancers_client.delete_load_balancer(load_balancer_id)
        if wait:
            cls._wait_for_load_balancer_status(
                load_balancer_id, delete=True)

    @classmethod
    def _update_load_balancer(cls, load_balancer_id, wait=True, **lb_kwargs):
        lb = cls.load_balancers_client.update_load_balancer(
            load_balancer_id, **lb_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(
                load_balancer_id)
        return lb

    @classmethod
    def _wait_for_load_balancer_status(cls, load_balancer_id,
                                       provisioning_status='ACTIVE',
                                       operating_status='ONLINE',
                                       delete=False):
        interval_time = 1
        timeout = 600
        end_time = time.time() + timeout
        lb = {}
        # When running with no-op drivers there is no actual health to
        # observe, so disable operating_status checks when running no-op.
        if CONF.lbaas.test_with_noop:
            operating_status = None
        while time.time() < end_time:
            try:
                lb = cls.load_balancers_client.get_load_balancer(
                    load_balancer_id)
                if not lb:
                        # loadbalancer not found
                    if delete:
                        break
                    else:
                        raise Exception(
                            _("loadbalancer {lb_id} not"
                              " found").format(
                                  lb_id=load_balancer_id))
                if lb.get('provisioning_status') == provisioning_status:
                    if operating_status is None:
                        break
                    elif lb.get('operating_status') == operating_status:
                        break
                time.sleep(interval_time)
            except exceptions.NotFound:
                # if wait is for delete operation do break
                if delete:
                    break
                else:
                    # raise original exception
                    raise
        else:
            if delete:
                raise exceptions.TimeoutException(
                    _("Waited for load balancer {lb_id} to be deleted for "
                      "{timeout} seconds but can still observe that it "
                      "exists.").format(
                          lb_id=load_balancer_id,
                          timeout=timeout))
            else:
                raise exceptions.TimeoutException(
                    _("Wait for load balancer ran for {timeout} seconds and "
                      "did not observe {lb_id} reach {provisioning_status} "
                      "provisioning status and {operating_status} "
                      "operating status.").format(
                          timeout=timeout,
                          lb_id=load_balancer_id,
                          provisioning_status=provisioning_status,
                          operating_status=operating_status))
        return lb

    @classmethod
    def _wait_for_neutron_port_delete(cls, port_id):
        """
        Neutron port deletion is asynchronous. This method waits, up to a
        timeout for the port deletion to complete.
        """
        interval_time = 1
        timeout = 600
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                cls.ports_client.show_port(port_id)
                time.sleep(interval_time)
            except exceptions.NotFound:
                break
        else:
            raise exceptions.TimeoutException(
                    _("Waited for port {port_id} to be deleted for "
                      "{timeout} seconds but can still observe that it "
                      "exists.").format(port_id=port_id, timeout=timeout))

    @classmethod
    def _create_listener(cls, wait=True, **listener_kwargs):
        listener = cls.listeners_client.create_listener(**listener_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))
        return listener

    @classmethod
    def _delete_listener(cls, listener_id, wait=True):
        cls.listeners_client.delete_listener(listener_id)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))

    @classmethod
    def _update_listener(cls, listener_id, wait=True, **listener_kwargs):
        listener = cls.listeners_client.update_listener(
            listener_id, **listener_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(
                cls.load_balancer.get('id'))
        return listener

    @classmethod
    def _create_pool(cls, wait=True, **pool_kwargs):
        pool = cls.pools_client.create_pool(**pool_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))
        return pool

    @classmethod
    def _delete_pool(cls, pool_id, wait=True):
        cls.pools_client.delete_pool(pool_id)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))

    @classmethod
    def _update_pool(cls, pool_id, wait=True, **pool_kwargs):
        pool = cls.pools_client.update_pool(pool_id, **pool_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(
                cls.load_balancer.get('id'))
        return pool

    def _create_health_monitor(self, wait=True, cleanup=True,
                               **health_monitor_kwargs):
        hm = self.health_monitors_client.create_health_monitor(
            **health_monitor_kwargs)
        if cleanup:
            self.addCleanup(self._delete_health_monitor, hm.get('id'))
        if wait:
            self._wait_for_load_balancer_status(self.load_balancer.get('id'))
        return hm

    def _delete_health_monitor(self, health_monitor_id, wait=True):
        self.health_monitors_client.delete_health_monitor(health_monitor_id)
        if wait:
            self._wait_for_load_balancer_status(self.load_balancer.get('id'))

    def _update_health_monitor(self, health_monitor_id, wait=True,
                               **health_monitor_kwargs):
        health_monitor = self.health_monitors_client.update_health_monitor(
            health_monitor_id, **health_monitor_kwargs)
        if wait:
            self._wait_for_load_balancer_status(
                self.load_balancer.get('id'))
        return health_monitor

    @classmethod
    def _create_member(cls, pool_id, wait=True, **member_kwargs):
        member = cls.members_client.create_member(pool_id, **member_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))
        return member

    @classmethod
    def _delete_member(cls, pool_id, member_id, wait=True):
        cls.members_client.delete_member(pool_id, member_id)
        if wait:
            cls._wait_for_load_balancer_status(cls.load_balancer.get('id'))

    @classmethod
    def _update_member(cls, pool_id, member_id, wait=True,
                       **member_kwargs):
        member = cls.members_client.update_member(
            pool_id, member_id, **member_kwargs)
        if wait:
            cls._wait_for_load_balancer_status(
                cls.load_balancer.get('id'))
        return member

    @classmethod
    def _check_status_tree(cls, load_balancer_id, listener_ids=None,
                           pool_ids=None, health_monitor_id=None,
                           member_ids=None):
        statuses = cls.load_balancers_client.get_load_balancer_status_tree(
            load_balancer_id=load_balancer_id)
        load_balancer = statuses['loadbalancer']

        # When running with no-op drivers there is no actual health to
        # observe, so disable operating_status checks when running no-op.
        if not CONF.lbaas.test_with_noop:
            assert 'ONLINE' == load_balancer['operating_status']

        assert 'ACTIVE' == load_balancer['provisioning_status']

        if listener_ids:
            cls._check_status_tree_thing(listener_ids,
                                         load_balancer['listeners'])
        if pool_ids:
            cls._check_status_tree_thing(pool_ids,
                                         load_balancer['listeners']['pools'])
        if member_ids:
            cls._check_status_tree_thing(
                member_ids,
                load_balancer['listeners']['pools']['members'])
        if health_monitor_id:
            health_monitor = (
                load_balancer['listeners']['pools']['health_monitor'])
            assert health_monitor_id == health_monitor['id']
            assert 'ACTIVE' == health_monitor['provisioning_status']

    @classmethod
    def _check_status_tree_thing(cls, actual_thing_ids, status_tree_things):
        found_things = 0
        assert len(actual_thing_ids) == len(status_tree_things)
        for actual_thing_id in actual_thing_ids:
            for status_tree_thing in status_tree_things:
                if status_tree_thing['id'] == actual_thing_id:
                    # When running with no-op drivers there is no actual
                    # health to observe, so disable operating_status checks
                    # when running no-op.
                    if not CONF.lbaas.test_with_noop:
                        assert 'ONLINE' == (
                            status_tree_thing['operating_status'])
                    assert 'ACTIVE' == (
                        status_tree_thing['provisioning_status'])
                    found_things += 1
        assert len(actual_thing_ids) == found_things

    @classmethod
    def _get_full_case_name(cls):
        name = '{module}:{case_name}'.format(
            module=cls.__module__,
            case_name=cls.__name__
        )
        return name

    def _test_provisioning_status_if_exists(self, created_obj, get_obj):
        prov_status_old = created_obj.pop('provisioning_status', None)
        prov_status_new = get_obj.pop('provisioning_status', None)

        if prov_status_old:
            self.assertIn('PENDING_', prov_status_old)
        if prov_status_new:
            self.assertEqual(n_constants.ACTIVE, prov_status_new)
        if not created_obj.get('updated_at') and get_obj.get('updated_at'):
            get_obj['updated_at'] = None


class BaseAdminTestCase(BaseTestCase):

    # This class picks admin credentials and run the tempest tests

    @classmethod
    def resource_setup(cls):

        super(BaseAdminTestCase, cls).resource_setup()

        mgr = cls.get_client_manager(credential_type='admin')
        auth_provider_admin = mgr.auth_provider
        client_args = _setup_client_args(auth_provider_admin)

        cls.load_balancers_client = (
            load_balancers_client.LoadBalancersClientJSON(*client_args))
        cls.listeners_client = (
            listeners_client.ListenersClientJSON(*client_args))
        cls.pools_client = (
            pools_client.PoolsClientJSON(*client_args))
        cls.members_client = (
            members_client.MembersClientJSON(*client_args))
        cls.health_monitors_client = (
            health_monitors_client.HealthMonitorsClientJSON(*client_args))

    @classmethod
    def resource_cleanup(cls):
        super(BaseAdminTestCase, cls).resource_cleanup()
