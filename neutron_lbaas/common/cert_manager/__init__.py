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

from oslo_config import cfg
from stevedore import driver

CONF = cfg.CONF

CERT_MANAGER_DEFAULT = 'barbican'

cert_manager_opts = [
    cfg.StrOpt('cert_manager_type',
               default=CERT_MANAGER_DEFAULT,
               deprecated_for_removal=True,
               deprecated_since='Queens',
               deprecated_reason='The neutron-lbaas project is now '
                                 'deprecated. See: https://wiki.openstack.org/'
                                 'wiki/Neutron/LBaaS/Deprecation',
               help='Certificate Manager plugin. '
                    'Defaults to {0}.'.format(CERT_MANAGER_DEFAULT)),
    cfg.StrOpt('barbican_auth',
               default='barbican_acl_auth',
               deprecated_for_removal=True,
               deprecated_since='Queens',
               deprecated_reason='The neutron-lbaas project is now '
                                 'deprecated. See: https://wiki.openstack.org/'
                                 'wiki/Neutron/LBaaS/Deprecation',
               help='Name of the Barbican authentication method to use')
]

CONF.register_opts(cert_manager_opts, group='certificates')

_CERT_MANAGER_PLUGIN = None


def get_backend():
    global _CERT_MANAGER_PLUGIN
    if not _CERT_MANAGER_PLUGIN:
        _CERT_MANAGER_PLUGIN = driver.DriverManager(
            "neutron_lbaas.cert_manager.backend",
            cfg.CONF.certificates.cert_manager_type).driver
    return _CERT_MANAGER_PLUGIN
