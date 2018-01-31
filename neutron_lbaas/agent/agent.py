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

import sys

from neutron.common import config as common_config
from neutron.common import rpc as n_rpc
from neutron.conf.agent import common as config
from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import service

from neutron_lbaas._i18n import _
from neutron_lbaas.agent import agent_manager as manager
from neutron_lbaas.services.loadbalancer import constants

LOG = logging.getLogger(__name__)

OPTS = [
    cfg.IntOpt(
        'periodic_interval',
        default=10,
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Seconds between periodic task runs')
    )
]


class LbaasAgentService(n_rpc.Service):
    def start(self):
        super(LbaasAgentService, self).start()
        self.tg.add_timer(
            cfg.CONF.periodic_interval,
            self.manager.run_periodic_tasks,
            None,
            None
        )


def main():
    cfg.CONF.register_opts(OPTS)
    cfg.CONF.register_opts(manager.OPTS)
    # import interface options just in case the driver uses namespaces
    config.register_interface_opts(cfg.CONF)
    config.register_external_process_opts(cfg.CONF)
    config.register_interface_driver_opts_helper(cfg.CONF)
    config.register_agent_state_opts_helper(cfg.CONF)
    config.register_root_helper(cfg.CONF)

    common_config.init(sys.argv[1:])
    config.setup_logging()
    config.setup_privsep()

    LOG.warning('neutron-lbaas is now deprecated. See: '
                'https://wiki.openstack.org/wiki/Neutron/LBaaS/Deprecation')

    mgr = manager.LbaasAgentManager(cfg.CONF)
    svc = LbaasAgentService(
        host=cfg.CONF.host,
        topic=constants.LOADBALANCER_AGENTV2,
        manager=mgr
    )
    service.launch(cfg.CONF, svc).wait()
