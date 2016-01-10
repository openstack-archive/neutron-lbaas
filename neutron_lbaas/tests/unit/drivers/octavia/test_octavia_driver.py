# Copyright 2015, Banashankar Veerad, Copyright IBM Corporation
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
from oslo_config import cfg

from neutron import context
from neutron_lbaas.drivers.octavia import driver
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.db.loadbalancer import test_db_loadbalancerv2


class ManagerTest(object):
    def __init__(self, parent, manager, mocked_req):
        self.parent = parent
        self.context = parent.context
        self.driver = parent.driver
        self.manager = manager
        self.mocked_req = mocked_req

    def create(self, model, url, args):
        self.manager.create(self.context, model)
        self.mocked_req.post.assert_called_with(url, args)

    def update(self, old_model, model, url, args):
        self.manager.update(self.context, old_model, model)
        self.mocked_req.put.assert_called_with(url, args)

    def delete(self, model, url):
        self.manager.delete(self.context, model)
        self.mocked_req.delete.assert_called_with(url)

    # TODO(Banashankar) : Complete refresh function. Need more info.
    def refresh(self):
        pass

    # TODO(Banashankar): Complete stats function. Need more info.
    def stats(self):
        pass


class BaseOctaviaDriverTest(test_db_loadbalancerv2.LbaasPluginDbTestCase):

    # Copied it from Brocade's test code :/
    def _create_fake_models(self):
        # This id is used for all the entities.
        id = 'test_id'
        lb = data_models.LoadBalancer(id=id)
        sni_container = data_models.SNI(listener_id=id)
        listener = data_models.Listener(id=id, loadbalancer=lb,
                                        sni_containers=[sni_container])
        pool = data_models.Pool(id=id, listener=listener)
        member = data_models.Member(id=id, pool=pool)
        hm = data_models.HealthMonitor(id=id, pool=pool)
        lb.listeners = [listener]
        listener.default_pool = pool
        pool.members = [member]
        pool.healthmonitor = hm
        return lb

    def setUp(self):
        super(BaseOctaviaDriverTest, self).setUp()
        self.context = context.get_admin_context()
        self.plugin = mock.Mock()
        self.driver = driver.OctaviaDriver(self.plugin)
        # mock of rest call.
        self.driver.req = mock.Mock()
        self.lb = self._create_fake_models()


class TestOctaviaDriver(BaseOctaviaDriverTest):

    def test_allocates_vip(self):
        self.addCleanup(cfg.CONF.clear_override,
                        'allocates_vip', group='octavia')
        cfg.CONF.set_override('allocates_vip', True, group='octavia')
        test_driver = driver.OctaviaDriver(self.plugin)
        self.assertTrue(test_driver.load_balancer.allocates_vip)

    def test_load_balancer_ops(self):
        m = ManagerTest(self, self.driver.load_balancer,
                        self.driver.req)

        lb = self.lb

        # urls for assert test.
        lb_url = '/v1/loadbalancers'
        lb_url_id = '/v1/loadbalancers/' + lb.id

        # Create LB test
        # args for create assert.
        args = {
            'id': lb.id,
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
            'project_id': lb.tenant_id,
            'vip': {
                'subnet_id': lb.vip_subnet_id,
                'ip_address': lb.vip_address,
                'port_id': lb.vip_port_id,
            }
        }
        m.create(lb, lb_url, args)

        # Update LB test
        # args for update assert.
        args = args = {
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
        }
        m.update(lb, lb, lb_url_id, args)

        # delete LB test
        m.delete(lb, lb_url_id)

        # TODO(Banashankar) : refresh n stats fucntions are not yet done.
        #m.refresh()
        #m.stats()

    def test_listener_ops(self):
        m = ManagerTest(self, self.driver.listener,
                        self.driver.req)

        listener = self.lb.listeners[0]

        # urls for assert test.
        list_url = '/v1/loadbalancers/%s/listeners' % listener.loadbalancer.id
        list_url_id = list_url + '/%s' % (listener.id)

        # Create Listener test.
        # args for create and update assert.
        sni_containers = [sni.tls_container_id
                          for sni in listener.sni_containers]
        args = {
            'id': listener.id,
            'name': listener.name,
            'description': listener.description,
            'enabled': listener.admin_state_up,
            'protocol': listener.protocol,
            'protocol_port': listener.protocol_port,
            'connection_limit': listener.connection_limit,
            'tls_certificate_id': listener.default_tls_container_id,
            'sni_containers': sni_containers,
            'project_id': listener.tenant_id
        }
        m.create(listener, list_url, args)

        # Update listener test.
        del args['id']
        del args['project_id']
        m.update(listener, listener, list_url_id, args)

        # Delete listener.
        m.delete(listener, list_url_id)

    def test_pool_ops(self):
        m = ManagerTest(self, self.driver.pool,
                        self.driver.req)

        pool = self.lb.listeners[0].default_pool

        # urls for assert test.
        pool_url = '/v1/loadbalancers/%s/listeners/%s/pools' % (
            pool.listener.loadbalancer.id,
            pool.listener.id)
        pool_url_id = pool_url + "/%s" % pool.id

        # Test create pool.
        # args for create and update assert.
        args = {
            'id': pool.id,
            'name': pool.name,
            'description': pool.description,
            'enabled': pool.admin_state_up,
            'protocol': pool.protocol,
            'lb_algorithm': pool.lb_algorithm,
            'project_id': pool.tenant_id
        }
        if pool.session_persistence:
            args['session_persistence'] = {
                'type': pool.session_persistence.type,
                'cookie_name': pool.session_persistence.cookie_name,
            }
        m.create(pool, pool_url, args)

        # Test update pool.
        del args['id']
        del args['project_id']
        m.update(pool, pool, pool_url_id, args)

        # Test pool delete.
        m.delete(pool, pool_url_id)

    def test_member_ops(self):
        m = ManagerTest(self, self.driver.member,
                        self.driver.req)

        member = self.lb.listeners[0].default_pool.members[0]

        # urls for assert.
        mem_url = '/v1/loadbalancers/%s/listeners/%s/pools/%s/members' % (
            member.pool.listener.loadbalancer.id,
            member.pool.listener.id,
            member.pool.id)
        mem_url_id = mem_url + "/%s" % member.id

        # Test Create member.
        # args for create assert.
        args = {
            'id': member.id,
            'enabled': member.admin_state_up,
            'ip_address': member.address,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
            'subnet_id': member.subnet_id,
            'project_id': member.tenant_id
        }
        m.create(member, mem_url, args)

        # Test member update.
        # args for update assert.
        args = {
            'enabled': member.admin_state_up,
            'protocol_port': member.protocol_port,
            'weight': member.weight,
        }
        m.update(member, member, mem_url_id, args)

        # Test member delete.
        m.delete(member, mem_url_id)

    def test_health_monitor_ops(self):
        m = ManagerTest(self, self.driver.health_monitor,
                        self.driver.req)

        hm = self.lb.listeners[0].default_pool.healthmonitor

        # urls for assert.
        hm_url = '/v1/loadbalancers/%s/listeners/%s/pools/%s/healthmonitor' % (
            hm.pool.listener.loadbalancer.id,
            hm.pool.listener.id,
            hm.pool.id)

        # Test HM create.
        # args for create and update assert.
        args = {
            'type': hm.type,
            'delay': hm.delay,
            'timeout': hm.timeout,
            'rise_threshold': hm.max_retries,
            'fall_threshold': hm.max_retries,
            'http_method': hm.http_method,
            'url_path': hm.url_path,
            'expected_codes': hm.expected_codes,
            'enabled': hm.admin_state_up,
            'project_id': hm.tenant_id
        }
        m.create(hm, hm_url, args)

        # Test HM update
        del args['project_id']
        m.update(hm, hm, hm_url, args)

        # Test HM delete
        m.delete(hm, hm_url)


