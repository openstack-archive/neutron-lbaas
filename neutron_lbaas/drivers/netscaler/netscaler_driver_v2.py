
# Copyright 2015 Citrix Systems, Inc.
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


import abc

from neutron_lib import constants
from neutron_lib import context as ncontext
from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import service

from neutron_lbaas._i18n import _
from neutron_lbaas.drivers import driver_base
from neutron_lbaas.drivers import driver_mixins
from neutron_lbaas.drivers.netscaler import ncc_client

DEFAULT_PERIODIC_TASK_INTERVAL = "2"
DEFAULT_STATUS_COLLECTION = "True"
DEFAULT_PAGE_SIZE = "300"
DEFAULT_IS_SYNCRONOUS = "True"

PROV = "provisioning_status"
NETSCALER = "netscaler"

LOG = logging.getLogger(__name__)

NETSCALER_CC_OPTS = [
    cfg.StrOpt(
        'netscaler_ncc_uri',
        help=_('The URL to reach the NetScaler Control Center Server.'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_username',
        help=_('Username to login to the NetScaler Control Center Server.'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_password',
        secret=True,
        help=_('Password to login to the NetScaler Control Center Server.'),
    ),
    cfg.StrOpt(
        'periodic_task_interval',
        default=DEFAULT_PERIODIC_TASK_INTERVAL,
        help=_('Setting for periodic task collection interval from'
               'NetScaler Control Center Server..'),
    ),
    cfg.StrOpt(
        'is_synchronous',
        default=DEFAULT_IS_SYNCRONOUS,
        help=_('Setting for option to enable synchronous operations'
               'NetScaler Control Center Server.'),
    ),
    cfg.StrOpt(
        'netscaler_ncc_cleanup_mode',
        help=_(
            'Setting to enable/disable cleanup mode for NetScaler Control '
            'Center Server'),
    ),
    cfg.StrOpt(
        'netscaler_status_collection',
        default=DEFAULT_STATUS_COLLECTION + "," + DEFAULT_PAGE_SIZE,
        help=_('Setting for member status collection from'
               'NetScaler Control Center Server.'),
    )
]


if not hasattr(cfg.CONF, "netscaler_driver"):
    cfg.CONF.register_opts(NETSCALER_CC_OPTS, 'netscaler_driver')


LBS_RESOURCE = 'loadbalancers'
LB_RESOURCE = 'loadbalancer'
LISTENERS_RESOURCE = 'listeners'
LISTENER_RESOURCE = 'listener'
POOLS_RESOURCE = 'pools'
POOL_RESOURCE = 'pool'
MEMBERS_RESOURCE = 'members'
MEMBER_RESOURCE = 'member'
MONITORS_RESOURCE = 'healthmonitors'
MONITOR_RESOURCE = 'healthmonitor'
STATS_RESOURCE = 'stats'
PROV_SEGMT_ID = 'provider:segmentation_id'
PROV_NET_TYPE = 'provider:network_type'
DRIVER_NAME = 'netscaler_driver'
RESOURCE_PREFIX = 'v2.0/lbaas'
STATUS_PREFIX = 'oca/v2'
MEMBER_STATUS = 'memberstatus'
PAGE = 'page'
SIZE = 'size'


PROVISIONING_STATUS_TRACKER = []


class NetScalerLoadBalancerDriverV2(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(NetScalerLoadBalancerDriverV2, self).__init__(plugin)

        self.driver_conf = cfg.CONF.netscaler_driver
        self.admin_ctx = ncontext.get_admin_context()
        self._init_client()
        self._init_managers()
        self._init_status_collection()

    def _init_client(self):
        ncc_uri = self.driver_conf.netscaler_ncc_uri
        ncc_username = self.driver_conf.netscaler_ncc_username
        ncc_password = self.driver_conf.netscaler_ncc_password
        ncc_cleanup_mode = cfg.CONF.netscaler_driver.netscaler_ncc_cleanup_mode
        self.client = ncc_client.NSClient(ncc_uri,
                                          ncc_username,
                                          ncc_password,
                                          ncc_cleanup_mode)

    def _init_managers(self):
        self.load_balancer = NetScalerLoadBalancerManager(self)
        self.listener = NetScalerListenerManager(self)
        self.pool = NetScalerPoolManager(self)
        self.member = NetScalerMemberManager(self)
        self.health_monitor = NetScalerHealthMonitorManager(self)

    def _init_status_collection(self):
        self.status_conf = self.driver_conf.netscaler_status_collection
        self.periodic_task_interval = self.driver_conf.periodic_task_interval
        status_conf = self.driver_conf.netscaler_status_collection
        (is_status_collection,
            pagesize_status_collection) = status_conf.split(",")
        self.is_status_collection = True
        if is_status_collection.lower() == "false":
            self.is_status_collection = False
        self.pagesize_status_collection = pagesize_status_collection

        self._init_pending_status_tracker()

        NetScalerStatusService(self).start()

    def _init_pending_status_tracker(self):
        # Initialize PROVISIONING_STATUS_TRACKER for loadbalancers in
        # pending state
        db_lbs = self.plugin.db.get_loadbalancers(
            self.admin_ctx)
        for db_lb in db_lbs:
            if ((db_lb.id not in PROVISIONING_STATUS_TRACKER) and
                (db_lb.provider.provider_name == NETSCALER) and
                    (db_lb.provisioning_status.startswith("PENDING_"))):
                PROVISIONING_STATUS_TRACKER.append(db_lb.id)

    def collect_provision_status(self):

        msg = ("Collecting status ", self.periodic_task_interval)
        LOG.debug(msg)
        self._update_loadbalancers_provision_status()

    def _update_loadbalancers_provision_status(self):
        for lb_id in PROVISIONING_STATUS_TRACKER:
            lb_statuses = self._get_loadbalancer_statuses(lb_id)
            if lb_statuses:
                self._update_status_tree_in_db(
                    lb_id, lb_statuses["lb_statuses"])

    def _get_loadbalancer_statuses(self, lb_id):
        """Retrieve listener status from Control Center."""
        resource_path = "%s/%s/%s/statuses" % (RESOURCE_PREFIX,
                                               LBS_RESOURCE,
                                               lb_id)
        try:
            statuses = self.client.retrieve_resource(
                "GLOBAL", resource_path)[1]['dict']
        except ncc_client.NCCException as e:
            if e.is_not_found_exception():
                return {"lb_statuses": None}
            else:
                return None
        statuses = statuses["statuses"]
        return {"lb_statuses": statuses}

    def _update_status_tree_in_db(self, lb_id, loadbalancer_statuses):
        track_loadbalancer = {"track": False}
        db_lb = self.plugin.db.get_loadbalancer(self.admin_ctx,
                                                lb_id)

        if (not loadbalancer_statuses and
                db_lb.provisioning_status == constants.PENDING_DELETE):
            try:
                self.load_balancer.successful_completion(
                    self.admin_ctx, db_lb, delete=True)
            except Exception:
                LOG.error("error with successful completion")
            PROVISIONING_STATUS_TRACKER.remove(lb_id)
            return
        else:
            status_lb = loadbalancer_statuses["loadbalancer"]

        status_listeners = status_lb["listeners"]
        for db_listener in db_lb.listeners:
            db_listener.loadbalancer = db_lb
            status_listener = (self.
                               _update_entity_status_in_db(track_loadbalancer,
                                                           db_listener,
                                                           status_listeners,
                                                           self.listener))
            if not status_listener:
                continue

            db_pool = db_listener.default_pool

            if not db_pool:
                continue
            db_pool.listener = db_listener

            status_pools = status_listener['pools']
            status_pool = self._update_entity_status_in_db(track_loadbalancer,
                                                           db_pool,
                                                           status_pools,
                                                           self.pool)

            db_members = db_pool.members
            if not status_pool:
                continue
            status_members = status_pool['members']

            for db_member in db_members:
                db_member.pool = db_pool
                self._update_entity_status_in_db(track_loadbalancer,
                                                 db_member,
                                                 status_members,
                                                 self.member)

            db_hm = db_pool.healthmonitor
            if db_hm:
                db_hm.pool = db_pool
                status_hm = status_pool['healthmonitor']
                self._update_entity_status_in_db(track_loadbalancer,
                                                 db_hm,
                                                 [status_hm],
                                                 self.health_monitor)

        if not track_loadbalancer['track']:
            self._update_entity_status_in_db(
                track_loadbalancer, db_lb, status_lb, self.load_balancer)
            if not track_loadbalancer['track']:
                PROVISIONING_STATUS_TRACKER.remove(lb_id)

    def _update_entity_status_in_db(self, track_loadbalancer,
                                    db_entity,
                                    status_entities,
                                    entity_manager):
        if isinstance(status_entities, list):
            entity_status = self._get_entity_status(
                db_entity.id, status_entities)
        else:
            entity_status = status_entities

        self._check_and_update_entity_status_in_db(
            track_loadbalancer, db_entity, entity_status, entity_manager)
        return entity_status

    def _get_entity_status(self, entity_id, entities_status):
        for entity_status in entities_status:
            if entity_status and entity_status['id'] == entity_id:
                return entity_status
        return None

    def _check_and_update_entity_status_in_db(self, track_loadbalancer,
                                              db_entity,
                                              entity_status, entity_manager):

        if not db_entity.provisioning_status.startswith("PENDING_"):
            # no operation is attempted on this entity
            return
        if entity_status:
            if entity_status[PROV].startswith("PENDING_"):
                # an entity is not finished provisioning. Continue to track
                track_loadbalancer['track'] = True
                return

            if entity_status[PROV] == constants.ERROR:
                # Marked for failed completion
                try:
                    entity_manager.failed_completion(
                        self.admin_ctx, db_entity)
                except Exception:
                    LOG.error("error with failed completion")
                return

        if db_entity.provisioning_status == constants.PENDING_DELETE:
            # entity is under deletion
            # if entity is missing in lb status tree it should to be
            # deleted
            if entity_status:
                msg = ('Invalid status set for delete of %s in statuses',
                       db_entity.id)
                LOG.error(msg)
                return
            try:
                entity_manager.successful_completion(
                    self.admin_ctx, db_entity, delete=True)
            except Exception:
                LOG.error("error with successful completion")
            return

        if entity_status[PROV] != constants.ACTIVE:
            msg = ('Invalid prov status for %s, should be ACTIVE '
                   "for CREATE and UPDATE",
                   db_entity.id)
            LOG.error(msg)
            return
        try:
            entity_manager.successful_completion(
                self.admin_ctx, db_entity)
        except Exception:
            LOG.error("error with successful completion")

        return


class NetScalerCommonManager(driver_mixins.BaseManagerMixin):

    def __init__(self, driver):
        super(NetScalerCommonManager, self).__init__(driver)
        self.payload_preparer = PayloadPreparer()
        self.client = self.driver.client

        self.is_synchronous = self.driver.driver_conf.is_synchronous
        if self.is_synchronous.lower() == "false":
            self.is_synchronous = False
        else:
            self.is_synchronous = True

    def create(self, context, obj):
        LOG.debug("%s, create %s", self.__class__.__name__, obj.id)
        try:
            self.create_entity(context, obj)
            if self.is_synchronous:
                self.successful_completion(context, obj)
            else:
                self.track_provision_status(obj)
        except Exception:
            self.failed_completion(context, obj)
            raise

    def update(self, context, old_obj, obj):
        LOG.debug("%s, update %s", self.__class__.__name__, old_obj.id)
        try:
            self.update_entity(context, old_obj, obj)
            if self.is_synchronous:
                self.successful_completion(context, obj)
            else:
                self.track_provision_status(obj)
        except Exception:
            self.failed_completion(context, obj)
            raise

    def delete(self, context, obj):
        LOG.debug("%s, delete %s", self.__class__.__name__, obj.id)
        try:
            self.delete_entity(context, obj)
            if self.is_synchronous:
                self.successful_completion(context, obj, delete=True)
            else:
                self.track_provision_status(obj)
        except Exception:
            self.failed_completion(context, obj)
            raise

    def track_provision_status(self, obj):
        for lb in self._get_loadbalancers(obj):
            if lb.id not in PROVISIONING_STATUS_TRACKER:
                PROVISIONING_STATUS_TRACKER.append(lb.id)

    def _get_loadbalancers(self, obj):
        lbs = []
        lbs.append(obj.root_loadbalancer)
        return lbs

    @abc.abstractmethod
    def create_entity(self, context, obj):
        pass

    @abc.abstractmethod
    def update_entity(self, context, old_obj, obj):
        pass

    @abc.abstractmethod
    def delete_entity(self, context, obj):
        pass


class NetScalerLoadBalancerManager(NetScalerCommonManager,
                                   driver_base.BaseLoadBalancerManager):

    def __init__(self, driver):
        driver_base.BaseLoadBalancerManager.__init__(self, driver)
        NetScalerCommonManager.__init__(self, driver)

    def refresh(self, context, lb_obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        LOG.debug("LB refresh %s", lb_obj.id)

    def stats(self, context, lb_obj):
        pass

    def create_entity(self, context, lb_obj):
        ncc_lb = self.payload_preparer.prepare_lb_for_creation(lb_obj)
        vip_subnet_id = lb_obj.vip_subnet_id
        network_info = self.payload_preparer.\
            get_network_info(context, self.driver.plugin, vip_subnet_id)
        ncc_lb.update(network_info)
        msg = _("NetScaler driver lb creation: %s") % repr(ncc_lb)
        LOG.debug(msg)
        resource_path = "%s/%s" % (RESOURCE_PREFIX, LBS_RESOURCE)
        self.client.create_resource(context.tenant_id, resource_path,
                                    LB_RESOURCE, ncc_lb)

    def update_entity(self, context, old_lb_obj, lb_obj):
        update_lb = self.payload_preparer.prepare_lb_for_update(lb_obj)
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, LBS_RESOURCE, lb_obj.id)
        msg = (_("NetScaler driver lb_obj %(lb_obj_id)s update: %(lb_obj)s") %
               {"lb_obj_id": old_lb_obj.id, "lb_obj": repr(lb_obj)})
        LOG.debug(msg)
        self.client.update_resource(context.tenant_id, resource_path,
                                    LB_RESOURCE, update_lb)

    def delete_entity(self, context, lb_obj):
        """Delete a loadbalancer on a NetScaler device."""
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, LBS_RESOURCE, lb_obj.id)
        msg = _("NetScaler driver lb_obj removal: %s") % lb_obj.id
        LOG.debug(msg)
        self.client.remove_resource(context.tenant_id, resource_path)


class NetScalerListenerManager(NetScalerCommonManager,
                               driver_base.BaseListenerManager):

    def __init__(self, driver):
        driver_base.BaseListenerManager.__init__(self, driver)
        NetScalerCommonManager.__init__(self, driver)

    def stats(self, context, listener):
        # returning dummy status now
        LOG.debug(
            "Tenant id %s , Listener stats %s", context.tenant_id, listener.id)
        return {
            "bytes_in": 0,
            "bytes_out": 0,
            "active_connections": 0,
            "total_connections": 0
        }

    def create_entity(self, context, listener):
        """Listener is created with loadbalancer """
        ncc_listener = self.payload_preparer.prepare_listener_for_creation(
            listener)
        msg = _("NetScaler driver listener creation: %s") % repr(ncc_listener)
        LOG.debug(msg)
        resource_path = "%s/%s" % (RESOURCE_PREFIX, LISTENERS_RESOURCE)
        self.client.create_resource(context.tenant_id, resource_path,
                                    LISTENER_RESOURCE, ncc_listener)

    def update_entity(self, context, old_listener, listener):
        update_listener = self.payload_preparer.prepare_listener_for_update(
            listener)
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, LISTENERS_RESOURCE,
                                      listener.id)
        msg = (_("NetScaler driver listener %(listener_id)s "
                 "update: %(listener_obj)s") %
               {"listener_id": old_listener.id,
                "listener_obj": repr(listener)})
        LOG.debug(msg)
        self.client.update_resource(context.tenant_id, resource_path,
                                    LISTENER_RESOURCE, update_listener)

    def delete_entity(self, context, listener):
        """Delete a listener on a NetScaler device."""
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, LISTENERS_RESOURCE,
                                      listener.id)
        msg = _("NetScaler driver listener removal: %s") % listener.id
        LOG.debug(msg)
        self.client.remove_resource(context.tenant_id, resource_path)


