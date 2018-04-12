# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""edge_driver

Revision ID: 4ba00375f715
Revises: lbaasv2_tls
Create Date: 2015-02-03 20:35:54.830634

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4ba00375f715'
down_revision = 'lbaasv2_tls'


def upgrade():
    op.create_table(
        'nsxv_edge_pool_mappings',
        sa.Column('pool_id', sa.String(length=36), nullable=False),
        sa.Column('edge_id', sa.String(length=36), nullable=False),
        sa.Column('edge_pool_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['pool_id'], ['pools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('pool_id')
    )
    op.create_table(
        'nsxv_edge_vip_mappings',
        sa.Column('pool_id', sa.String(length=36), nullable=False),
        sa.Column('edge_id', sa.String(length=36), nullable=False),
        sa.Column('edge_app_profile_id', sa.String(length=36),
                  nullable=False),
        sa.Column('edge_vse_id', sa.String(length=36), nullable=False),
        sa.Column('edge_fw_rule_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['pool_id'], ['pools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('pool_id')
    )
    op.create_table(
        'nsxv_edge_monitor_mappings',
        sa.Column('monitor_id', sa.String(length=36), nullable=False),
        sa.Column('edge_id', sa.String(length=36), nullable=False),
        sa.Column('edge_monitor_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['monitor_id'], ['healthmonitors.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('monitor_id'),
        sa.UniqueConstraint('monitor_id', 'edge_id',
                            name='uniq_nsxv_edge_monitor_mappings')
    )