class TestThreadedDriver(BaseOctaviaDriverTest):

        def setUp(self):
            super(TestThreadedDriver, self).setUp()
            cfg.CONF.set_override('request_poll_interval', 1, group='octavia')
            cfg.CONF.set_override('request_poll_timeout', 5, group='octavia')
            self.driver.req.get = mock.MagicMock()
            self.succ_completion = mock.MagicMock()
            self.fail_completion = mock.MagicMock()
            self.context = mock.MagicMock()
            ctx_patcher = mock.patch('neutron.context.get_admin_context',
                                     return_value=self.context)
            ctx_patcher.start()
            self.addCleanup(ctx_patcher.stop)
            self.driver.load_balancer.successful_completion = (
                self.succ_completion)
            self.driver.load_balancer.failed_completion = self.fail_completion

        def test_thread_op_goes_active(self):
            self.driver.req.get.side_effect = [
                {'provisioning_status': 'PENDING_CREATE'},
                {'provisioning_status': 'ACTIVE'}
            ]
            driver.thread_op(self.driver.load_balancer, self.lb)
            self.succ_completion.assert_called_once_with(self.context, self.lb,
                                                         delete=False)
            self.assertEqual(0, self.fail_completion.call_count)

        def test_thread_op_goes_deleted(self):
            self.driver.req.get.side_effect = [
                {'provisioning_status': 'PENDING_DELETE'},
                {'provisioning_status': 'DELETED'}
            ]
            driver.thread_op(self.driver.load_balancer, self.lb, delete=True)
            self.succ_completion.assert_called_once_with(self.context, self.lb,
                                                         delete=True)
            self.assertEqual(0, self.fail_completion.call_count)

        def test_thread_op_goes_error(self):
            self.driver.req.get.side_effect = [
                {'provisioning_status': 'PENDING_CREATE'},
                {'provisioning_status': 'ERROR'}
            ]
            driver.thread_op(self.driver.load_balancer, self.lb)
            self.fail_completion.assert_called_once_with(self.context, self.lb)
            self.assertEqual(0, self.succ_completion.call_count)

        def test_thread_op_a_times_out(self):
            cfg.CONF.set_override('request_poll_timeout', 1, group='octavia')
            self.driver.req.get.side_effect = [
                {'provisioning_status': 'PENDING_CREATE'}
            ]
            driver.thread_op(self.driver.load_balancer, self.lb)
            self.fail_completion.assert_called_once_with(self.context, self.lb)
            self.assertEqual(0, self.succ_completion.call_count)

        def test_thread_op_updates_vip_when_vip_delegated(self):
            cfg.CONF.set_override('allocates_vip', True, group='octavia')
            expected_vip = '10.1.1.1'
            self.driver.req.get.side_effect = [
                {'provisioning_status': 'PENDING_CREATE',
                 'vip': {'ip_address': ''}},
                {'provisioning_status': 'ACTIVE',
                 'vip': {'ip_address': expected_vip}}
            ]
            driver.thread_op(self.driver.load_balancer,
                             self.lb,
                             lb_create=True)
            self.succ_completion.assert_called_once_with(self.context, self.lb,
                                                         delete=False,
                                                         lb_create=True)
            self.assertEqual(expected_vip, self.lb.vip_address)
