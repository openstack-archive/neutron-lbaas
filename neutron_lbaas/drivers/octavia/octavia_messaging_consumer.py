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

from neutron_lbaas._i18n import _
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_messaging.rpc import dispatcher
from oslo_service import service


oslo_messaging_opts = [
    cfg.StrOpt('event_stream_topic',
               default='neutron_lbaas_event',
               deprecated_for_removal=True,
               deprecated_since='Queens',
               deprecated_reason='The neutron-lbaas project is now '
                                 'deprecated. See: https://wiki.openstack.org/'
                                 'wiki/Neutron/LBaaS/Deprecation',
               help=_('topic name for receiving events from a queue'))
]

cfg.CONF.register_opts(oslo_messaging_opts, group='oslo_messaging')


LOG = logging.getLogger(__name__)


class InfoContainer(object):
    @staticmethod
    def from_dict(dict_obj):
        return InfoContainer(dict_obj['info_type'],
                             dict_obj['info_id'],
                             dict_obj['info_payload'])

    def __init__(self, info_type, info_id, info_payload):
        self.info_type = info_type
        self.info_id = info_id
        self.info_payload = info_payload

    def to_dict(self):
        return {'info_type': self.info_type,
                'info_id': self.info_id,
                'info_payload': self.info_payload}

    def __eq__(self, other):
        if not isinstance(other, InfoContainer):
            return False
        if self.info_type != other.info_type:
            return False
        if self.info_id != other.info_id:
            return False
        if self.info_payload != other.info_payload:
            return False
        return True

    def __ne__(self, other):
        return not self == other


class ConsumerEndPoint(object):
    target = messaging.Target(namespace="control", version='1.0')

    def __init__(self, driver):
        self.driver = driver

    def update_info(self, ctx, container):
        LOG.debug("Received event from stream %s", container)
        container_inst = InfoContainer.from_dict(container)
        self.driver.handle_streamed_event(container_inst)


class OctaviaConsumer(service.Service):
    def __init__(self, driver, **kwargs):
        super(OctaviaConsumer, self).__init__(**kwargs)
        topic = cfg.CONF.oslo_messaging.event_stream_topic
        server = cfg.CONF.host
        self.driver = driver
        self.transport = messaging.get_rpc_transport(cfg.CONF)
        self.target = messaging.Target(topic=topic, server=server,
                                       exchange="common", fanout=False)
        self.endpoints = [ConsumerEndPoint(self.driver)]
        self.server = None

    def start(self):
        super(OctaviaConsumer, self).start()
        LOG.info("Starting octavia consumer...")
        access_policy = dispatcher.DefaultRPCAccessPolicy
        self.server = messaging.get_rpc_server(self.transport, self.target,
                                               self.endpoints,
                                               executor='eventlet',
                                               access_policy=access_policy)
        self.server.start()

    def stop(self, graceful=False):
        if self.server:
            LOG.info('Stopping consumer...')
            self.server.stop()
            if graceful:
                LOG.info(
                    ('Consumer successfully stopped.  Waiting for final '
                     'messages to be processed...'))
                self.server.wait()
        super(OctaviaConsumer, self).stop(graceful=graceful)

    def reset(self):
        if self.server:
            self.server.reset()
        super(OctaviaConsumer, self).reset()
