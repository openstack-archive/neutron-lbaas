# Copyright 2015 OpenStack Foundation
# Copyright 2015 Blue Box, an IBM Company
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

"""independent pools

Revision ID: 6aee0434f911
Revises: 3426acbc12de
Create Date: 2015-08-28 03:15:42.533386

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6aee0434f911'
down_revision = '3426acbc12de'


def upgrade():
    conn = op.get_bind()
    # Minimal examples of the tables we need to manipulate
    listeners = sa.sql.table(
        'lbaas_listeners',
        sa.sql.column('loadbalancer_id', sa.String),
        sa.sql.column('default_pool_id', sa.String))
    pools = sa.sql.table(
        'lbaas_pools',
        sa.sql.column('loadbalancer_id', sa.String),
        sa.sql.column('id', sa.String))

    # This foreign key does not need to be unique anymore. To remove the
    # uniqueness but keep the foreign key we have to do some juggling.
    #
    # Also, because different database engines handle unique constraints
    # in incompatible ways, we can't simply call op.drop_constraint and
    # expect it to work for all DB engines. This is yet another unfortunate
    # case where sqlalchemy isn't able to abstract everything away.
    if op.get_context().dialect.name == 'postgresql':
        # PostgreSQL path:
        op.drop_constraint('lbaas_listeners_default_pool_id_key',
                           'lbaas_listeners', 'unique')
    else:
        # MySQL path:
        op.drop_constraint('lbaas_listeners_ibfk_2', 'lbaas_listeners',
                           type_='foreignkey')
        op.drop_constraint('default_pool_id', 'lbaas_listeners',
                           type_='unique')
        op.create_foreign_key('lbaas_listeners_ibfk_2', 'lbaas_listeners',
                              'lbaas_pools', ['default_pool_id'], ['id'])

    op.add_column(
        u'lbaas_pools',
        sa.Column('loadbalancer_id', sa.String(36),
            sa.ForeignKey('lbaas_loadbalancers.id'), nullable=True)
    )

    # Populate this new column appropriately
    select_obj = sa.select([listeners.c.loadbalancer_id,
                           listeners.c.default_pool_id]).where(
                           listeners.c.default_pool_id is not None)
    result = conn.execute(select_obj)
    for row in result:
        stmt = pools.update().values(loadbalancer_id=row[0]).where(
            pools.c.id == row[1])
        op.execute(stmt)

# For existing installations, the above ETL should populate the above column
# using the following procedure:
#
# Get the output from this:
#
# SELECT default_pool_id, loadbalancer_id l_id FROM lbaas_listeners WHERE
# default_pool_id IS NOT NULL;
#
# Then for every row returned run:
#
# UPDATE lbaas_pools SET loadbalancer_id = l_id WHERE id = default_pool_id;
