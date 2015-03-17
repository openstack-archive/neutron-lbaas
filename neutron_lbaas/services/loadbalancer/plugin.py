#
# Copyright 2013 Radware LTD.
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

from neutron.api.v2 import attributes as attrs
from neutron.common import exceptions as n_exc
from neutron import context as ncontext
from neutron.db import servicetype_db as st_db
from neutron.i18n import _LI, _LE
from neutron.plugins.common import constants
from neutron.services import provider_configuration as pconf
from neutron.services import service_base
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from neutron_lbaas import agent_scheduler as agent_scheduler_v2
from neutron_lbaas.db.loadbalancer import loadbalancer_db as ldb
from neutron_lbaas.db.loadbalancer import loadbalancer_dbv2 as ldbv2
from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.extensions import lbaas_agentschedulerv2
from neutron_lbaas.extensions import loadbalancer as lb_ext
from neutron_lbaas.extensions import loadbalancerv2
from neutron_lbaas.services.loadbalancer import agent_scheduler
from neutron_lbaas.services.loadbalancer import constants as lb_const

LOG = logging.getLogger(__name__)


def verify_lbaas_mutual_exclusion():
    """Verifies lbaas v1 and lbaas v2 cannot be active concurrently."""
    plugins = set([LoadBalancerPlugin.__name__, LoadBalancerPluginv2.__name__])
    cfg_sps = set([sp.split('.')[-1] for sp in cfg.CONF.service_plugins])

    if len(plugins.intersection(cfg_sps)) >= 2:
        msg = _LE("Cannot have service plugins %(v1)s and %(v2)s active at "
                  "the same time!") % {'v1': LoadBalancerPlugin.__name__,
                                       'v2': LoadBalancerPluginv2.__name__}
        LOG.error(msg)
        raise SystemExit(1)