class NetScalerPoolManager(NetScalerCommonManager,
                           driver_base.BasePoolManager):

    def __init__(self, driver):
        driver_base.BasePoolManager.__init__(self, driver)
        NetScalerCommonManager.__init__(self, driver)

    def create_entity(self, context, pool):
        ncc_pool = self.payload_preparer.prepare_pool_for_creation(
            pool)
        msg = _("NetScaler driver pool creation: %s") % repr(ncc_pool)
        LOG.debug(msg)
        resource_path = "%s/%s" % (RESOURCE_PREFIX, POOLS_RESOURCE)
        self.client.create_resource(context.tenant_id, resource_path,
                                    POOL_RESOURCE, ncc_pool)

    def update_entity(self, context, old_pool, pool):
        update_pool = self.payload_preparer.prepare_pool_for_update(pool)
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, POOLS_RESOURCE,
                                      pool.id)
        msg = (_("NetScaler driver pool %(pool_id)s update: %(pool_obj)s") %
               {"pool_id": old_pool.id, "pool_obj": repr(pool)})
        LOG.debug(msg)
        self.client.update_resource(context.tenant_id, resource_path,
                                    POOL_RESOURCE, update_pool)

    def delete_entity(self, context, pool):
        """Delete a pool on a NetScaler device."""
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, POOLS_RESOURCE,
                                      pool.id)
        msg = _("NetScaler driver pool removal: %s") % pool.id
        LOG.debug(msg)
        self.client.remove_resource(context.tenant_id, resource_path)


