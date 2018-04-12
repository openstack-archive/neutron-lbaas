# Copyright 2015 Rackspace.
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
"""agentv2

Revision ID: 364f9b6064f0
Revises: 4b6d8d5310b8
Create Date: 2015-02-05 10:17:13.229358

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '364f9b6064f0'
down_revision = '4b6d8d5310b8'


def upgrade():
    op.create_table(
        'lbaas_loadbalanceragentbindings',
        sa.Column('loadbalancer_id', sa.String(length=36), nullable=False),
        sa.Column('agent_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['loadbalancer_id'],
                                ['lbaas_loadbalancers.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('loadbalancer_id'))