class LoadBalancerPlugin(ldb.LoadBalancerPluginDb,
                         agent_scheduler.LbaasAgentSchedulerDbMixin):
    """Implementation of the Neutron Loadbalancer Service Plugin.

    This class manages the workflow of LBaaS request/response.
    Most DB related works are implemented in class
    loadbalancer_db.LoadBalancerPluginDb.
    """
    supported_extension_aliases = ["lbaas",
                                   "lbaas_agent_scheduler",
                                   "service-type"]

    # lbaas agent notifiers to handle agent update operations;
    # can be updated by plugin drivers while loading;
    # will be extracted by neutron manager when loading service plugins;
    agent_notifiers = {}

    def __init__(self):
        """Initialization for the loadbalancer service plugin."""
        self.service_type_manager = st_db.ServiceTypeManager.get_instance()
        self._load_drivers()

    def _load_drivers(self):
        """Loads plugin-drivers specified in configuration."""
        self.drivers, self.default_provider = service_base.load_drivers(
            constants.LOADBALANCER, self)

        # NOTE(blogan): this method MUST be called after
        # service_base.load_drivers to correctly verify
        verify_lbaas_mutual_exclusion()

        # we're at the point when extensions are not loaded yet
        # so prevent policy from being loaded
        ctx = ncontext.get_admin_context(load_admin_roles=False)
        # stop service in case provider was removed, but resources were not
        self._check_orphan_pool_associations(ctx, self.drivers.keys())

    def _check_orphan_pool_associations(self, context, provider_names):
        """Checks remaining associations between pools and providers.

        If admin has not undeployed resources with provider that was deleted
        from configuration, neutron service is stopped. Admin must delete
        resources prior to removing providers from configuration.
        """
        pools = self.get_pools(context)
        lost_providers = set([pool['provider'] for pool in pools
                              if pool['provider'] not in provider_names])
        # resources are left without provider - stop the service
        if lost_providers:
            LOG.exception(_LE("Delete associated loadbalancer pools before "
                              "removing providers %s"),
                          list(lost_providers))
            raise SystemExit(1)

    def _get_driver_for_provider(self, provider):
        if provider in self.drivers:
            return self.drivers[provider]
        # raise if not associated (should never be reached)
        raise n_exc.Invalid(_LE("Error retrieving driver for provider %s") %
                            provider)

    def _get_driver_for_pool(self, context, pool_id):
        pool = self.get_pool(context, pool_id)
        try:
            return self.drivers[pool['provider']]
        except KeyError:
            raise n_exc.Invalid(_LE("Error retrieving provider for pool %s") %
                                pool_id)

    def get_plugin_type(self):
        return constants.LOADBALANCER

    def get_plugin_description(self):
        return "Neutron LoadBalancer Service Plugin"

    def create_vip(self, context, vip):
        v = super(LoadBalancerPlugin, self).create_vip(context, vip)
        driver = self._get_driver_for_pool(context, v['pool_id'])
        driver.create_vip(context, v)
        return v

    def update_vip(self, context, id, vip):
        if 'status' not in vip['vip']:
            vip['vip']['status'] = constants.PENDING_UPDATE
        old_vip = self.get_vip(context, id)
        v = super(LoadBalancerPlugin, self).update_vip(context, id, vip)
        driver = self._get_driver_for_pool(context, v['pool_id'])
        driver.update_vip(context, old_vip, v)
        return v

    def _delete_db_vip(self, context, id):
        # proxy the call until plugin inherits from DBPlugin
        super(LoadBalancerPlugin, self).delete_vip(context, id)

    def delete_vip(self, context, id):
        self.update_status(context, ldb.Vip,
                           id, constants.PENDING_DELETE)
        v = self.get_vip(context, id)
        driver = self._get_driver_for_pool(context, v['pool_id'])
        driver.delete_vip(context, v)

    def _get_provider_name(self, context, pool):
        if ('provider' in pool and
            pool['provider'] != attrs.ATTR_NOT_SPECIFIED):
            provider_name = pconf.normalize_provider_name(pool['provider'])
            self.validate_provider(provider_name)
            return provider_name
        else:
            if not self.default_provider:
                raise pconf.DefaultServiceProviderNotFound(
                    service_type=constants.LOADBALANCER)
            return self.default_provider

    def create_pool(self, context, pool):
        # This validation is because the new API version also has a resource
        # called pool and these attributes have to be optional in the old API
        # so they are not required attributes of the new.  Its complicated.
        if pool['pool']['lb_method'] == attrs.ATTR_NOT_SPECIFIED:
            raise loadbalancerv2.RequiredAttributeNotSpecified(
                attr_name='lb_method')
        if pool['pool']['subnet_id'] == attrs.ATTR_NOT_SPECIFIED:
            raise loadbalancerv2.RequiredAttributeNotSpecified(
                attr_name='subnet_id')

        provider_name = self._get_provider_name(context, pool['pool'])
        p = super(LoadBalancerPlugin, self).create_pool(context, pool)

        self.service_type_manager.add_resource_association(
            context,
            constants.LOADBALANCER,
            provider_name, p['id'])
        # need to add provider name to pool dict,
        # because provider was not known to db plugin at pool creation
        p['provider'] = provider_name
        driver = self.drivers[provider_name]
        try:
            driver.create_pool(context, p)
        except lb_ext.NoEligibleBackend:
            # that should catch cases when backend of any kind
            # is not available (agent, appliance, etc)
            self.update_status(context, ldb.Pool,
                               p['id'], constants.ERROR,
                               "No eligible backend")
            raise lb_ext.NoEligibleBackend(pool_id=p['id'])
        return p

    def update_pool(self, context, id, pool):
        if 'status' not in pool['pool']:
            pool['pool']['status'] = constants.PENDING_UPDATE
        old_pool = self.get_pool(context, id)
        p = super(LoadBalancerPlugin, self).update_pool(context, id, pool)
        driver = self._get_driver_for_provider(p['provider'])
        driver.update_pool(context, old_pool, p)
        return p

    def _delete_db_pool(self, context, id):
        # proxy the call until plugin inherits from DBPlugin
        # rely on uuid uniqueness:
        try:
            with context.session.begin(subtransactions=True):
                self.service_type_manager.del_resource_associations(
                    context, [id])
                super(LoadBalancerPlugin, self).delete_pool(context, id)
        except Exception:
            # that should not happen
            # if it's still a case - something goes wrong
            # log the error and mark the pool as ERROR
            LOG.error(_LE('Failed to delete pool %s, putting it in ERROR '
                          'state'),
                      id)
            with excutils.save_and_reraise_exception():
                self.update_status(context, ldb.Pool,
                                   id, constants.ERROR)

    def delete_pool(self, context, id):
        # check for delete conditions and update the status
        # within a transaction to avoid a race
        with context.session.begin(subtransactions=True):
            self.update_status(context, ldb.Pool,
                               id, constants.PENDING_DELETE)
            self._ensure_pool_delete_conditions(context, id)
        p = self.get_pool(context, id)
        driver = self._get_driver_for_provider(p['provider'])
        driver.delete_pool(context, p)

    def create_member(self, context, member):
        m = super(LoadBalancerPlugin, self).create_member(context, member)
        driver = self._get_driver_for_pool(context, m['pool_id'])
        driver.create_member(context, m)
        return m

    def update_member(self, context, id, member):
        if 'status' not in member['member']:
            member['member']['status'] = constants.PENDING_UPDATE
        old_member = self.get_member(context, id)
        m = super(LoadBalancerPlugin, self).update_member(context, id, member)
        driver = self._get_driver_for_pool(context, m['pool_id'])
        driver.update_member(context, old_member, m)
        return m

    def _delete_db_member(self, context, id):
        # proxy the call until plugin inherits from DBPlugin
        super(LoadBalancerPlugin, self).delete_member(context, id)

    def delete_member(self, context, id):
        self.update_status(context, ldb.Member,
                           id, constants.PENDING_DELETE)
        m = self.get_member(context, id)
        driver = self._get_driver_for_pool(context, m['pool_id'])
        driver.delete_member(context, m)

    def _validate_hm_parameters(self, delay, timeout):
        if delay < timeout:
            raise lb_ext.DelayOrTimeoutInvalid()

    def create_health_monitor(self, context, health_monitor):
        new_hm = health_monitor['health_monitor']
        self._validate_hm_parameters(new_hm['delay'], new_hm['timeout'])

        hm = super(LoadBalancerPlugin, self).create_health_monitor(
            context,
            health_monitor
        )
        return hm

    def update_health_monitor(self, context, id, health_monitor):
        new_hm = health_monitor['health_monitor']
        old_hm = self.get_health_monitor(context, id)
        delay = new_hm.get('delay', old_hm.get('delay'))
        timeout = new_hm.get('timeout', old_hm.get('timeout'))
        self._validate_hm_parameters(delay, timeout)

        hm = super(LoadBalancerPlugin, self).update_health_monitor(
            context,
            id,
            health_monitor
        )

        with context.session.begin(subtransactions=True):
            qry = context.session.query(
                ldb.PoolMonitorAssociation
            ).filter_by(monitor_id=hm['id']).join(ldb.Pool)
            for assoc in qry:
                driver = self._get_driver_for_pool(context, assoc['pool_id'])
                driver.update_pool_health_monitor(context, old_hm,
                                                  hm, assoc['pool_id'])
        return hm

    def _delete_db_pool_health_monitor(self, context, hm_id, pool_id):
        super(LoadBalancerPlugin, self).delete_pool_health_monitor(context,
                                                                   hm_id,
                                                                   pool_id)

    def _delete_db_health_monitor(self, context, id):
        super(LoadBalancerPlugin, self).delete_health_monitor(context, id)

    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        retval = super(LoadBalancerPlugin, self).create_pool_health_monitor(
            context,
            health_monitor,
            pool_id
        )
        monitor_id = health_monitor['health_monitor']['id']
        hm = self.get_health_monitor(context, monitor_id)
        driver = self._get_driver_for_pool(context, pool_id)
        driver.create_pool_health_monitor(context, hm, pool_id)
        return retval

    def delete_pool_health_monitor(self, context, id, pool_id):
        self.update_pool_health_monitor(context, id, pool_id,
                                        constants.PENDING_DELETE)
        hm = self.get_health_monitor(context, id)
        driver = self._get_driver_for_pool(context, pool_id)
        driver.delete_pool_health_monitor(context, hm, pool_id)

    def stats(self, context, pool_id):
        driver = self._get_driver_for_pool(context, pool_id)
        stats_data = driver.stats(context, pool_id)
        # if we get something from the driver -
        # update the db and return the value from db
        # else - return what we have in db
        if stats_data:
            super(LoadBalancerPlugin, self).update_pool_stats(
                context,
                pool_id,
                stats_data
            )
        return super(LoadBalancerPlugin, self).stats(context,
                                                     pool_id)

    def populate_vip_graph(self, context, vip):
        """Populate the vip with: pool, members, healthmonitors."""

        pool = self.get_pool(context, vip['pool_id'])
        vip['pool'] = pool
        vip['members'] = [self.get_member(context, member_id)
                          for member_id in pool['members']]
        vip['health_monitors'] = [self.get_health_monitor(context, hm_id)
                                  for hm_id in pool['health_monitors']]
        return vip

    def validate_provider(self, provider):
        if provider not in self.drivers:
            raise pconf.ServiceProviderNotFound(
                provider=provider, service_type=constants.LOADBALANCER)


