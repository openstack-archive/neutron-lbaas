#
# Copyright 2014 OpenStack Foundation.  All rights reserved
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


from oslo.db import exception
from sqlalchemy import orm
from sqlalchemy.orm import exc

from neutron.api.v2 import attributes
from neutron.db import common_db_mixin as base_db
from neutron.db.loadbalancer import models
from neutron.extensions import loadbalancerv2
from neutron import manager
from neutron.openstack.common import excutils
from neutron.openstack.common import uuidutils
from neutron.plugins.common import constants
from neutron.services.loadbalancer import constants as lb_const
from neutron.services.loadbalancer import data_models


class LoadBalancerPluginDbv2(base_db.CommonDbMixin):
    """Wraps loadbalancer with SQLAlchemy models.

    A class that wraps the implementation of the Neutron loadbalancer
    plugin database access interface using SQLAlchemy models.
    """

    @property
    def _core_plugin(self):
        return manager.NeutronManager.get_plugin()

    def _get_resource(self, context, model, id, for_update=False):
        resource = None
        try:
            if for_update:
                query = self._model_query(context, model).filter(
                    model.id == id).with_lockmode('update')
                resource = query.one()
            else:
                resource = self._get_by_id(context, model, id)
        except exc.NoResultFound:
            with excutils.save_and_reraise_exception(reraise=False) as ctx:
                if issubclass(model, (models.LoadBalancer, models.Listener,
                                      models.PoolV2, models.MemberV2,
                                      models.HealthMonitorV2,
                                      models.LoadBalancerStatistics,
                                      models.SessionPersistenceV2)):
                    raise loadbalancerv2.EntityNotFound(name=model.NAME, id=id)
                ctx.reraise = True
        return resource

    def _resource_exists(self, context, model, id):
        try:
            self._get_by_id(context, model, id)
        except exc.NoResultFound:
            return False
        return True

    def _get_resources(self, context, model, filters=None):
        query = self._get_collection_query(context, model,
                                           filters=filters)
        return [model_instance for model_instance in query]

    def _create_port_for_load_balancer(self, context, lb_db, ip_address):
        # resolve subnet and create port
        subnet = self._core_plugin.get_subnet(context, lb_db.vip_subnet_id)
        fixed_ip = {'subnet_id': subnet['id']}
        if ip_address and ip_address != attributes.ATTR_NOT_SPECIFIED:
            fixed_ip['ip_address'] = ip_address

        port_data = {
            'tenant_id': lb_db.tenant_id,
            'name': 'loadbalancer-' + lb_db.id,
            'network_id': subnet['network_id'],
            'mac_address': attributes.ATTR_NOT_SPECIFIED,
            'admin_state_up': False,
            'device_id': '',
            'device_owner': '',
            'fixed_ips': [fixed_ip]
        }

        port = self._core_plugin.create_port(context, {'port': port_data})
        lb_db.vip_port_id = port['id']
        for fixed_ip in port['fixed_ips']:
            if fixed_ip['subnet_id'] == lb_db.vip_subnet_id:
                lb_db.vip_address = fixed_ip['ip_address']
                break

        # explicitly sync session with db
        context.session.flush()

    def _create_loadbalancer_stats(self, context, loadbalancer_id, data=None):
        # This is internal method to add load balancer statistics.  It won't
        # be exposed to API
        data = data or {}
        stats_db = models.LoadBalancerStatistics(
            loadbalancer_id=loadbalancer_id,
            bytes_in=data.get(lb_const.STATS_IN_BYTES, 0),
            bytes_out=data.get(lb_const.STATS_OUT_BYTES, 0),
            active_connections=data.get(lb_const.STATS_ACTIVE_CONNECTIONS, 0),
            total_connections=data.get(lb_const.STATS_TOTAL_CONNECTIONS, 0)
        )
        return stats_db

    def _delete_loadbalancer_stats(self, context, loadbalancer_id):
        # This is internal method to delete pool statistics. It won't
        # be exposed to API
        with context.session.begin(subtransactions=True):
            stats_qry = context.session.query(models.LoadBalancerStatistics)
            try:
                stats = stats_qry.filter_by(
                    loadbalancer_id=loadbalancer_id).one()
            except exc.NoResultFound:
                raise loadbalancerv2.EntityNotFound(
                    name=models.LoadBalancerStatistics.NAME,
                    id=loadbalancer_id)
            context.session.delete(stats)

    def _load_id_and_tenant_id(self, context, model_dict):
        model_dict['id'] = uuidutils.generate_uuid()
        model_dict['tenant_id'] = self._get_tenant_id_for_create(
            context, model_dict)

    def assert_modification_allowed(self, obj):
        status = getattr(obj, 'status', None)
        if status in [constants.PENDING_DELETE, constants.PENDING_UPDATE,
                      constants.PENDING_CREATE]:
            id = getattr(obj, 'id', None)
            raise loadbalancerv2.StateInvalid(id=id, state=status)

    def test_and_set_status(self, context, model, id, status):
        with context.session.begin(subtransactions=True):
            model_db = self._get_resource(context, model, id, for_update=True)
            self.assert_modification_allowed(model_db)
            if model_db.status != status:
                model_db.status = status

    def update_status(self, context, model, id, status):
        with context.session.begin(subtransactions=True):
            if issubclass(model, models.LoadBalancer):
                try:
                    model_db = (self._model_query(context, model).
                                filter(model.id == id).
                                options(orm.noload('vip_port')).
                                one())
                except exc.NoResultFound:
                    raise loadbalancerv2.EntityNotFound(
                        name=models.LoadBalancer.NAME, id=id)
            else:
                model_db = self._get_resource(context, model, id)
            if model_db.status != status:
                model_db.status = status

    def create_loadbalancer(self, context, loadbalancer):
        with context.session.begin(subtransactions=True):
            self._load_id_and_tenant_id(context, loadbalancer)
            vip_address = loadbalancer.pop('vip_address')
            loadbalancer['status'] = constants.PENDING_CREATE
            lb_db = models.LoadBalancer(**loadbalancer)
            context.session.add(lb_db)
            context.session.flush()
            lb_db.stats = self._create_loadbalancer_stats(
                context, lb_db.id)
            context.session.add(lb_db)

        # create port outside of lb create transaction since it can sometimes
        # cause lock wait timeouts
        try:
            self._create_port_for_load_balancer(context, lb_db, vip_address)
        except Exception:
            with excutils.save_and_reraise_exception():
                context.session.delete(lb_db)
                context.session.flush()
        return data_models.LoadBalancer.from_sqlalchemy_model(lb_db)

    def update_loadbalancer(self, context, id, loadbalancer):
        with context.session.begin(subtransactions=True):
            lb_db = self._get_resource(context, models.LoadBalancer, id)
            lb_db.update(loadbalancer)
        return data_models.LoadBalancer.from_sqlalchemy_model(lb_db)

    def delete_loadbalancer(self, context, id):
        with context.session.begin(subtransactions=True):
            lb_db = self._get_resource(context, models.LoadBalancer, id)
            context.session.delete(lb_db)
        if lb_db.vip_port:
            self._core_plugin.delete_port(context, lb_db.vip_port_id)

    def get_loadbalancers(self, context, filters=None):
        lb_dbs = self._get_resources(context, models.LoadBalancer,
                                     filters=filters)
        return [data_models.LoadBalancer.from_sqlalchemy_model(lb_db)
                for lb_db in lb_dbs]

    def get_loadbalancer(self, context, id):
        lb_db = self._get_resource(context, models.LoadBalancer, id)
        return data_models.LoadBalancer.from_sqlalchemy_model(lb_db)

    def _validate_listener_data(self, context, listener):
        pool_id = listener.get('default_pool_id')
        lb_id = listener.get('loadbalancer_id')
        if lb_id:
            if not self._resource_exists(context, models.LoadBalancer,
                                         lb_id):
                raise loadbalancerv2.EntityNotFound(
                    name=models.LoadBalancer.NAME, id=lb_id)
        if pool_id:
            pool = self._get_resource(context, models.PoolV2, pool_id)
            if pool.protocol != listener.get('protocol'):
                raise loadbalancerv2.ListenerPoolProtocolMismatch(
                    listener_proto=listener['protocol'],
                    pool_proto=pool.protocol)
            filters = {'default_pool_id': [pool_id]}
            listenerpools = self._get_resources(context,
                                                models.Listener,
                                                filters=filters)
            if listenerpools:
                raise loadbalancerv2.EntityInUse(
                    entity_using=models.Listener.NAME,
                    id=listenerpools[0].id,
                    entity_in_use=models.PoolV2.NAME)

    def create_listener(self, context, listener):
        try:
            with context.session.begin(subtransactions=True):
                self._load_id_and_tenant_id(context, listener)
                listener['status'] = constants.PENDING_CREATE
                # Check for unspecified loadbalancer_id and listener_id and
                # set to None
                for id in ['loadbalancer_id', 'default_pool_id']:
                    if listener.get(id) == attributes.ATTR_NOT_SPECIFIED:
                        listener[id] = None
                self._validate_listener_data(context, listener)
                listener_db_entry = models.Listener(**listener)
                context.session.add(listener_db_entry)
        except exception.DBDuplicateEntry:
            raise loadbalancerv2.LoadBalancerListenerProtocolPortExists(
                lb_id=listener['loadbalancer_id'],
                protocol_port=listener['protocol_port'])
        return data_models.Listener.from_sqlalchemy_model(listener_db_entry)

    def update_listener(self, context, id, listener):
        with context.session.begin(subtransactions=True):
            listener_db = self._get_resource(context, models.Listener, id)
            # Do not allow changing loadbalancer ids
            if listener_db.loadbalancer_id and listener.get('loadbalancer_id'):
                raise loadbalancerv2.AttributeIDImmutable(
                    attribute='loadbalancer_id')
            # Do not allow changing pool ids
            if listener_db.default_pool_id and listener.get('default_pool_id'):
                raise loadbalancerv2.AttributeIDImmutable(
                    attribute='default_pool_id')
            if not listener.get('protocol'):
                # User did not intend to change the protocol so we will just
                # use the same protocol already stored so the validation knows
                listener['protocol'] = listener_db.protocol
            self._validate_listener_data(context, listener)
            listener_db.update(listener)
        context.session.refresh(listener_db)
        return data_models.Listener.from_sqlalchemy_model(listener_db)

    def delete_listener(self, context, id):
        listener_db_entry = self._get_resource(context, models.Listener, id)
        with context.session.begin(subtransactions=True):
            context.session.delete(listener_db_entry)

    def get_listeners(self, context, filters=None):
        listener_dbs = self._get_resources(context, models.Listener,
                                           filters=filters)
        return [data_models.Listener.from_sqlalchemy_model(listener_db)
                for listener_db in listener_dbs]

    def get_listener(self, context, id):
        listener_db = self._get_resource(context, models.Listener, id)
        return data_models.Listener.from_sqlalchemy_model(listener_db)

    def _create_session_persistence_db(self, session_info, pool_id):
        session_info['pool_id'] = pool_id
        return models.SessionPersistenceV2(**session_info)

    def _update_pool_session_persistence(self, context, pool_id, info):
        pool = self._get_resource(context, models.PoolV2, pool_id)
        with context.session.begin(subtransactions=True):
            # Update sessionPersistence table
            sess_qry = context.session.query(models.SessionPersistenceV2)
            sesspersist_db = sess_qry.filter_by(pool_id=pool_id).first()

            # Insert a None cookie_info if it is not present to overwrite an
            # existing value in the database.
            if 'cookie_name' not in info:
                info['cookie_name'] = None

            if sesspersist_db:
                sesspersist_db.update(info)
            else:
                info['pool_id'] = pool_id
                sesspersist_db = models.SessionPersistenceV2(**info)
                context.session.add(sesspersist_db)
                # Update pool table
                pool.session_persistence = sesspersist_db
            context.session.add(pool)

    def _delete_session_persistence(self, context, pool_id):
        with context.session.begin(subtransactions=True):
            sess_qry = context.session.query(models.SessionPersistenceV2)
            sess_qry.filter_by(pool_id=pool_id).delete()

    def create_pool(self, context, pool):
        with context.session.begin(subtransactions=True):
            self._load_id_and_tenant_id(context, pool)
            pool['status'] = constants.PENDING_CREATE
            if pool['healthmonitor_id'] == attributes.ATTR_NOT_SPECIFIED:
                pool['healthmonitor_id'] = None
            hm_id = pool['healthmonitor_id']
            if hm_id:
                if not self._resource_exists(context, models.HealthMonitorV2,
                                             hm_id):
                    raise loadbalancerv2.EntityNotFound(
                        name=models.HealthMonitorV2.NAME, id=hm_id)

                filters = {'healthmonitor_id': [hm_id]}
                hmpools = self._get_resources(context,
                                              models.PoolV2,
                                              filters=filters)
                if hmpools:
                    raise loadbalancerv2.EntityInUse(
                        entity_using=models.PoolV2.NAME,
                        id=hmpools[0].id,
                        entity_in_use=models.HealthMonitorV2.NAME)

            session_info = pool.pop('session_persistence')
            pool_db = models.PoolV2(**pool)

            if session_info:
                s_p = self._create_session_persistence_db(session_info,
                                                          pool_db.id)
                pool_db.sessionpersistence = s_p

            context.session.add(pool_db)
        return data_models.Pool.from_sqlalchemy_model(pool_db)

    def update_pool(self, context, id, pool):
        with context.session.begin(subtransactions=True):
            pool_db = self._get_resource(context, models.PoolV2, id)
            hm_id = pool.get('healthmonitor_id')
            if hm_id:
                if pool_db.healthmonitor and hm_id:
                    raise loadbalancerv2.AttributeIDImmutable(
                        attribute='healthmonitor_id')
                if not self._resource_exists(context, models.HealthMonitorV2,
                                             hm_id):
                    raise loadbalancerv2.EntityNotFound(
                        name=models.HealthMonitorV2.NAME,
                        id=hm_id)
                filters = {'healthmonitor_id': [hm_id]}
                hmpools = self._get_resources(context,
                                              models.PoolV2,
                                              filters=filters)
                if hmpools:
                    raise loadbalancerv2.EntityInUse(
                        entity_using=models.PoolV2.NAME,
                        id=hmpools[0].id,
                        entity_in_use=models.HealthMonitorV2.NAME)

            sp = pool.pop('session_persistence', None)
            if sp:
                self._update_pool_session_persistence(context, id, sp)
            else:
                self._delete_session_persistence(context, id)

            pool_db.update(pool)
        context.session.refresh(pool_db)
        return data_models.Pool.from_sqlalchemy_model(pool_db)

    def delete_pool(self, context, id):
        with context.session.begin(subtransactions=True):
            pool_db = self._get_resource(context, models.PoolV2, id)
            context.session.delete(pool_db)

    def get_pools(self, context, filters=None):
        pool_dbs = self._get_resources(context, models.PoolV2, filters=filters)
        return [data_models.Pool.from_sqlalchemy_model(pool_db)
                for pool_db in pool_dbs]

    def get_pool(self, context, id):
        pool_db = self._get_resource(context, models.PoolV2, id)
        return data_models.Pool.from_sqlalchemy_model(pool_db)

    def create_pool_member(self, context, member, pool_id):
        try:
            with context.session.begin(subtransactions=True):
                if not self._resource_exists(context, models.PoolV2, pool_id):
                    raise loadbalancerv2.EntityNotFound(
                        name=models.PoolV2.NAME, id=pool_id)
                self._load_id_and_tenant_id(context, member)
                member['pool_id'] = pool_id
                member['status'] = constants.PENDING_CREATE
                member_db = models.MemberV2(**member)
                context.session.add(member_db)
        except exception.DBDuplicateEntry:
            raise loadbalancerv2.MemberExists(address=member['address'],
                                              port=member['protocol_port'],
                                              pool=pool_id)
        return data_models.Member.from_sqlalchemy_model(member_db)

    def update_pool_member(self, context, id, member, pool_id):
        with context.session.begin(subtransactions=True):
            if not self._resource_exists(context, models.PoolV2, pool_id):
                raise loadbalancerv2.MemberNotFoundForPool(pool_id=pool_id,
                                                           member_id=id)
            member_db = self._get_resource(context, models.MemberV2, id)
            member_db.update(member)
        context.session.refresh(member_db)
        return data_models.Member.from_sqlalchemy_model(member_db)

    def delete_pool_member(self, context, id, pool_id):
        with context.session.begin(subtransactions=True):
            if not self._resource_exists(context, models.PoolV2, pool_id):
                raise loadbalancerv2.MemberNotFoundForPool(pool_id=pool_id,
                                                           member_id=id)
            member_db = self._get_resource(context, models.MemberV2, id)
            context.session.delete(member_db)

    def get_pool_members(self, context, pool_id, filters=None):
        filters = filters or {}
        filters.update({'pool_id': [pool_id]})
        member_dbs = self._get_resources(context, models.MemberV2,
                                         filters=filters)
        return [data_models.Member.from_sqlalchemy_model(member_db)
                for member_db in member_dbs]

    def get_pool_member(self, context, id, pool_id, filters=None):
        # NOTE(blogan): filters parameter is needed because neutron's extension
        # code calls this method with that parameter even though we do not
        # need it
        member_db = self._get_resource(context, models.MemberV2, id)
        if member_db.pool_id != pool_id:
            raise loadbalancerv2.MemberNotFoundForPool(member_id=id,
                                                       pool_id=pool_id)
        return data_models.Member.from_sqlalchemy_model(member_db)

    def delete_member(self, context, id):
        with context.session.begin(subtransactions=True):
            member_db = self._get_resource(context, models.MemberV2, id)
            context.session.delete(member_db)

    def create_healthmonitor(self, context, healthmonitor):
        with context.session.begin(subtransactions=True):
            self._load_id_and_tenant_id(context, healthmonitor)
            healthmonitor['status'] = constants.PENDING_CREATE
            hm_db_entry = models.HealthMonitorV2(**healthmonitor)
            context.session.add(hm_db_entry)
        return data_models.HealthMonitor.from_sqlalchemy_model(hm_db_entry)

    def update_healthmonitor(self, context, id, healthmonitor):
        with context.session.begin(subtransactions=True):
            hm_db = self._get_resource(context, models.HealthMonitorV2, id)
            hm_db.update(healthmonitor)
        context.session.refresh(hm_db)
        return data_models.HealthMonitor.from_sqlalchemy_model(hm_db)

    def delete_healthmonitor(self, context, id):
        with context.session.begin(subtransactions=True):
            hm_db_entry = self._get_resource(context,
                                             models.HealthMonitorV2, id)
            context.session.delete(hm_db_entry)

    def get_healthmonitor(self, context, id):
        hm_db = self._get_resource(context, models.HealthMonitorV2, id)
        return data_models.HealthMonitor.from_sqlalchemy_model(hm_db)

    def get_healthmonitors(self, context, filters=None):
        hm_dbs = self._get_resources(context, models.HealthMonitorV2,
                                     filters=filters)
        return [data_models.HealthMonitor.from_sqlalchemy_model(hm_db)
                for hm_db in hm_dbs]

    def update_loadbalancer_stats(self, context, loadbalancer_id, stats_data):
        stats_data = stats_data or {}
        with context.session.begin(subtransactions=True):
            lb_db = self._get_resource(context, models.LoadBalancer,
                                       loadbalancer_id)
            self.assert_modification_allowed(lb_db)
            lb_db.stats = self._create_loadbalancer_stats(context,
                                                          loadbalancer_id,
                                                          data=stats_data)

    def stats(self, context, loadbalancer_id):
        loadbalancer = self._get_resource(context, models.LoadBalancer,
                                          loadbalancer_id)
        return data_models.LoadBalancerStatistics.from_sqlalchemy_model(
            loadbalancer.stats)
