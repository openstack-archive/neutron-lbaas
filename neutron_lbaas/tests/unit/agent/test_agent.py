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

import mock
from oslo_config import cfg

from neutron_lbaas.agent import agent
from neutron_lbaas.tests import base


class TestLbaasService(base.BaseTestCase):
    def test_start(self):
        with mock.patch.object(
            agent.n_rpc.Service, 'start'
        ) as mock_start:

            mgr = mock.Mock()
            cfg.CONF.periodic_interval = mock.Mock(return_value=10)
            agent_service = agent.LbaasAgentService('host', 'topic', mgr)
            agent_service.start()

            self.assertTrue(mock_start.called)

    def test_main(self):
        logging_str = 'neutron.conf.agent.common.setup_logging'
        privsep_str = 'neutron.conf.agent.common.setup_privsep'
        with mock.patch(logging_str), \
                mock.patch(privsep_str), \
                mock.patch.object(agent.service, 'launch') as mock_launch, \
                mock.patch('sys.argv'), \
                mock.patch.object(agent.manager, 'LbaasAgentManager'), \
                mock.patch.object(cfg.CONF, 'register_opts'):
            agent.main()

            mock_launch.assert_called_once_with(mock.ANY, mock.ANY)
