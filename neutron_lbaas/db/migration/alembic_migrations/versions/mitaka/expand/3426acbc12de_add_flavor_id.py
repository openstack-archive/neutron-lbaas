# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

"""Add flavor id

Revision ID: 3426acbc12de
Revises: 4a408dd491c2
Create Date: 2015-12-02 15:24:35.775474

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3426acbc12de'
down_revision = '4a408dd491c2'


def upgrade():
    op.add_column('lbaas_loadbalancers',
                  sa.Column(u'flavor_id', sa.String(36), nullable=True))
    op.create_foreign_key(u'fk_lbaas_loadbalancers_flavors_id',
                          u'lbaas_loadbalancers',
                          u'flavors',
                          [u'flavor_id'],
                          [u'id'])