class NetScalerMemberManager(NetScalerCommonManager,
                             driver_base.BaseMemberManager):

    def __init__(self, driver):
        driver_base.BaseMemberManager.__init__(self, driver)
        NetScalerCommonManager.__init__(self, driver)

    def create_entity(self, context, member):

        ncc_member = self.payload_preparer.prepare_member_for_creation(member)
        subnet_id = member.subnet_id
        network_info = (self.payload_preparer.
                        get_network_info(context, self.driver.plugin,
                                         subnet_id))
        ncc_member.update(network_info)
        msg = _("NetScaler driver member creation: %s") % repr(ncc_member)
        LOG.debug(msg)
        parent_pool_id = member.pool.id
        resource_path = "%s/%s/%s/%s" % (RESOURCE_PREFIX, POOLS_RESOURCE,
                                         parent_pool_id, MEMBERS_RESOURCE)
        self.client.create_resource(context.tenant_id, resource_path,
                                    MEMBER_RESOURCE, ncc_member)

    def update_entity(self, context, old_member, member):
        parent_pool_id = member.pool.id
        update_member = self.payload_preparer.prepare_member_for_update(member)
        resource_path = "%s/%s/%s/%s/%s" % (RESOURCE_PREFIX,
                                            POOLS_RESOURCE,
                                            parent_pool_id,
                                            MEMBERS_RESOURCE,
                                            member.id)
        msg = (_("NetScaler driver member %(member_id)s "
                 "update: %(member_obj)s") %
               {"member_id": old_member.id, "member_obj": repr(member)})
        LOG.debug(msg)
        self.client.update_resource(context.tenant_id, resource_path,
                                    MEMBER_RESOURCE, update_member)

    def delete_entity(self, context, member):
        """Delete a member on a NetScaler device."""
        parent_pool_id = member.pool.id
        resource_path = "%s/%s/%s/%s/%s" % (RESOURCE_PREFIX,
                                            POOLS_RESOURCE,
                                            parent_pool_id,
                                            MEMBERS_RESOURCE,
                                            member.id)
        msg = _("NetScaler driver member removal: %s") % member.id
        LOG.debug(msg)
        self.client.remove_resource(context.tenant_id, resource_path)


