#    Copyright 2015 Rackspace
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

from keystoneauth1.identity import v2 as v2_client
from keystoneauth1.identity import v3 as v3_client
from keystoneauth1 import session
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from neutron_lbaas._i18n import _


LOG = logging.getLogger(__name__)

_SESSION = None
OPTS = [
    cfg.StrOpt(
        'auth_url',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Authentication endpoint'),
    ),
    cfg.StrOpt(
        'admin_user',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='admin',
        help=_('The service admin user name'),
    ),
    cfg.StrOpt(
        'admin_tenant_name',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='admin',
        help=_('The service admin tenant name'),
    ),
    cfg.StrOpt(
        'admin_password',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        secret=True,
        default='password',
        help=_('The service admin password'),
    ),
    cfg.StrOpt(
        'admin_user_domain',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='Default',
        help=_('The admin user domain name'),
    ),
    cfg.StrOpt(
        'admin_project_domain',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='Default',
        help=_('The admin project domain name'),
    ),
    cfg.StrOpt(
        'region',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='RegionOne',
        help=_('The deployment region'),
    ),
    cfg.StrOpt(
        'service_name',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='lbaas',
        help=_('The name of the service'),
    ),
    cfg.StrOpt(
        'auth_version',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='3',
        help=_('The auth version used to authenticate'),
    ),
    cfg.StrOpt(
        'endpoint_type',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default='public',
        help=_('The endpoint_type to be used')
    ),
    cfg.BoolOpt(
        'insecure',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        default=False,
        help=_('Disable server certificate verification')
    ),
    cfg.StrOpt(
        'cafile',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('CA certificate file path')
    ),
    cfg.StrOpt(
        'certfile',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Client certificate cert file path')
    ),
    cfg.StrOpt(
        'keyfile',
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Client certificate key file path')
    )
]

cfg.CONF.register_opts(OPTS, 'service_auth')


def get_session():
    """Initializes a Keystone session.

    :returns: a Keystone Session object
    :raises Exception: if the session cannot be established
    """
    global _SESSION
    if not _SESSION:

        auth_url = cfg.CONF.service_auth.auth_url
        insecure = cfg.CONF.service_auth.insecure
        cacert = cfg.CONF.service_auth.cafile
        cert = cfg.CONF.service_auth.certfile
        key = cfg.CONF.service_auth.keyfile

        if insecure:
            verify = False
        else:
            verify = cacert or True

        if cert and key:
            cert = (cert, key)

        kwargs = {'auth_url': auth_url,
                  'username': cfg.CONF.service_auth.admin_user,
                  'password': cfg.CONF.service_auth.admin_password}

        if cfg.CONF.service_auth.auth_version == '2':
            client = v2_client
            kwargs['tenant_name'] = cfg.CONF.service_auth.admin_tenant_name
        elif cfg.CONF.service_auth.auth_version == '3':
            client = v3_client
            kwargs['project_name'] = cfg.CONF.service_auth.admin_tenant_name
            kwargs['user_domain_name'] = (cfg.CONF.service_auth.
                                          admin_user_domain)
            kwargs['project_domain_name'] = (cfg.CONF.service_auth.
                                             admin_project_domain)
        else:
            raise Exception(_('Unknown keystone version!'))

        try:
            kc = client.Password(**kwargs)
            _SESSION = session.Session(auth=kc, verify=verify, cert=cert)
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception("Error creating Keystone session.")

    return _SESSION
