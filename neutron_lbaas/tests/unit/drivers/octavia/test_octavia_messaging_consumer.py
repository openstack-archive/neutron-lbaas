# Copyright 2016 Rackspace
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
from oslo_messaging.rpc import dispatcher

from neutron_lbaas.common import exceptions
from neutron_lbaas.db.loadbalancer import models
import neutron_lbaas.drivers.octavia.driver as odriver
from neutron_lbaas.drivers.octavia.driver import octavia_messaging_consumer
from neutron_lbaas.services.loadbalancer import constants
from neutron_lbaas.tests.unit.drivers.octavia import test_octavia_driver

InfoContainer = octavia_messaging_consumer.InfoContainer


class TestOctaviaMessagingConsumer(test_octavia_driver.BaseOctaviaDriverTest):
    def setUp(self):
        super(test_octavia_driver.BaseOctaviaDriverTest, self).setUp()
        self.plugin = mock.Mock()
        self.driver = odriver.OctaviaDriver(self.plugin)

    def assert_handle_streamed_event_called(self, model_class, id_param,
                                            payload):
        call_args_list = self.driver.plugin.db.update_status.call_args_list[0]
        self.assertEqual(len(call_args_list), 2)
        self.assertEqual(len(call_args_list[0]), 3)
        self.assertEqual(model_class, call_args_list[0][1])
        self.assertEqual(call_args_list[0][2], id_param)
        self.assertEqual(call_args_list[1], payload)

    def test_info_container_constructor(self):
        ID = 'test_id'
        PAYLOAD = 'test_payload'
        TYPE = 'test_type'
        cnt = InfoContainer(TYPE, ID, PAYLOAD)
        self.assertEqual(cnt.info_type, TYPE)
        self.assertEqual(cnt.info_id, ID)
        self.assertEqual(cnt.info_payload, PAYLOAD)
        self.assertEqual(cnt.to_dict(), {'info_type': TYPE, 'info_id': ID,
        'info_payload': PAYLOAD})

    def test_info_container_from_dict(self):
        ID = 'test_id'
        PAYLOAD = 'test_payload'
        TYPE = 'test_type'
        cnt = InfoContainer.from_dict({'info_type': TYPE, 'info_id': ID,
        'info_payload': PAYLOAD})
        self.assertEqual(cnt.info_type, TYPE)
        self.assertEqual(cnt.info_id, ID)
        self.assertEqual(cnt.info_payload, PAYLOAD)

    def test_set_consumer_topic(self):
        TOPIC = 'neutron_lbaas_event'
        self.addCleanup(cfg.CONF.clear_override, 'event_stream_topic',
                        group='oslo_messaging')
        cfg.CONF.set_override('event_stream_topic', TOPIC,
                              group='oslo_messaging')
        consumer = octavia_messaging_consumer.OctaviaConsumer(self.driver)
        self.assertIsNotNone(consumer.transport)
        self.assertEqual(TOPIC, consumer.target.topic)
        self.assertEqual(cfg.CONF.host, consumer.target.server)

    @mock.patch.object(octavia_messaging_consumer.messaging, 'get_rpc_server')
    def test_consumer_start(self, mock_get_rpc_server):
        mock_server = mock.Mock()
        mock_get_rpc_server.return_value = mock_server
        TOPIC = 'neutron_lbaas_event'
        self.addCleanup(cfg.CONF.clear_override, 'event_stream_topic',
                        group='oslo_messaging')
        cfg.CONF.set_override('event_stream_topic', TOPIC,
                              group='oslo_messaging')
        consumer = octavia_messaging_consumer.OctaviaConsumer(self.driver)
        consumer.start()
        access_policy = dispatcher.DefaultRPCAccessPolicy
        mock_get_rpc_server.assert_called_once_with(
            consumer.transport, consumer.target, consumer.endpoints,
            executor='eventlet', access_policy=access_policy
        )
        mock_server.start.assert_called_once_with()

    @mock.patch.object(octavia_messaging_consumer.messaging, 'get_rpc_server')
    def test_consumer_stop(self, mock_get_rpc_server):
        mock_server = mock.Mock()
        mock_get_rpc_server.return_value = mock_server
        consumer = octavia_messaging_consumer.OctaviaConsumer(self.driver)
        consumer.start()
        consumer.stop()
        mock_server.stop.assert_called_once_with()
        mock_server.wait.assert_not_called()

    @mock.patch.object(octavia_messaging_consumer.messaging, 'get_rpc_server')
    def test_consumer_graceful_stop(self, mock_get_rpc_server):
        mock_server = mock.Mock()
        mock_get_rpc_server.return_value = mock_server
        consumer = octavia_messaging_consumer.OctaviaConsumer(self.driver)
        consumer.start()
        consumer.stop(graceful=True)
        mock_server.stop.assert_called_once_with()
        mock_server.wait.assert_called_once_with()

    @mock.patch.object(octavia_messaging_consumer.messaging, 'get_rpc_server')
    def test_consumer_reset(self, mock_get_rpc_server):
        mock_server = mock.Mock()
        mock_get_rpc_server.return_value = mock_server
        consumer = octavia_messaging_consumer.OctaviaConsumer(self.driver)
        consumer.start()
        consumer.reset()
        mock_server.reset.assert_called_once_with()

    def set_db_mocks(self):
        TOPIC = 'neutron_lbaas_event'
        self.addCleanup(cfg.CONF.clear_override, 'event_stream_topic',
                        group='oslo_messaging')
        cfg.CONF.set_override('event_stream_topic', TOPIC,
                              group='oslo_messaging')
        self.payload = {'operating_status': 'ONLINE'}
        self.consumer = octavia_messaging_consumer.OctaviaConsumer(
            self.driver)

    def test_updatedb_with_raises_exception_with_bad_model_name(self):
        self.set_db_mocks()

        cnt = InfoContainer('listener_statsX', 'id',
                            self.payload).to_dict()
        self.assertRaises(exceptions.ModelMapException,
                          self.consumer.endpoints[0].update_info, {}, cnt)

    def test_update_loadbalancer_stats(self):
        self.set_db_mocks()
        stats = {
            'bytes_in': 1,
            'bytes_out': 2,
            'active_connections': 3,
            'total_connections': 4,
            'request_errors': 5,
        }
        cnt = InfoContainer(constants.LOADBALANCER_STATS_EVENT, 'lb_id',
                            stats).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        self.driver.plugin.db.update_loadbalancer_stats.assert_called_with(
            mock.ANY, 'lb_id', stats)

    def test_updatedb_ignores_listener_stats(self):
        self.set_db_mocks()
        cnt = InfoContainer('listener_stats', 'id', self.payload).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        call_len = len(self.driver.plugin.db.update_status.call_args_list)
        self.assertEqual(call_len, 0)   # See didn't do anything

    def test_updatedb_loadbalancer(self):
        self.set_db_mocks()
        cnt = InfoContainer(constants.LOADBALANCER_EVENT, 'lb_id',
                            self.payload).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        self.assert_handle_streamed_event_called(models.LoadBalancer, 'lb_id',
                                                 self.payload)

    def test_updatedb_listener(self):
        self.set_db_mocks()
        cnt = InfoContainer(constants.LISTENER_EVENT, 'listener_id',
                            self.payload).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        self.assert_handle_streamed_event_called(models.Listener,
                                                 'listener_id',
                                                 self.payload)

    def test_updatedb_pool(self):
        self.set_db_mocks()
        cnt = InfoContainer(constants.POOL_EVENT, 'pool_id',
                            self.payload).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        self.assert_handle_streamed_event_called(models.PoolV2, 'pool_id',
                                                 self.payload)

    def test_updatedb_member(self):
        self.set_db_mocks()
        cnt = InfoContainer(constants.MEMBER_EVENT, 'pool_id',
                            self.payload).to_dict()
        self.consumer.endpoints[0].update_info({}, cnt)
        self.assert_handle_streamed_event_called(models.MemberV2, 'pool_id',
                                                 self.payload)
