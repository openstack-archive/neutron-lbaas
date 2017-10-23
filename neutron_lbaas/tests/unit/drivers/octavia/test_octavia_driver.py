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

import copy

import mock
from neutron_lib import context
from oslo_config import cfg

from neutron_lbaas.common import exceptions
from neutron_lbaas.drivers.octavia import driver
from neutron_lbaas.services.loadbalancer import constants
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

    def delete_cascade(self, model, url):
        self.manager.delete_cascade(self.context, model)
        self.mocked_req.delete.assert_called_with(url)

    # TODO(Banashankar) : Complete refresh function. Need more info.
    def refresh(self):
        pass

    # TODO(Banashankar): Complete stats function. Need more info.
    def stats(self):
        pass


class BaseOctaviaDriverTest(test_db_loadbalancerv2.LbaasPluginDbTestCase):

    # Copied it from Brocade's test code :/
    def _create_fake_models(self, children=True, graph=False):
        # This id is used for all the entities.
        id = 'test_id'
        lb = data_models.LoadBalancer(id=id)
        if not children:
            return lb
        sni_container = data_models.SNI(listener_id=id)
        listener = data_models.Listener(id=id, loadbalancer=lb,
                                        sni_containers=[sni_container])
        pool = data_models.Pool(id=id, loadbalancer=lb)
        member = data_models.Member(id=id, pool=pool)
        hm = data_models.HealthMonitor(id=id, pool=pool)
        sp = data_models.SessionPersistence(pool_id=pool.id, pool=pool)
        l7policy = data_models.L7Policy(
            id=id, listener=listener, listener_id=listener.id,
            action=constants.L7_POLICY_ACTION_REDIRECT_TO_POOL)
        l7rule = data_models.L7Rule(
            id=id, policy=l7policy, type=constants.L7_RULE_TYPE_PATH,
            compare_type=constants.L7_RULE_COMPARE_TYPE_STARTS_WITH,
            value='/api')
        lb.listeners = [listener]
        lb.pools = [pool]
        if graph:
            r_pool = data_models.Pool(id=id, loadbalancer=lb)
            r_member = data_models.Member(id=id, pool=r_pool)
            r_pool.members = [r_member]
            l7policy.redirect_pool = r_pool
            l7policy.redirect_pool_id = r_pool.id
            lb.pools.append(r_pool)
        else:
            l7policy.redirect_pool = pool
            l7policy.redirect_pool_id = pool.id
        listener.default_pool = pool
        listener.l7_policies = [l7policy]
        l7policy.rules = [l7rule]
        pool.members = [member]
        pool.session_persistence = sp
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

    def test_create_load_balancer_graph(self):
        m = ManagerTest(self, self.driver.load_balancer,
                        self.driver.req)
        lb = self._create_fake_models(children=True, graph=True)
        listener = lb.listeners[0]
        sni_container = listener.sni_containers[0]
        policy = listener.l7_policies[0]
        r_pool = policy.redirect_pool
        r_member = r_pool.members[0]
        rule = policy.rules[0]
        pool = listener.default_pool
        member = pool.members[0]
        sp = pool.session_persistence
        hm = pool.healthmonitor

        lb_url = '/v1/loadbalancers'

        args = {
            "id": lb.id,
            "name": lb.name,
            "enabled": lb.admin_state_up,
            "vip": {
                "subnet_id": lb.vip_subnet_id,
                "port_id": lb.vip_port_id,
                "ip_address": lb.vip_address
            },
            "listeners": [{
                "id": listener.id,
                "protocol": listener.protocol,
                "enabled": listener.admin_state_up,
                "sni_containers": [sni_container.tls_container_id],
                "tls_certificate_id": listener.default_tls_container_id,
                "l7policies": [{
                    "id": policy.id,
                    "name": policy.name,
                    "redirect_pool": {
                        "id": r_pool.id,
                        "lb_algorithm": r_pool.lb_algorithm,
                        "protocol": r_pool.protocol,
                        "name": r_pool.name,
                        "enabled": r_pool.admin_state_up,
                        "session_persistence": r_pool.session_persistence,
                        "members": [{
                            "project_id": r_member.tenant_id,
                            "weight": r_member.weight,
                            "subnet_id": r_member.subnet_id,
                            "ip_address": r_member.address,
                            "protocol_port": r_member.protocol_port,
                            "enabled": r_member.admin_state_up,
                            "id": r_member.id
                        }],
                        "project_id": r_pool.tenant_id,
                        "description": r_pool.description
                    },
                    "l7rules": [{
                        "id": rule.id,
                        "type": rule.type,
                        "compare_type": rule.compare_type,
                        "key": rule.key,
                        "value": rule.value,
                        "invert": rule.invert
                    }],
                    "enabled": policy.admin_state_up,
                    "action": policy.action,
                    "position": policy.position,
                    "description": policy.description
                }],
                "name": listener.name,
                "description": listener.description,
                "default_pool": {
                    "id": pool.id,
                    "lb_algorithm": pool.lb_algorithm,
                    "protocol": pool.protocol,
                    "name": pool.name,
                    "enabled": pool.admin_state_up,
                    "session_persistence": {
                        "cookie_name": sp.cookie_name,
                        "type": sp.type
                    },
                    "members": [{
                        "project_id": member.tenant_id,
                        "weight": member.weight,
                        "subnet_id": member.subnet_id,
                        "ip_address": member.address,
                        "protocol_port": member.protocol_port,
                        "enabled": member.admin_state_up,
                        "id": member.id
                    }],
                    "health_monitor": {
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
                    },
                    "project_id": pool.tenant_id,
                    "description": pool.description
                },
                "connection_limit": listener.connection_limit,
                "protocol_port": listener.protocol_port,
                "project_id": listener.tenant_id
            }],
            "project_id": lb.tenant_id,
            "description": lb.description
        }

        m.create(lb, lb_url, args)

    def test_load_balancer_ops(self):
        m = ManagerTest(self, self.driver.load_balancer,
                        self.driver.req)

        lb = self._create_fake_models(children=False)

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
        args = {
            'name': lb.name,
            'description': lb.description,
            'enabled': lb.admin_state_up,
        }
        m.update(lb, lb, lb_url_id, args)

        # delete LB test
        m.delete_cascade(lb, lb_url_id + '/delete_cascade')

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
            'default_pool_id': listener.default_pool_id,
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
        pool_url = '/v1/loadbalancers/%s/pools' % (
            pool.loadbalancer.id)
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
        else:
            args['session_persistence'] = None
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
        mem_url = '/v1/loadbalancers/%s/pools/%s/members' % (
            member.pool.loadbalancer.id,
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
        hm_url = '/v1/loadbalancers/%s/pools/%s/healthmonitor' % (
            hm.pool.loadbalancer.id,
            hm.pool.id)

        # Test HM create.
        # args for create and update assert.
        args = {
            'type': hm.type,
            'delay': hm.delay,
            'timeout': hm.timeout,
            'rise_threshold': hm.max_retries,
            'fall_threshold': hm.max_retries_down,
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

    def test_l7_policy_ops_reject(self):
        m = ManagerTest(self, self.driver.l7policy,
                        self.driver.req)

        l7p = copy.deepcopy(self.lb.listeners[0].l7_policies[0])
        l7p.action = constants.L7_POLICY_ACTION_REJECT

        # urls for assert.
        l7p_url = '/v1/loadbalancers/%s/listeners/%s/l7policies' % (
            l7p.listener.loadbalancer.id,
            l7p.listener.id)
        l7p_url_id = l7p_url + "/%s" % l7p.id

        # Test L7Policy create.
        # args for create and update assert.
        args = {
            'id': l7p.id,
            'name': l7p.name,
            'description': l7p.description,
            'action': constants.L7_POLICY_ACTION_REJECT,
            'position': l7p.position,
            'enabled': l7p.admin_state_up
        }
        m.create(l7p, l7p_url, args)

        # Test L7Policy update
        del args['id']
        m.update(l7p, l7p, l7p_url_id, args)

        # Test L7Policy delete
        m.delete(l7p, l7p_url_id)

    def test_l7_policy_ops_rdr_pool(self):
        m = ManagerTest(self, self.driver.l7policy,
                        self.driver.req)

        l7p = copy.deepcopy(self.lb.listeners[0].l7_policies[0])
        l7p.action = constants.L7_POLICY_ACTION_REDIRECT_TO_POOL

        # urls for assert.
        l7p_url = '/v1/loadbalancers/%s/listeners/%s/l7policies' % (
            l7p.listener.loadbalancer.id,
            l7p.listener.id)
        l7p_url_id = l7p_url + "/%s" % l7p.id

        # Test L7Policy create.
        # args for create and update assert.
        args = {
            'id': l7p.id,
            'name': l7p.name,
            'description': l7p.description,
            'action': constants.L7_POLICY_ACTION_REDIRECT_TO_POOL,
            'redirect_pool_id': l7p.redirect_pool_id,
            'position': l7p.position,
            'enabled': l7p.admin_state_up
        }
        m.create(l7p, l7p_url, args)

        # Test L7Policy update
        del args['id']
        m.update(l7p, l7p, l7p_url_id, args)

        # Test L7Policy delete
        m.delete(l7p, l7p_url_id)

    def test_l7_policy_ops_rdr_url(self):
        m = ManagerTest(self, self.driver.l7policy,
                        self.driver.req)

        l7p = copy.deepcopy(self.lb.listeners[0].l7_policies[0])
        l7p.action = constants.L7_POLICY_ACTION_REDIRECT_TO_URL

        # urls for assert.
        l7p_url = '/v1/loadbalancers/%s/listeners/%s/l7policies' % (
            l7p.listener.loadbalancer.id,
            l7p.listener.id)
        l7p_url_id = l7p_url + "/%s" % l7p.id

        # Test L7Policy create.
        # args for create and update assert.
        args = {
            'id': l7p.id,
            'name': l7p.name,
            'description': l7p.description,
            'action': constants.L7_POLICY_ACTION_REDIRECT_TO_URL,
            'redirect_url': l7p.redirect_url,
            'position': l7p.position,
            'enabled': l7p.admin_state_up
        }
        m.create(l7p, l7p_url, args)

        # Test L7Policy update
        del args['id']
        m.update(l7p, l7p, l7p_url_id, args)

        # Test L7Policy delete
        m.delete(l7p, l7p_url_id)

    def test_l7_rule_ops(self):
        m = ManagerTest(self, self.driver.l7rule,
                        self.driver.req)

        l7r = self.lb.listeners[0].l7_policies[0].rules[0]

        # urls for assert.
        l7r_url = '/v1/loadbalancers/%s/listeners/%s/l7policies/%s/l7rules' % (
            l7r.policy.listener.loadbalancer.id,
            l7r.policy.listener.id,
            l7r.policy.id)
        l7r_url_id = l7r_url + "/%s" % l7r.id

        # Test L7Rule create.
        # args for create and update assert.
        args = {
            'id': l7r.id,
            'type': l7r.type,
            'compare_type': l7r.compare_type,
            'key': l7r.key,
            'value': l7r.value,
            'invert': l7r.invert
        }
        m.create(l7r, l7r_url, args)

        # Test L7rule update
        del args['id']
        m.update(l7r, l7r, l7r_url_id, args)

        # Test L7Rule delete
        m.delete(l7r, l7r_url_id)


class TestThreadedDriver(BaseOctaviaDriverTest):

        def setUp(self):
            super(TestThreadedDriver, self).setUp()
            cfg.CONF.set_override('request_poll_interval', 1, group='octavia')
            cfg.CONF.set_override('request_poll_timeout', 5, group='octavia')
            self.driver.req.get = mock.MagicMock()
            self.succ_completion = mock.MagicMock()
            self.fail_completion = mock.MagicMock()
            self.context = mock.MagicMock()
            ctx_patcher = mock.patch('neutron_lib.context.get_admin_context',
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


class TestOctaviaRequest(test_db_loadbalancerv2.LbaasPluginDbTestCase):

    def setUp(self):
        super(TestOctaviaRequest, self).setUp()
        self.OctaviaRequestObj = driver.OctaviaRequest("TEST_URL",
                                                       "TEST_SESSION")

    @mock.patch('requests.request')
    def test_request(self, mock_requests):
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.content = "TEST"
        mock_response.headers = "TEST headers"
        mock_response.json.return_value = "TEST json"

        mock_requests.return_value = mock_response

        fake_header = {'X-Auth-Token': "TEST_TOKEN"}
        result = self.OctaviaRequestObj.request("TEST_METHOD", "TEST_URL",
                                                headers=fake_header)

        self.assertEqual("TEST json", result)

    @mock.patch('requests.request')
    def _test_request_Octavia(self, status_code, exception, mock_requests):
        mock_response = mock.MagicMock()
        mock_response.status_code = status_code
        mock_response.content = '{"faultstring": "FAILED"}'
        mock_response.headers = "TEST headers"

        mock_requests.return_value = mock_response

        fake_header = {'X-Auth-Token': "TEST_TOKEN"}
        self.assertRaisesRegex(exception,
                               "FAILED",
                               self.OctaviaRequestObj.request,
                               "TEST_METHOD", "TEST_URL", headers=fake_header)

        mock_response.json.assert_not_called()

    def test_request_Octavia_400(self):
        self._test_request_Octavia(400, exceptions.BadRequestException)

    def test_request_Octavia_401(self):
        self._test_request_Octavia(401, exceptions.NotAuthorizedException)

    def test_request_Octavia_403(self):
        self._test_request_Octavia(403, exceptions.NotAuthorizedException)

    def test_request_Octavia_404(self):
        self._test_request_Octavia(404, exceptions.NotFoundException)

    def test_request_Octavia_409(self):
        self._test_request_Octavia(409, exceptions.ConflictException)

    def test_request_Octavia_500(self):
        self._test_request_Octavia(500, exceptions.UnknownException)

    def test_request_Octavia_503(self):
        self._test_request_Octavia(503, exceptions.ServiceUnavailableException)
