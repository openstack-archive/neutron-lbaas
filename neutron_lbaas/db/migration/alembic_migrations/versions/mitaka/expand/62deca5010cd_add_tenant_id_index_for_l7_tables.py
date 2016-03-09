# Copyright (c) 2016 Midokura SARL
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
#

"""Add tenant-id index for L7 tables

Revision ID: 62deca5010cd
Revises: 3543deab1547
Create Date: 2016-03-02 08:42:37.737281

"""

from alembic import op

from neutron.db import migration


# revision identifiers, used by Alembic.
revision = '62deca5010cd'
down_revision = '3543deab1547'

# milestone identifier, used by neutron-db-manage
neutron_milestone = [migration.MITAKA]


def upgrade():
    for table in ['lbaas_l7rules', 'lbaas_l7policies']:
        op.create_index(op.f('ix_%s_tenant_id' % table),
                        table, ['tenant_id'], unique=False)
