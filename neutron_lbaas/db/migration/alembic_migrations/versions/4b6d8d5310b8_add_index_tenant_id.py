# Copyright 2015
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

"""add_index_tenant_id

Revision ID: 4b6d8d5310b8
Revises: 4deef6d81931
Create Date: 2015-02-10 18:28:26.362881

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '4b6d8d5310b8'
down_revision = '4deef6d81931'

TABLES = ['lbaas_members', 'lbaas_healthmonitors', 'lbaas_pools',
          'lbaas_loadbalancers', 'lbaas_listeners', 'vips', 'members',
          'pools', 'healthmonitors']


def upgrade():
    for table in TABLES:
        op.create_index(op.f('ix_%s_tenant_id' % table),
                        table, ['tenant_id'], unique=False)
