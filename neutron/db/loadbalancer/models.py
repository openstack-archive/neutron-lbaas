# Copyright (c) 2014 OpenStack Foundation.
# All Rights Reserved.
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

import sqlalchemy as sa
from sqlalchemy import orm

from neutron.db import model_base
from neutron.db import models_v2
from neutron.db import servicetype_db as st_db
from neutron.services.loadbalancer import constants as lb_const


class SessionPersistenceV2(model_base.BASEV2):

    __tablename__ = "lbaas_sessionpersistences"

    pool_id = sa.Column(sa.String(36),
                        sa.ForeignKey("lbaas_pools.id"),
                        primary_key=True,
                        nullable=False)
    type = sa.Column(sa.Enum(*lb_const.SUPPORTED_SP_TYPES,
                             name="lbaas_sesssionpersistences_typev2"),
                     nullable=False)
    cookie_name = sa.Column(sa.String(1024), nullable=True)


class LoadBalancerStatistics(model_base.BASEV2):
    """Represents load balancer statistics."""

    NAME = 'loadbalancer_stats'

    __tablename__ = "lbaas_loadbalancer_statistics"

    loadbalancer_id = sa.Column(sa.String(36),
                                sa.ForeignKey("lbaas_loadbalancers.id"),
                                primary_key=True,
                                nullable=False)
    bytes_in = sa.Column(sa.BigInteger, nullable=False)
    bytes_out = sa.Column(sa.BigInteger, nullable=False)
    active_connections = sa.Column(sa.BigInteger, nullable=False)
    total_connections = sa.Column(sa.BigInteger, nullable=False)

    @orm.validates('bytes_in', 'bytes_out',
                   'active_connections', 'total_connections')
    def validate_non_negative_int(self, key, value):
        if value < 0:
            data = {'key': key, 'value': value}
            raise ValueError(_('The %(key)s field can not have '
                               'negative value. '
                               'Current value is %(value)d.') % data)
        return value


class MemberV2(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron load balancer member."""

    NAME = 'member'

    __tablename__ = "lbaas_members"

    __table_args__ = (
        sa.schema.UniqueConstraint('pool_id', 'address', 'protocol_port',
                                   name='uniq_pool_address_port_v2'),
    )
    pool_id = sa.Column(sa.String(36), sa.ForeignKey("lbaas_pools.id"),
                        nullable=False)
    address = sa.Column(sa.String(64), nullable=False)
    protocol_port = sa.Column(sa.Integer, nullable=False)
    weight = sa.Column(sa.Integer, nullable=True)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    subnet_id = sa.Column(sa.String(36), nullable=True)
    status = sa.Column(sa.String(16), nullable=False)


class HealthMonitorV2(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron load balancer healthmonitor."""

    NAME = 'healthmonitor'

    __tablename__ = "lbaas_healthmonitors"

    type = sa.Column(sa.Enum(*lb_const.SUPPORTED_HEALTH_MONITOR_TYPES,
                             name="healthmonitors_typev2"),
                     nullable=False)
    delay = sa.Column(sa.Integer, nullable=False)
    timeout = sa.Column(sa.Integer, nullable=False)
    max_retries = sa.Column(sa.Integer, nullable=False)
    http_method = sa.Column(sa.String(16), nullable=True)
    url_path = sa.Column(sa.String(255), nullable=True)
    expected_codes = sa.Column(sa.String(64), nullable=True)
    status = sa.Column(sa.String(16), nullable=False)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)


class PoolV2(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron load balancer pool."""

    NAME = 'pool'

    __tablename__ = "lbaas_pools"

    name = sa.Column(sa.String(255), nullable=True)
    description = sa.Column(sa.String(255), nullable=True)
    healthmonitor_id = sa.Column(sa.String(36),
                                 sa.ForeignKey("lbaas_healthmonitors.id"),
                                 unique=True,
                                 nullable=True)
    protocol = sa.Column(sa.Enum(*lb_const.SUPPORTED_PROTOCOLS,
                                 name="pool_protocolsv2"),
                         nullable=False)
    lb_algorithm = sa.Column(sa.Enum(*lb_const.SUPPORTED_LB_ALGORITHMS,
                                     name="lb_algorithmsv2"),
                             nullable=False)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    status = sa.Column(sa.String(16), nullable=False)
    members = orm.relationship(MemberV2,
                               backref=orm.backref("pool", uselist=False),
                               cascade="all, delete-orphan",
                               lazy='joined')
    healthmonitor = orm.relationship(
        HealthMonitorV2,
        backref=orm.backref("pool", uselist=False),
        lazy='joined')
    sessionpersistence = orm.relationship(
        SessionPersistenceV2,
        uselist=False,
        backref=orm.backref("pool", uselist=False),
        cascade="all, delete-orphan",
        lazy='joined')


class LoadBalancer(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron load balancer."""

    NAME = 'loadbalancer'

    __tablename__ = "lbaas_loadbalancers"

    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(255))
    vip_subnet_id = sa.Column(sa.String(36), nullable=False)
    vip_port_id = sa.Column(sa.String(36), sa.ForeignKey(
        'ports.id', name='fk_lbaas_loadbalancers_ports_id'))
    vip_address = sa.Column(sa.String(36))
    status = sa.Column(sa.String(16), nullable=False)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    vip_port = orm.relationship(models_v2.Port)
    stats = orm.relationship(
        LoadBalancerStatistics,
        uselist=False,
        backref=orm.backref("loadbalancer", uselist=False),
        cascade="all, delete-orphan",
        lazy='joined')
    provider = orm.relationship(
        st_db.ProviderResourceAssociation,
        uselist=False,
        lazy="joined",
        primaryjoin="LoadBalancer.id==ProviderResourceAssociation.resource_id",
        foreign_keys=[st_db.ProviderResourceAssociation.resource_id],
        # this is only for old API backwards compatibility because when a load
        # balancer is deleted the pool ID should be the same as the load
        # balancer ID and should not be cleared out in this table
        viewonly=True
    )


class Listener(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a v2 neutron listener."""

    NAME = 'listener'

    __tablename__ = "lbaas_listeners"

    __table_args__ = (
        sa.schema.UniqueConstraint('loadbalancer_id', 'protocol_port',
                                   name='uniq_loadbalancer_listener_port'),
    )

    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(255))
    default_pool_id = sa.Column(sa.String(36), sa.ForeignKey("lbaas_pools.id"),
                                unique=True)
    loadbalancer_id = sa.Column(sa.String(36), sa.ForeignKey(
        "lbaas_loadbalancers.id"))
    protocol = sa.Column(sa.Enum(*lb_const.SUPPORTED_PROTOCOLS,
                                 name="listener_protocolsv2"),
                         nullable=False)
    protocol_port = sa.Column(sa.Integer, nullable=False)
    connection_limit = sa.Column(sa.Integer)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    status = sa.Column(sa.String(16), nullable=False)
    default_pool = orm.relationship(
        PoolV2, backref=orm.backref("listener", uselist=False), lazy='joined')
    loadbalancer = orm.relationship(
        LoadBalancer, backref=orm.backref("listeners"), lazy='joined')
