#  Copyright 2015, Shane McGough, KEMPtechnologies
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from oslo_config import cfg

from neutron_lbaas._i18n import _


KEMP_OPTS = [
    cfg.StrOpt('lm_address', default='192.168.0.1',
               help=_('Management address of the LoadMaster appliance.')),
    cfg.StrOpt('lm_username', default='bal',
               help=_('The management user. Default is bal.')),
    cfg.StrOpt('lm_password', default='1fourall', secret=True,
               help=_('Password for management user. Default is 1fourall.')),
    cfg.IntOpt('check_interval', default=9,
               help=_('The interval between real server health checks.')),
    cfg.IntOpt('connect_timeout', default=4,
               help=_('The time to wait for a real server to respond to a '
                      'health check request.')),
    cfg.IntOpt('retry_count', default=2,
               help=_('If a real server fails to respond to a health check '
                      'request. The LoadMaster will retry the specified '
                      'number of times.')),
]