class LoadBalancerPluginv2(loadbalancerv2.LoadBalancerPluginBaseV2):
    """Implementation of the Neutron Loadbalancer Service Plugin.

    This class manages the workflow of LBaaS request/response.
    Most DB related works are implemented in class
    loadbalancer_db.LoadBalancerPluginDb.
    """
    supported_extension_aliases = ["lbaasv2",
                                   "lbaas_agent_schedulerv2",
                                   "service-type"]

    agent_notifiers = (
        agent_scheduler_v2.LbaasAgentSchedulerDbMixin.agent_notifiers)

    def __init__(self):
        """Initialization for the loadbalancer service plugin."""
        self.db = ldbv2.LoadBalancerPluginDbv2()
        self.service_type_manager = st_db.ServiceTypeManager.get_instance()
        self._load_drivers()

    def _load_drivers(self):
        """Loads plugin-drivers specified in configuration."""
        self.drivers, self.default_provider = service_base.load_drivers(
            constants.LOADBALANCERV2, self)

        # NOTE(blogan): this method MUST be called after
        # service_base.load_drivers to correctly verify
        verify_lbaas_mutual_exclusion()

        # we're at the point when extensions are not loaded yet
        # so prevent policy from being loaded
        ctx = ncontext.get_admin_context(load_admin_roles=False)
        # stop service in case provider was removed, but resources were not
        self._check_orphan_loadbalancer_associations(ctx, self.drivers.keys())

    def _check_orphan_loadbalancer_associations(self, context, provider_names):
        """Checks remaining associations between loadbalancers and providers.

        If admin has not undeployed resources with provider that was deleted
        from configuration, neutron service is stopped. Admin must delete
        resources prior to removing providers from configuration.
        """
        loadbalancers = self.db.get_loadbalancers(context)
        lost_providers = set(
            [lb.provider.provider_name
             for lb in loadbalancers
             if lb.provider.provider_name not in provider_names])
        # resources are left without provider - stop the service
        if lost_providers:
            msg = _LE("Delete associated load balancers before "
                      "removing providers %s") % list(lost_providers)
            LOG.error(msg)
            raise SystemExit(1)

    def _get_driver_for_provider(self, provider):
        try:
            return self.drivers[provider]
        except KeyError:
            # raise if not associated (should never be reached)
            raise n_exc.Invalid(_LE("Error retrieving driver for provider "
                                    "%s") % provider)

    def _get_driver_for_loadbalancer(self, context, loadbalancer_id):
        lb = self.db.get_loadbalancer(context, loadbalancer_id)
        try:
            return self.drivers[lb.provider.provider_name]
        except KeyError:
            raise n_exc.Invalid(
                _LE("Error retrieving provider for load balancer. Possible "
                    "providers are %s.") % self.drivers.keys()
            )

    def _get_provider_name(self, entity):
        if ('provider' in entity and
                entity['provider'] != attrs.ATTR_NOT_SPECIFIED):
            provider_name = pconf.normalize_provider_name(entity['provider'])
            del entity['provider']
            self.validate_provider(provider_name)
            return provider_name
        else:
            if not self.default_provider:
                raise pconf.DefaultServiceProviderNotFound(
                    service_type=constants.LOADBALANCER)
            del entity['provider']
            return self.default_provider

    def _call_driver_operation(self, context, driver_method, db_entity,
                               old_db_entity=None):
        manager_method = "%s.%s" % (driver_method.__self__.__class__.__name__,
                                    driver_method.__name__)
        LOG.info(_LI("Calling driver operation %s") % manager_method)
        try:
            if old_db_entity:
                driver_method(context, old_db_entity, db_entity)
            else:
                driver_method(context, db_entity)
        # catching and reraising agent issues
        except (lbaas_agentschedulerv2.NoEligibleLbaasAgent,
                lbaas_agentschedulerv2.NoActiveLbaasAgent) as no_agent:
            raise no_agent
        except Exception:
            LOG.exception(_LE("There was an error in the driver"))
            self._handle_driver_error(context, db_entity)
            raise loadbalancerv2.DriverError()

    def _handle_driver_error(self, context, db_entity):
        lb_id = db_entity.root_loadbalancer.id
        self.db.update_status(context, models.LoadBalancer, lb_id,
                              constants.ERROR)

    def _validate_session_persistence_info(self, sp_info):
        """Performs sanity check on session persistence info.

        :param sp_info: Session persistence info
        """
        if not sp_info:
            return
        if sp_info['type'] == lb_const.SESSION_PERSISTENCE_APP_COOKIE:
            if not sp_info.get('cookie_name'):
                raise loadbalancerv2.SessionPersistenceConfigurationInvalid(
                    msg="'cookie_name' should be specified for %s"
                        " session persistence." % sp_info['type'])
        else:
            if 'cookie_name' in sp_info:
                raise loadbalancerv2.SessionPersistenceConfigurationInvalid(
                    msg="'cookie_name' is not allowed for %s"
                        " session persistence" % sp_info['type'])

    def get_plugin_type(self):
        return constants.LOADBALANCERV2

    def get_plugin_description(self):
        return "Neutron LoadBalancer Service Plugin v2"

    def create_loadbalancer(self, context, loadbalancer):
        loadbalancer = loadbalancer.get('loadbalancer')
        provider_name = self._get_provider_name(loadbalancer)
        lb_db = self.db.create_loadbalancer(context, loadbalancer)
        self.service_type_manager.add_resource_association(
            context,
            constants.LOADBALANCERV2,
            provider_name, lb_db.id)
        driver = self.drivers[provider_name]
        self._call_driver_operation(
            context, driver.load_balancer.create, lb_db)
        return self.db.get_loadbalancer(context, lb_db.id).to_api_dict()

    def update_loadbalancer(self, context, id, loadbalancer):
        loadbalancer = loadbalancer.get('loadbalancer')
        old_lb = self.db.get_loadbalancer(context, id)
        self.db.test_and_set_status(context, models.LoadBalancer, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_lb = self.db.update_loadbalancer(
                context, id, loadbalancer)
        except Exception as exc:
            self.db.update_status(context, models.LoadBalancer, id,
                                  old_lb.provisioning_status)
            raise exc
        driver = self._get_driver_for_provider(old_lb.provider.provider_name)
        self._call_driver_operation(context,
                                    driver.load_balancer.update,
                                    updated_lb, old_db_entity=old_lb)
        return self.db.get_loadbalancer(context, id).to_api_dict()

    def delete_loadbalancer(self, context, id):
        old_lb = self.db.get_loadbalancer(context, id)
        if old_lb.listeners:
            raise loadbalancerv2.EntityInUse(
                entity_using=models.Listener.NAME,
                id=old_lb.listeners[0].id,
                entity_in_use=models.LoadBalancer.NAME)
        self.db.test_and_set_status(context, models.LoadBalancer, id,
                                    constants.PENDING_DELETE)
        driver = self._get_driver_for_provider(old_lb.provider.provider_name)
        db_lb = self.db.get_loadbalancer(context, id)
        self._call_driver_operation(
            context, driver.load_balancer.delete, db_lb)

    def get_loadbalancer(self, context, id, fields=None):
        return self.db.get_loadbalancer(context, id).to_api_dict()

    def get_loadbalancers(self, context, filters=None, fields=None):
        return [listener.to_api_dict() for listener in
                self.db.get_loadbalancers(context, filters=filters)]

    def create_listener(self, context, listener):
        listener = listener.get('listener')
        lb_id = listener.get('loadbalancer_id')
        listener['default_pool_id'] = None
        self.db.test_and_set_status(context, models.LoadBalancer, lb_id,
                                    constants.PENDING_UPDATE)
        try:
            listener_db = self.db.create_listener(context, listener)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, lb_id)
            raise exc
        driver = self._get_driver_for_loadbalancer(
            context, listener_db.loadbalancer_id)
        self._call_driver_operation(
            context, driver.listener.create, listener_db)

        return self.db.get_listener(context, listener_db.id).to_api_dict()

    def update_listener(self, context, id, listener):
        listener = listener.get('listener')
        old_listener = self.db.get_listener(context, id)
        self.db.test_and_set_status(context, models.Listener, id,
                                    constants.PENDING_UPDATE)
        try:
            listener_db = self.db.update_listener(context, id, listener)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, old_listener.loadbalancer.id)
            raise exc

        driver = self._get_driver_for_loadbalancer(
            context, listener_db.loadbalancer_id)
        self._call_driver_operation(
            context,
            driver.listener.update,
            listener_db,
            old_db_entity=old_listener)

        return self.db.get_listener(context, id).to_api_dict()

    def delete_listener(self, context, id):
        old_listener = self.db.get_listener(context, id)
        if old_listener.default_pool:
            raise loadbalancerv2.EntityInUse(
                entity_using=models.PoolV2.NAME,
                id=old_listener.default_pool.id,
                entity_in_use=models.Listener.NAME)
        self.db.test_and_set_status(context, models.Listener, id,
                                    constants.PENDING_DELETE)
        listener_db = self.db.get_listener(context, id)

        driver = self._get_driver_for_loadbalancer(
            context, listener_db.loadbalancer_id)
        self._call_driver_operation(
            context, driver.listener.delete, listener_db)

    def get_listener(self, context, id, fields=None):
        return self.db.get_listener(context, id).to_api_dict()

    def get_listeners(self, context, filters=None, fields=None):
        return [listener.to_api_dict() for listener in self.db.get_listeners(
            context, filters=filters)]

    def create_pool(self, context, pool):
        pool = pool.get('pool')
        listener_id = pool.pop('listener_id')
        db_listener = self.db.get_listener(context, listener_id)
        if db_listener.default_pool_id:
            raise loadbalancerv2.OnePoolPerListener(
                listener_id=listener_id, pool_id=db_listener.default_pool_id)
        self._validate_session_persistence_info(
            pool.get('session_persistence'))
        self.db.test_and_set_status(context, models.LoadBalancer,
                                    db_listener.loadbalancer.id,
                                    constants.PENDING_UPDATE)
        try:
            db_pool = self.db.create_pool_and_add_to_listener(context, pool,
                                                              listener_id)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, db_listener.loadbalancer.id)
            raise exc
        driver = self._get_driver_for_loadbalancer(
            context, db_pool.listener.loadbalancer_id)
        self._call_driver_operation(context, driver.pool.create, db_pool)
        return self.db.get_pool(context, db_pool.id).to_api_dict()

    def update_pool(self, context, id, pool):
        pool = pool.get('pool')
        self._validate_session_persistence_info(
            pool.get('session_persistence'))
        old_pool = self.db.get_pool(context, id)
        self.db.test_and_set_status(context, models.PoolV2, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_pool = self.db.update_pool(context, id, pool)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, old_pool.root_loadbalancer.id)
            raise exc

        driver = self._get_driver_for_loadbalancer(
            context, updated_pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.pool.update,
                                    updated_pool,
                                    old_db_entity=old_pool)

        return self.db.get_pool(context, id).to_api_dict()

    def delete_pool(self, context, id):
        self.db.test_and_set_status(context, models.PoolV2, id,
                                    constants.PENDING_DELETE)
        db_pool = self.db.get_pool(context, id)

        driver = self._get_driver_for_loadbalancer(
            context, db_pool.listener.loadbalancer_id)
        self._call_driver_operation(context, driver.pool.delete, db_pool)

    def get_pools(self, context, filters=None, fields=None):
        return [pool.to_api_dict() for pool in self.db.get_pools(
            context, filters=filters)]

    def get_pool(self, context, id, fields=None):
        return self.db.get_pool(context, id).to_api_dict()

    def _check_pool_exists(self, context, pool_id):
        if not self.db._resource_exists(context, models.PoolV2, pool_id):
            raise loadbalancerv2.EntityNotFound(name=models.PoolV2.NAME,
                                                id=pool_id)

    def create_pool_member(self, context, pool_id, member):
        self._check_pool_exists(context, pool_id)
        db_pool = self.db.get_pool(context, pool_id)
        self.db.test_and_set_status(context, models.LoadBalancer,
                                    db_pool.root_loadbalancer.id,
                                    constants.PENDING_UPDATE)
        member = member.get('member')
        try:
            member_db = self.db.create_pool_member(context, member, pool_id)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, db_pool.root_loadbalancer.id)
            raise exc

        driver = self._get_driver_for_loadbalancer(
            context, member_db.pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.member.create,
                                    member_db)

        return self.db.get_pool_member(context, member_db.id).to_api_dict()

    def update_pool_member(self, context, id, pool_id, member):
        self._check_pool_exists(context, pool_id)
        member = member.get('member')
        old_member = self.db.get_pool_member(context, id)
        self.db.test_and_set_status(context, models.MemberV2, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_member = self.db.update_pool_member(context, id, member)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, old_member.pool.listener.loadbalancer.id)
            raise exc

        driver = self._get_driver_for_loadbalancer(
            context, updated_member.pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.member.update,
                                    updated_member,
                                    old_db_entity=old_member)

        return self.db.get_pool_member(context, id).to_api_dict()

    def delete_pool_member(self, context, id, pool_id):
        self._check_pool_exists(context, pool_id)
        self.db.test_and_set_status(context, models.MemberV2, id,
                                    constants.PENDING_DELETE)
        db_member = self.db.get_pool_member(context, id)

        driver = self._get_driver_for_loadbalancer(
            context, db_member.pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.member.delete,
                                    db_member)

    def get_pool_members(self, context, pool_id, filters=None, fields=None):
        self._check_pool_exists(context, pool_id)
        return [mem.to_api_dict() for mem in self.db.get_pool_members(
            context, filters=filters)]

    def get_pool_member(self, context, id, pool_id, fields=None):
        self._check_pool_exists(context, pool_id)
        return self.db.get_pool_member(context, id).to_api_dict()

    def _check_pool_already_has_healthmonitor(self, context, pool_id):
        pool = self.db.get_pool(context, pool_id)
        if pool.healthmonitor:
            raise loadbalancerv2.OneHealthMonitorPerPool(
                pool_id=pool_id, hm_id=pool.healthmonitor.id)

    def create_healthmonitor(self, context, healthmonitor):
        healthmonitor = healthmonitor.get('healthmonitor')
        pool_id = healthmonitor.pop('pool_id')
        self._check_pool_exists(context, pool_id)
        self._check_pool_already_has_healthmonitor(context, pool_id)
        db_pool = self.db.get_pool(context, pool_id)
        self.db.test_and_set_status(context, models.LoadBalancer,
                                    db_pool.root_loadbalancer.id,
                                    constants.PENDING_UPDATE)
        try:
            db_hm = self.db.create_healthmonitor_on_pool(context, pool_id,
                                                         healthmonitor)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, db_pool.root_loadbalancer.id)
            raise exc
        driver = self._get_driver_for_loadbalancer(
            context, db_hm.pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.health_monitor.create,
                                    db_hm)
        return self.db.get_healthmonitor(context, db_hm.id).to_api_dict()

    def update_healthmonitor(self, context, id, healthmonitor):
        healthmonitor = healthmonitor.get('healthmonitor')
        old_hm = self.db.get_healthmonitor(context, id)
        self.db.test_and_set_status(context, models.HealthMonitorV2, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_hm = self.db.update_healthmonitor(context, id,
                                                      healthmonitor)
        except Exception as exc:
            self.db.update_loadbalancer_provisioning_status(
                context, old_hm.root_loadbalancer.id)
            raise exc

        driver = self._get_driver_for_loadbalancer(
            context, updated_hm.pool.listener.loadbalancer_id)
        self._call_driver_operation(context,
                                    driver.health_monitor.update,
                                    updated_hm,
                                    old_db_entity=old_hm)

        return self.db.get_healthmonitor(context, updated_hm.id).to_api_dict()

    def delete_healthmonitor(self, context, id):
        self.db.test_and_set_status(context, models.HealthMonitorV2, id,
                                    constants.PENDING_DELETE)
        db_hm = self.db.get_healthmonitor(context, id)

        driver = self._get_driver_for_loadbalancer(
            context, db_hm.pool.listener.loadbalancer_id)
        self._call_driver_operation(
            context, driver.health_monitor.delete, db_hm)

    def get_healthmonitor(self, context, id, fields=None):
        return self.db.get_healthmonitor(context, id).to_api_dict()

    def get_healthmonitors(self, context, filters=None, fields=None):
        return [hm.to_api_dict() for hm in self.db.get_healthmonitors(
            context, filters=filters)]

    def stats(self, context, loadbalancer_id):
        lb = self.db.get_loadbalancer(context, loadbalancer_id)
        driver = self._get_driver_for_loadbalancer(context, loadbalancer_id)
        stats_data = driver.load_balancer.stats(context, lb)
        # if we get something from the driver -
        # update the db and return the value from db
        # else - return what we have in db
        if stats_data:
            self.db.update_loadbalancer_stats(context, loadbalancer_id,
                                              stats_data)
        db_stats = self.db.stats(context, loadbalancer_id)
        return {'stats': db_stats.to_api_dict()}

    def validate_provider(self, provider):
        if provider not in self.drivers:
            raise pconf.ServiceProviderNotFound(
                provider=provider, service_type=constants.LOADBALANCERV2)

    def statuses(self, context, loadbalancer_id):
        PROV = 'provisioning_status'
        OPER = 'operating_status'
        lb = self.db.get_loadbalancer(context, loadbalancer_id)
        statuses = {'statuses': {}}
        statuses['statuses']['loadbalancer'] = {
            PROV: getattr(lb, PROV),
            OPER: getattr(lb, OPER)
        }
        listener_statuses = []
        for lindex, listener in enumerate(lb.listeners):
            listener_statuses.append({
                'id': listener.id,
                PROV: getattr(listener, PROV),
                OPER: getattr(listener, OPER)
            })
            pool_statuses = []
            if listener.default_pool:
                pool_statuses.append({
                    'id': listener.default_pool.id,
                    PROV: getattr(listener.default_pool, PROV),
                    OPER: getattr(listener.default_pool, OPER)
                })
                member_statuses = []
                for mindex, member in enumerate(listener.default_pool.members):
                    member_statuses.append({
                        'id': member.id,
                        PROV: getattr(member, PROV),
                        OPER: getattr(member, OPER)
                    })
                hm_status = {}
                if listener.default_pool.healthmonitor:
                    hm_status = {
                        'id': listener.default_pool.healthmonitor.id,
                        PROV: getattr(listener.default_pool.healthmonitor,
                                      PROV)
                    }
                pool_statuses[0]['healthmonitor'] = hm_status
                pool_statuses[0]['members'] = member_statuses
            listener_statuses[lindex]['pools'] = pool_statuses
        statuses['statuses']['loadbalancer']['listeners'] = listener_statuses
        return statuses

    # NOTE(brandon-logan): these need to be concrete methods because the
    # neutron request pipeline calls these methods before the plugin methods
    # are ever called
    def get_members(self, context, filters=None, fields=None):
        pass

    def get_member(self, context, id, fields=None):
        pass
