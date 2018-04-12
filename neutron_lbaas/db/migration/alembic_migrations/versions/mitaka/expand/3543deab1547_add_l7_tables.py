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

"""add_l7_tables

Revision ID: 3543deab1547
Revises: 6aee0434f911
Create Date: 2015-02-05 10:50:15.606420

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3543deab1547'
down_revision = '6aee0434f911'

l7rule_type = sa.Enum("HOST_NAME", "PATH", "FILE_TYPE", "HEADER", "COOKIE",
                      name="l7rule_typesv2")
l7rule_compare_type = sa.Enum("REGEX", "STARTS_WITH", "ENDS_WITH", "CONTAINS",
                              "EQUAL_TO", name="l7rule_compare_typesv2")
l7policy_action_type = sa.Enum("REJECT", "REDIRECT_TO_URL", "REDIRECT_TO_POOL",
                               name="l7policy_action_typesv2")


def upgrade():
    op.create_table(
        u'lbaas_l7policies',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'description', sa.String(255), nullable=True),
        sa.Column(u'listener_id', sa.String(36), nullable=False),
        sa.Column(u'action', l7policy_action_type, nullable=False),
        sa.Column(u'redirect_pool_id', sa.String(36), nullable=True),
        sa.Column(u'redirect_url', sa.String(255), nullable=True),
        sa.Column(u'position', sa.Integer, nullable=False),
        sa.Column(u'provisioning_status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),

        sa.PrimaryKeyConstraint(u'id'),
        sa.ForeignKeyConstraint([u'listener_id'],
                                [u'lbaas_listeners.id']),
        sa.ForeignKeyConstraint([u'redirect_pool_id'],
                                [u'lbaas_pools.id'])
    )

    op.create_table(
        u'lbaas_l7rules',
        sa.Column(u'tenant_id', sa.String(255), nullable=True),
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'l7policy_id', sa.String(36), nullable=False),
        sa.Column(u'type', l7rule_type, nullable=False),
        sa.Column(u'compare_type', l7rule_compare_type, nullable=False),
        sa.Column(u'invert', sa.Boolean(), nullable=False),
        sa.Column(u'key', sa.String(255), nullable=True),
        sa.Column(u'value', sa.String(255), nullable=False),
        sa.Column(u'provisioning_status', sa.String(16), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(u'id'),
        sa.ForeignKeyConstraint([u'l7policy_id'],
                                [u'lbaas_l7policies.id'])
    )