class NetScalerHealthMonitorManager(NetScalerCommonManager,
                                    driver_base.BaseHealthMonitorManager):

    def __init__(self, driver):
        driver_base.BaseHealthMonitorManager.__init__(self, driver)
        NetScalerCommonManager.__init__(self, driver)

    def create_entity(self, context, hm):
        ncc_hm = self.payload_preparer.prepare_healthmonitor_for_creation(hm)
        msg = _("NetScaler driver healthmonitor creation: %s") % repr(ncc_hm)
        LOG.debug(msg)
        resource_path = "%s/%s" % (RESOURCE_PREFIX, MONITORS_RESOURCE)
        self.client.create_resource(context.tenant_id, resource_path,
                                    MONITOR_RESOURCE, ncc_hm)

    def update_entity(self, context, old_healthmonitor, hm):
        update_hm = self.payload_preparer.prepare_healthmonitor_for_update(hm)
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, MONITORS_RESOURCE,
                                      hm.id)
        msg = (_("NetScaler driver healthmonitor %(healthmonitor_id)s "
                 "update: %(healthmonitor_obj)s") %
               {"healthmonitor_id": old_healthmonitor.id,
                "healthmonitor_obj": repr(hm)})
        LOG.debug(msg)
        self.client.update_resource(context.tenant_id, resource_path,
                                    MONITOR_RESOURCE, update_hm)

    def delete_entity(self, context, hm):
        """Delete a healthmonitor on a NetScaler device."""
        resource_path = "%s/%s/%s" % (RESOURCE_PREFIX, MONITORS_RESOURCE,
                                      hm.id)
        msg = _("NetScaler driver healthmonitor removal: %s") % hm.id
        LOG.debug(msg)
        self.client.remove_resource(context.tenant_id, resource_path)


