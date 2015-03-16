# Copyright 2015 Rackspace US, Inc.
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

import importlib

from oslo_config import cfg

CONF = cfg.CONF

CERT_MANAGER_DEFAULT = ('neutron_lbaas.common.cert_manager.'
                        'barbican_cert_manager')

cert_manager_opts = [
    cfg.StrOpt('cert_manager_class',
               default=CERT_MANAGER_DEFAULT,
               help='Certificate Manager plugin. '
                    'Defaults to {0}.'.format(CERT_MANAGER_DEFAULT))
]

CONF.register_opts(cert_manager_opts, group='certificates')

# Use CERT_MANAGER_PLUGIN.CertManager and CERT_MANAGER_PLUGIN.Cert to reference
#   the Certificate plugin chosen via the service configuration.
# TODO(rm_work): Investigate using Stevedore here.
CERT_MANAGER_PLUGIN = importlib.import_module(
    CONF.certificates.cert_manager_class
)
