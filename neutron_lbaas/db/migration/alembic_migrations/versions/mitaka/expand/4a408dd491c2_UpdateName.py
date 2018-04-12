# Copyright 2015 NEC Corporation
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

"""Addition of Name column to lbaas_members and lbaas_healthmonitors table

Revision ID: 4a408dd491c2
Revises: 3345facd0452
Create Date: 2015-11-16 11:47:43.061649

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4a408dd491c2'
down_revision = '3345facd0452'

LB_TAB_NAME = ['lbaas_members', 'lbaas_healthmonitors']


def upgrade():
    for table in LB_TAB_NAME:
        op.add_column(table, sa.Column('name', sa.String(255), nullable=True))
