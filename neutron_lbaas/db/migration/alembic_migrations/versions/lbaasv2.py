# Copyright 2014 OpenStack Foundation
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
#

"""lbaas version 2 api

Revision ID: lbaasv2
Revises: start_neutron_lbaas
Create Date: 2014-06-18 10:50:15.606420

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'lbaasv2'
down_revision = 'start_neutron_lbaas'


listener_protocols = sa.Enum("HTTP", "HTTPS", "TCP",
                             name="listener_protocolsv2")
pool_protocols = sa.Enum("HTTP", "HTTPS", "TCP",
                         name="pool_protocolsv2")
sesssionpersistences_type = sa.Enum("SOURCE_IP", "HTTP_COOKIE", "APP_COOKIE",
                                    name="sesssionpersistences_typev2")
lb_algorithms = sa.Enum("ROUND_ROBIN", "LEAST_CONNECTIONS", "SOURCE_IP",
                        name="lb_algorithmsv2")
healthmonitors_type = sa.Enum("PING", "TCP", "HTTP", "HTTPS",
                              name="healthmonitors_typev2")


def upgrade():
    op.create_table(
        u'lbaas_healthmonitors',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'type', healthmonitors_type, nullable=False),
        sa.Column(u'delay', sa.Integer(), nullable=False),
        sa.Column(u'timeout', sa.Integer(), nullable=False),
        sa.Column(u'max_retries', sa.Integer(), nullable=False),
        sa.Column(u'http_method', sa.String(16), nullable=True),
        sa.Column(u'url_path', sa.String(255), nullable=True),
        sa.Column(u'expected_codes', sa.String(64), nullable=True),
        sa.Column(u'status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(u'id')
    )

    op.create_table(
        u'lbaas_pools',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'description', sa.String(255), nullable=True),
        sa.Column(u'protocol', pool_protocols, nullable=False),
        sa.Column(u'lb_algorithm', lb_algorithms, nullable=False),
        sa.Column(u'healthmonitor_id', sa.String(36), nullable=True),
        sa.Column(u'status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(u'id'),
        sa.UniqueConstraint(u'healthmonitor_id'),
        sa.ForeignKeyConstraint([u'healthmonitor_id'],
                                [u'lbaas_healthmonitors.id'])
    )

    op.create_table(
        u'lbaas_sessionpersistences',
        sa.Column(u'pool_id', sa.String(36), nullable=False),
        sa.Column(u'type', sesssionpersistences_type, nullable=False),
        sa.Column(u'cookie_name', sa.String(1024), nullable=True),
        sa.ForeignKeyConstraint([u'pool_id'], [u'lbaas_pools.id']),
        sa.PrimaryKeyConstraint(u'pool_id')
    )

    op.create_table(
        u'lbaas_members',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'pool_id', sa.String(36), nullable=False),
        sa.Column(u'subnet_id', sa.String(36), nullable=True),
        sa.Column(u'address', sa.String(64), nullable=False),
        sa.Column(u'protocol_port', sa.Integer(), nullable=False),
        sa.Column(u'weight', sa.Integer(), nullable=True),
        sa.Column(u'status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(u'id'),
        sa.ForeignKeyConstraint([u'pool_id'], [u'lbaas_pools.id']),
        sa.UniqueConstraint(u'pool_id', u'address', u'protocol_port',
                            name=u'uniq_pool_address_port_v2')
    )

    op.create_table(
        u'lbaas_loadbalancers',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'description', sa.String(255), nullable=True),
        sa.Column(u'vip_port_id', sa.String(36), nullable=True),
        sa.Column(u'vip_subnet_id', sa.String(36), nullable=False),
        sa.Column(u'vip_address', sa.String(36), nullable=True),
        sa.Column(u'status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint([u'vip_port_id'], [u'ports.id'],
                                name=u'fk_lbaas_loadbalancers_ports_id'),
        sa.PrimaryKeyConstraint(u'id')
    )

    op.create_table(
        u'lbaas_listeners',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'description', sa.String(255), nullable=True),
        sa.Column(u'protocol', listener_protocols, nullable=False),
        sa.Column(u'protocol_port', sa.Integer(), nullable=False),
        sa.Column(u'connection_limit', sa.Integer(), nullable=True),
        sa.Column(u'loadbalancer_id', sa.String(36), nullable=True),
        sa.Column(u'default_pool_id', sa.String(36), nullable=True),
        sa.Column(u'status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint([u'loadbalancer_id'],
                                [u'lbaas_loadbalancers.id']),
        sa.ForeignKeyConstraint([u'default_pool_id'],
                                [u'lbaas_pools.id']),
        sa.UniqueConstraint(u'default_pool_id'),
        sa.UniqueConstraint(u'loadbalancer_id', u'protocol_port',
                            name=u'uniq_loadbalancer_listener_port'),
        sa.PrimaryKeyConstraint(u'id')
    )

    op.create_table(
        u'lbaas_loadbalancer_statistics',
        sa.Column(u'loadbalancer_id', sa.String(36), nullable=False),
        sa.Column(u'bytes_in', sa.BigInteger(), nullable=False),
        sa.Column(u'bytes_out', sa.BigInteger(), nullable=False),
        sa.Column(u'active_connections', sa.BigInteger(), nullable=False),
        sa.Column(u'total_connections', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(u'loadbalancer_id'),
        sa.ForeignKeyConstraint([u'loadbalancer_id'],
                                [u'lbaas_loadbalancers.id'])
    )
