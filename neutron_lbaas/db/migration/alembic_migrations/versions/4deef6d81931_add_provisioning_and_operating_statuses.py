# Copyright 2014-2015 Rackspace
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

"""add provisioning and operating statuses

Revision ID: 4deef6d81931
Revises: lbaasv2
Create Date: 2015-01-27 20:38:20.796401

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4deef6d81931'
down_revision = 'lbaasv2'

PROVISIONING_STATUS = u'provisioning_status'
OPERATING_STATUS = u'operating_status'
STATUS = u'status'


def upgrade():
    op.drop_column(u'lbaas_loadbalancers', STATUS)
    op.add_column(
        u'lbaas_loadbalancers',
        sa.Column(PROVISIONING_STATUS, sa.String(16), nullable=False)
    )
    op.add_column(
        u'lbaas_loadbalancers',
        sa.Column(OPERATING_STATUS, sa.String(16), nullable=False)
    )
    op.drop_column(u'lbaas_listeners', STATUS)
    op.add_column(
        u'lbaas_listeners',
        sa.Column(PROVISIONING_STATUS, sa.String(16), nullable=False)
    )
    op.add_column(
        u'lbaas_listeners',
        sa.Column(OPERATING_STATUS, sa.String(16), nullable=False)
    )
    op.drop_column(u'lbaas_pools', STATUS)
    op.add_column(
        u'lbaas_pools',
        sa.Column(PROVISIONING_STATUS, sa.String(16), nullable=False)
    )
    op.add_column(
        u'lbaas_pools',
        sa.Column(OPERATING_STATUS, sa.String(16), nullable=False)
    )
    op.drop_column(u'lbaas_members', STATUS)
    op.add_column(
        u'lbaas_members',
        sa.Column(PROVISIONING_STATUS, sa.String(16), nullable=False)
    )
    op.add_column(
        u'lbaas_members',
        sa.Column(OPERATING_STATUS, sa.String(16), nullable=False)
    )
    op.drop_column(u'lbaas_healthmonitors', STATUS)
    op.add_column(
        u'lbaas_healthmonitors',
        sa.Column(PROVISIONING_STATUS, sa.String(16), nullable=False)
    )
