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
from neutron.db.loadbalancer import loadbalancer_db as ldb
from neutron.db.loadbalancer import loadbalancer_dbv2 as ldbv2
from neutron.db.loadbalancer import models
from neutron.db import servicetype_db as st_db
from neutron.extensions import loadbalancer
from neutron.extensions import loadbalancerv2
from neutron.openstack.common import excutils
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants
from neutron.services.loadbalancer import agent_scheduler
from neutron.services.loadbalancer import constants as lb_const
from neutron.services.loadbalancer import data_models
from neutron.services import provider_configuration as pconf
from neutron.services import service_base

LOG = logging.getLogger(__name__)


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
            msg = _("Delete associated loadbalancer pools before "
                    "removing providers %s") % list(lost_providers)
            LOG.exception(msg)
            raise SystemExit(1)

    def _get_driver_for_provider(self, provider):
        if provider in self.drivers:
            return self.drivers[provider]
        # raise if not associated (should never be reached)
        raise n_exc.Invalid(_("Error retrieving driver for provider %s") %
                            provider)

    def _get_driver_for_pool(self, context, pool_id):
        pool = self.get_pool(context, pool_id)
        try:
            return self.drivers[pool['provider']]
        except KeyError:
            raise n_exc.Invalid(_("Error retrieving provider for pool %s") %
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
        if (pool['pool']['lb_method'] == attrs.ATTR_NOT_SPECIFIED):
            raise loadbalancerv2.RequiredAttributeNotSpecified(
                attr_name='lb_method')
        if (pool['pool']['subnet_id'] == attrs.ATTR_NOT_SPECIFIED):
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
        except loadbalancer.NoEligibleBackend:
            # that should catch cases when backend of any kind
            # is not available (agent, appliance, etc)
            self.update_status(context, ldb.Pool,
                               p['id'], constants.ERROR,
                               "No eligible backend")
            raise loadbalancer.NoEligibleBackend(pool_id=p['id'])
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
            LOG.error(_('Failed to delete pool %s, putting it in ERROR state'),
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
            raise loadbalancer.DelayOrTimeoutInvalid()

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


class LoadBalancerPluginv2(loadbalancerv2.LoadBalancerPluginBaseV2,
                           agent_scheduler.LbaasAgentSchedulerDbMixin):
    """Implementation of the Neutron Loadbalancer Service Plugin.

    This class manages the workflow of LBaaS request/response.
    Most DB related works are implemented in class
    loadbalancer_db.LoadBalancerPluginDb.
    """
    supported_extension_aliases = ["lbaasv2",
                                   "lbaas_agent_scheduler",
                                   "service-type"]

    # lbaas agent notifiers to handle agent update operations;
    # can be updated by plugin drivers while loading;
    # will be extracted by neutron manager when loading service plugins;
    agent_notifiers = {}

    def __init__(self):
        """Initialization for the loadbalancer service plugin."""

        self.db = ldbv2.LoadBalancerPluginDbv2()
        self.service_type_manager = st_db.ServiceTypeManager.get_instance()
        self._load_drivers()

    def _load_drivers(self):
        """Loads plugin-drivers specified in configuration."""
        self.drivers, self.default_provider = service_base.load_drivers(
            constants.LOADBALANCERV2, self)

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
            [loadbalancer.provider.provider_name
             for loadbalancer in loadbalancers
             if loadbalancer.provider.provider_name not in provider_names])
        # resources are left without provider - stop the service
        if lost_providers:
            msg = _("Delete associated load balancers before "
                    "removing providers %s") % list(lost_providers)
            LOG.error(msg)
            raise SystemExit(1)

    def _get_driver_for_provider(self, provider):
        try:
            return self.drivers[provider]
        except KeyError:
            # raise if not associated (should never be reached)
            raise n_exc.Invalid(_("Error retrieving driver for provider %s") %
                                provider)

    def _get_driver_for_loadbalancer(self, context, loadbalancer_id):
        loadbalancer = self.db.get_loadbalancer(context, loadbalancer_id)
        try:
            return self.drivers[loadbalancer.provider.provider_name]
        except KeyError:
            raise n_exc.Invalid(
                _("Error retrieving provider for load balancer. Possible "
                  "providers are %s.") % self.drivers.keys()
            )

    def _get_provider_name(self, entity):
        if ('provider' in entity and
                entity['provider'] != attrs.ATTR_NOT_SPECIFIED):
            provider_name = pconf.normalize_provider_name(entity['provider'])
            self.validate_provider(provider_name)
            return provider_name
        else:
            if not self.default_provider:
                raise pconf.DefaultServiceProviderNotFound(
                    service_type=constants.LOADBALANCER)
            return self.default_provider

    def _call_driver_operation(self, context, driver_method, db_entity,
                               old_db_entity=None):
        manager_method = "%s.%s" % (driver_method.__self__.__class__.__name__,
                                    driver_method.__name__)
        LOG.info(_("Calling driver operation %s") % manager_method)
        try:
            if old_db_entity:
                driver_method(context, old_db_entity, db_entity)
            else:
                driver_method(context, db_entity)
        except Exception:
            LOG.exception(_("There was an error in the driver"))
            self.db.update_status(context, db_entity.__class__._SA_MODEL,
                                  db_entity.id, constants.ERROR)
            raise loadbalancerv2.DriverError()

    def _validate_session_persistence_info(self, sp_info):
        """Performs sanity check on session persistence info.

        :param sp_info: Session persistence info
        """
        if not sp_info:
            return
        if sp_info['type'] == lb_const.SESSION_PERSISTENCE_APP_COOKIE:
            if not sp_info.get('cookie_name'):
                raise ValueError(_("'cookie_name' should be specified for %s"
                                   " session persistence.") % sp_info['type'])
        else:
            if 'cookie_name' in sp_info:
                raise ValueError(_("'cookie_name' is not allowed for %s"
                                   " session persistence") % sp_info['type'])

    def defer_listener(self, context, listener, cascade=True):
        self.db.update_status(context, models.Listener, listener.id,
                              constants.DEFERRED)
        if cascade and listener.default_pool:
            self.defer_pool(context, listener.default_pool, cascade=cascade)

    def defer_pool(self, context, pool, cascade=True):
        self.db.update_status(context, models.PoolV2, pool.id,
                              constants.DEFERRED)
        if cascade:
            self.defer_members(context, pool.members)
        if cascade and pool.healthmonitor:
            self.defer_healthmonitor(context, pool.healthmonitor)

    def defer_healthmonitor(self, context, healthmonitor):
        self.db.update_status(context, models.HealthMonitorV2,
                              healthmonitor.id, constants.DEFERRED)

    def defer_members(self, context, members):
        for member in members:
            self.db.update_status(context, models.MemberV2,
                                  member.id, constants.DEFERRED)

    def defer_unlinked_entities(self, context, obj, old_obj=None):
        # if old_obj is None then this is delete else it is an update
        if isinstance(obj, models.Listener):
            # if listener.loadbalancer_id is set to None set listener status
            # to deferred
            deleted_listener = not old_obj
            unlinked_listener = (not obj.loadbalancer and old_obj and
                                 old_obj.loadbalancer)
            unlinked_pool = (bool(old_obj) and not obj.default_pool and
                             old_obj.default_pool)
            if unlinked_listener:
                self.db.update_status(context, models.Listener,
                                      old_obj.id, constants.DEFERRED)
            # if listener has been deleted OR if default_pool_id has been
            # updated to None, then set Pool and its children statuses to
            # DEFERRED
            if deleted_listener or unlinked_pool or unlinked_listener:
                if old_obj:
                    obj = old_obj
                if not obj.default_pool:
                    return
                self.db.update_status(context, models.PoolV2,
                                      obj.default_pool.id, constants.DEFERRED)
                if obj.default_pool.healthmonitor:
                    self.db.update_status(context, models.HealthMonitorV2,
                                          obj.default_pool.healthmonitor.id,
                                          constants.DEFERRED)
                for member in obj.default_pool.members:
                    self.db.update_status(context, models.MemberV2,
                                          member.id, constants.DEFERRED)
        elif isinstance(obj, models.PoolV2):
            # if pool has been deleted OR if pool.healthmonitor_id has been
            # updated to None then set healthmonitor status to DEFERRED
            deleted_pool = not old_obj
            unlinked_hm = (bool(old_obj) and not obj.healthmonitor and
                           old_obj.healthmonitor)
            if deleted_pool or unlinked_hm:
                if old_obj:
                    obj = old_obj
                self.db.update_status(context, models.HealthMonitorV2,
                                      obj.healthmonitor.id,
                                      constants.DEFERRED)

    def activate_linked_entities(self, context, obj):
        if isinstance(obj, data_models.LoadBalancer):
            self.db.update_status(context, models.LoadBalancer,
                                  obj.id, constants.ACTIVE)
            # only update loadbalancer's status because it's not able to
            # change any links to children
            return
        if isinstance(obj, data_models.Listener):
            self.db.update_status(context, models.Listener,
                                  obj.id, constants.ACTIVE)
            if obj.default_pool:
                self.activate_linked_entities(context, obj.default_pool)
        if isinstance(obj, data_models.Pool):
            self.db.update_status(context, models.PoolV2,
                                  obj.id, constants.ACTIVE)
            if obj.healthmonitor:
                self.activate_linked_entities(context, obj.healthmonitor)
            for member in obj.members:
                self.activate_linked_entities(context, member)
        if isinstance(obj, data_models.Member):
            # do not overwrite INACTVE status
            if obj.status != constants.INACTIVE:
                self.db.update_status(context, models.MemberV2, obj.id,
                                      constants.ACTIVE)
        if isinstance(obj, data_models.HealthMonitor):
            self.db.update_status(context, models.HealthMonitorV2, obj.id,
                                  constants.ACTIVE)

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
        return self.db.get_loadbalancer(context, lb_db.id).to_dict()

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
                                  old_lb.status)
            raise exc
        driver = self._get_driver_for_provider(old_lb.provider.provider_name)
        self._call_driver_operation(context,
                                    driver.load_balancer.update,
                                    updated_lb, old_db_entity=old_lb)
        return self.db.get_loadbalancer(context, updated_lb.id).to_dict()

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
        self._call_driver_operation(
            context, driver.load_balancer.delete, old_lb)

    def get_loadbalancer(self, context, id, fields=None):
        lb_db = self.db.get_loadbalancer(context, id)
        return self.db._fields(lb_db.to_dict(), fields)

    def get_loadbalancers(self, context, filters=None, fields=None):
        loadbalancers = self.db.get_loadbalancers(context, filters=filters)
        return [self.db._fields(lb.to_dict(), fields) for lb in loadbalancers]

    def create_listener(self, context, listener):
        listener = listener.get('listener')
        listener_db = self.db.create_listener(context, listener)

        if listener_db.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, listener_db.loadbalancer_id)
            self._call_driver_operation(
                context, driver.listener.create, listener_db)
        else:
            self.db.update_status(context, models.Listener, listener_db.id,
                                  constants.DEFERRED)

        return self.db.get_listener(context, listener_db.id).to_dict()

    def update_listener(self, context, id, listener):
        listener = listener.get('listener')
        old_listener = self.db.get_listener(context, id)
        self.db.test_and_set_status(context, models.Listener, id,
                                    constants.PENDING_UPDATE)

        try:
            listener_db = self.db.update_listener(context, id, listener)
        except Exception as exc:
            self.db.update_status(context, models.Listener, id,
                                  old_listener.status)
            raise exc

        if (listener_db.attached_to_loadbalancer() or
                old_listener.attached_to_loadbalancer()):
            if listener_db.attached_to_loadbalancer():
                driver = self._get_driver_for_loadbalancer(
                    context, listener_db.loadbalancer_id)
            else:
                driver = self._get_driver_for_loadbalancer(
                    context, old_listener.loadbalancer_id)
            self._call_driver_operation(
                context,
                driver.listener.update,
                listener_db,
                old_db_entity=old_listener)
        else:
            self.db.update_status(context, models.Listener, id,
                                  constants.DEFERRED)

        return self.db.get_listener(context, listener_db.id).to_dict()

    def delete_listener(self, context, id):
        self.db.test_and_set_status(context, models.Listener, id,
                                    constants.PENDING_DELETE)
        listener_db = self.db.get_listener(context, id)

        if listener_db.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, listener_db.loadbalancer_id)
            self._call_driver_operation(
                context, driver.listener.delete, listener_db)
        else:
            self.db.delete_listener(context, id)

    def get_listener(self, context, id, fields=None):
        listener_db = self.db.get_listener(context, id)
        return self.db._fields(listener_db.to_dict(), fields)

    def get_listeners(self, context, filters=None, fields=None):
        listeners = self.db.get_listeners(context, filters=filters)
        return [self.db._fields(listener.to_dict(), fields)
                for listener in listeners]

    def create_pool(self, context, pool):
        pool = pool.get('pool')

        # FIXME(brandon-logan) This validation should only exist while the old
        # version of the API exists.  Remove the following block when this
        # happens
        pool.pop('lb_method', None)
        pool.pop('provider', None)
        pool.pop('subnet_id', None)
        pool.pop('health_monitors', None)
        if ('lb_algorithm' not in pool or
                pool['lb_algorithm'] == attrs.ATTR_NOT_SPECIFIED):
            raise loadbalancerv2.RequiredAttributeNotSpecified(
                attr_name='lb_algorithm')

        self._validate_session_persistence_info(
            pool.get('session_persistence'))

        db_pool = self.db.create_pool(context, pool)
        # no need to call driver since on create it cannot be linked to a load
        # balancer, but will still update status to DEFERRED
        self.db.update_status(context, models.PoolV2, db_pool.id,
                              constants.DEFERRED)
        return self.db.get_pool(context, db_pool.id).to_dict()

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
            self.db.update_status(context, models.PoolV2, id, old_pool.status)
            raise exc

        if (updated_pool.attached_to_loadbalancer() or
                old_pool.attached_to_loadbalancer()):
            if updated_pool.attached_to_loadbalancer():
                driver = self._get_driver_for_loadbalancer(
                    context, updated_pool.listener.loadbalancer_id)
            else:
                driver = self._get_driver_for_loadbalancer(
                    context, old_pool.listener.loadbalancer_id)
            self._call_driver_operation(context,
                                        driver.pool.update,
                                        updated_pool,
                                        old_db_entity=old_pool)
        else:
            self.db.update_status(context, models.PoolV2, id,
                                  constants.DEFERRED)

        return self.db.get_pool(context, updated_pool.id).to_dict()

    def delete_pool(self, context, id):
        self.db.test_and_set_status(context, models.PoolV2, id,
                                    constants.PENDING_DELETE)
        db_pool = self.db.get_pool(context, id)

        if db_pool.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, db_pool.listener.loadbalancer_id)
            self._call_driver_operation(context, driver.pool.delete, db_pool)
        else:
            self.db.delete_pool(context, id)

    def get_pools(self, context, filters=None, fields=None):
        pools = self.db.get_pools(context, filters=filters)
        return [self.db._fields(pool.to_dict(), fields) for pool in pools]

    def get_pool(self, context, id, fields=None):
        pool_db = self.db.get_pool(context, id)
        return self.db._fields(pool_db.to_dict(), fields)

    def create_pool_member(self, context, member, pool_id):
        member = member.get('member')
        member_db = self.db.create_pool_member(context, member, pool_id)

        if member_db.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, member_db.pool.listener.loadbalancer_id)
            self._call_driver_operation(context,
                                        driver.member.create,
                                        member_db)
        else:
            self.db.update_status(context, models.MemberV2, member_db.id,
                                  constants.DEFERRED)

        return self.db.get_pool_member(context, member_db.id,
                                       pool_id).to_dict()

    def update_pool_member(self, context, id, member, pool_id):
        member = member.get('member')
        old_member = self.db.get_pool_member(context, id, pool_id)
        self.db.test_and_set_status(context, models.MemberV2, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_member = self.db.update_pool_member(context, id, member,
                                                        pool_id)
        except Exception as exc:
            self.db.update_status(context, models.MemberV2, id,
                                  old_member.status)
            raise exc
        # cannot unlink a member from a loadbalancer through an update
        # so no need to check if the old_member is attached
        if updated_member.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, updated_member.pool.listener.loadbalancer_id)
            self._call_driver_operation(context,
                                        driver.member.update,
                                        updated_member,
                                        old_db_entity=old_member)
        else:
            self.db.update_status(context, models.MemberV2, id,
                                  constants.DEFERRED)

        return self.db.get_pool_member(context, updated_member.id,
                                       pool_id).to_dict()

    def delete_pool_member(self, context, id, pool_id):
        self.db.test_and_set_status(context, models.MemberV2, id,
                                    constants.PENDING_DELETE)
        db_member = self.db.get_pool_member(context, id, pool_id)

        if db_member.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, db_member.pool.listener.loadbalancer_id)
            self._call_driver_operation(context,
                                        driver.member.delete,
                                        db_member)
        else:
            self.db.delete_pool_member(context, id, pool_id)

    def get_pool_members(self, context, pool_id, filters=None, fields=None):
        members = self.db.get_pool_members(context, pool_id, filters=filters)
        return [self.db._fields(member.to_dict(), fields)
                for member in members]

    def get_pool_member(self, context, id, pool_id, filters=None, fields=None):
        member = self.db.get_pool_member(context, id, pool_id, filters=filters)
        return member.to_dict()

    def create_healthmonitor(self, context, healthmonitor):
        healthmonitor = healthmonitor.get('healthmonitor')
        db_hm = self.db.create_healthmonitor(context, healthmonitor)

        # no need to call driver since on create it cannot be linked to a load
        # balancer, but will still update status to DEFERRED
        self.db.update_status(context, models.HealthMonitorV2, db_hm.id,
                              constants.DEFERRED)
        return self.db.get_healthmonitor(context, db_hm.id).to_dict()

    def update_healthmonitor(self, context, id, healthmonitor):
        healthmonitor = healthmonitor.get('healthmonitor')
        old_hm = self.db.get_healthmonitor(context, id)
        self.db.test_and_set_status(context, models.HealthMonitorV2, id,
                                    constants.PENDING_UPDATE)
        try:
            updated_hm = self.db.update_healthmonitor(context, id,
                                                      healthmonitor)
        except Exception as exc:
            self.db.update_status(context, models.HealthMonitorV2, id,
                                  old_hm.status)
            raise exc

        # cannot unlink a healthmonitor from a loadbalancer through an update
        # so no need to check if old_hm is attached
        if updated_hm.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, updated_hm.pool.listener.loadbalancer_id)
            self._call_driver_operation(context,
                                        driver.healthmonitor.update,
                                        updated_hm,
                                        old_db_entity=old_hm)
        else:
            self.db.update_status(context, models.HealthMonitorV2, id,
                                  constants.DEFERRED)

        return self.db.get_healthmonitor(context, updated_hm.id).to_dict()

    def delete_healthmonitor(self, context, id):
        self.db.test_and_set_status(context, models.HealthMonitorV2, id,
                                    constants.PENDING_DELETE)
        db_hm = self.db.get_healthmonitor(context, id)

        if db_hm.attached_to_loadbalancer():
            driver = self._get_driver_for_loadbalancer(
                context, db_hm.pool.listener.loadbalancer_id)
            self._call_driver_operation(
                context, driver.healthmonitor.delete, db_hm)
        else:
            self.db.delete_healthmonitor(context, id)

    def get_healthmonitor(self, context, id, fields=None):
        hm_db = self.db.get_healthmonitor(context, id)
        return self.db._fields(hm_db.to_dict(), fields)

    def get_healthmonitors(self, context, filters=None, fields=None):
        healthmonitors = self.db.get_healthmonitors(context, filters=filters)
        return [self.db._fields(healthmonitor.to_dict(), fields)
                for healthmonitor in healthmonitors]

    def stats(self, context, loadbalancer_id):
        loadbalancer = self.db.get_loadbalancer(context, loadbalancer_id)
        driver = self._get_driver_for_loadbalancer(context, loadbalancer_id)
        stats_data = driver.load_balancer.stats(context, loadbalancer)
        # if we get something from the driver -
        # update the db and return the value from db
        # else - return what we have in db
        if stats_data:
            self.db.update_loadbalancer_stats(context, loadbalancer_id,
                                              stats_data)
        db_stats = self.db.stats(context, loadbalancer_id)
        return {'stats': db_stats.to_dict()}

    def validate_provider(self, provider):
        if provider not in self.drivers:
            raise pconf.ServiceProviderNotFound(
                provider=provider, service_type=constants.LOADBALANCERV2)

    # NOTE(brandon-logan): these need to be concrete methods because the
    # neutron request pipeline calls these methods before the plugin methods
    # are ever called
    def get_members(self, context, filters=None, fields=None):
        pass

    def get_member(self, context, id, fields=None):
        pass