class PayloadPreparer(object):

    def prepare_lb_for_creation(self, lb):
        creation_attrs = {
            'id': lb.id,
            'tenant_id': lb.tenant_id,
            'vip_address': lb.vip_address,
            'vip_subnet_id': lb.vip_subnet_id,
        }
        update_attrs = self.prepare_lb_for_update(lb)
        creation_attrs.update(update_attrs)

        return creation_attrs

    def prepare_lb_for_update(self, lb):
        return {
            'name': lb.name,
            'description': lb.description,
            'admin_state_up': lb.admin_state_up,
        }

    def prepare_listener_for_creation(self, listener):
        creation_attrs = {
            'id': listener.id,
            'tenant_id': listener.tenant_id,
            'protocol': listener.protocol,
            'protocol_port': listener.protocol_port,
            'loadbalancer_id': listener.loadbalancer_id
        }
        update_attrs = self.prepare_listener_for_update(listener)
        creation_attrs.update(update_attrs)
        return creation_attrs

    def prepare_listener_for_update(self, listener):
        sni_container_ids = self.prepare_sni_container_ids(listener)
        listener_dict = {
            'name': listener.name,
            'description': listener.description,
            'sni_container_ids': sni_container_ids,
            'default_tls_container_id': listener.default_tls_container_id,
            'connection_limit': listener.connection_limit,
            'admin_state_up': listener.admin_state_up
        }
        return listener_dict

    def prepare_pool_for_creation(self, pool):
        create_attrs = {
            'id': pool.id,
            'tenant_id': pool.tenant_id,
            'listener_id': pool.listener.id,
            'protocol': pool.protocol,
        }
        update_attrs = self.prepare_pool_for_update(pool)
        create_attrs.update(update_attrs)
        return create_attrs

    def prepare_pool_for_update(self, pool):
        update_attrs = {
            'name': pool.name,
            'description': pool.description,
            'lb_algorithm': pool.lb_algorithm,
            'admin_state_up': pool.admin_state_up
        }
        if pool.session_persistence:
            peristence = pool.session_persistence
            peristence_payload = self.prepare_sessionpersistence(peristence)
            update_attrs['session_persistence'] = peristence_payload
        return update_attrs

    def prepare_sessionpersistence(self, persistence):
        return {
            'type': persistence.type,
            'cookie_name': persistence.cookie_name
        }

    def prepare_members_for_pool(self, members):
        members_attrs = []
        for member in members:
            member_attrs = self.prepare_member_for_creation(member)
            members_attrs.append(member_attrs)
        return members_attrs

    def prepare_member_for_creation(self, member):
        creation_attrs = {
            'id': member.id,
            'tenant_id': member.tenant_id,
            'address': member.address,
            'protocol_port': member.protocol_port,
            'subnet_id': member.subnet_id
        }
        update_attrs = self.prepare_member_for_update(member)
        creation_attrs.update(update_attrs)
        return creation_attrs

    def prepare_member_for_update(self, member):
        return {
            'weight': member.weight,
            'admin_state_up': member.admin_state_up,
        }

    def prepare_healthmonitor_for_creation(self, health_monitor):
        creation_attrs = {
            'id': health_monitor.id,
            'tenant_id': health_monitor.tenant_id,
            'pool_id': health_monitor.pool.id,
            'type': health_monitor.type,
        }
        update_attrs = self.prepare_healthmonitor_for_update(health_monitor)
        creation_attrs.update(update_attrs)
        return creation_attrs

    def prepare_healthmonitor_for_update(self, health_monitor):
        ncc_hm = {
            'delay': health_monitor.delay,
            'timeout': health_monitor.timeout,
            'max_retries': health_monitor.max_retries,
            'admin_state_up': health_monitor.admin_state_up,
        }
        if health_monitor.type in ['HTTP', 'HTTPS']:
            ncc_hm['http_method'] = health_monitor.http_method
            ncc_hm['url_path'] = health_monitor.url_path
            ncc_hm['expected_codes'] = health_monitor.expected_codes
        return ncc_hm

    def get_network_info(self, context, plugin, subnet_id):
        network_info = {}
        subnet = plugin.db._core_plugin.get_subnet(context, subnet_id)
        network_id = subnet['network_id']
        network = plugin.db._core_plugin.get_network(context, network_id)
        network_info['network_id'] = network_id
        network_info['subnet_id'] = subnet_id
        if PROV_NET_TYPE in network:
            network_info['network_type'] = network[PROV_NET_TYPE]
        if PROV_SEGMT_ID in network:
            network_info['segmentation_id'] = network[PROV_SEGMT_ID]
        return network_info

    def prepare_sni_container_ids(self, listener):
        sni_container_ids = []
        for sni_container in listener.sni_containers:
            sni_container_ids.append(sni_container.tls_container_id)
        return sni_container_ids


class NetScalerStatusService(service.Service):

    def __init__(self, driver):
        super(NetScalerStatusService, self).__init__()
        self.driver = driver

    def start(self):
        super(NetScalerStatusService, self).start()
        self.tg.add_timer(
            int(self.driver.periodic_task_interval),
            self.driver.collect_provision_status,
            None
        )
