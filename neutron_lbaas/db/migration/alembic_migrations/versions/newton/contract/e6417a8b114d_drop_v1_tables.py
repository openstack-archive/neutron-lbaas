# Copyright 2016 <PUT YOUR NAME/COMPANY HERE>
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

"""Drop v1 tables

Revision ID: e6417a8b114d
Create Date: 2016-08-23 12:48:46.985939

"""

from alembic import op

from neutron.db import migration


revision = 'e6417a8b114d'
down_revision = '4b4dc6d5d843'


# milestone identifier, used by neutron-db-manage
neutron_milestone = [migration.NEWTON]


def upgrade():
    op.drop_table('nsxv_edge_pool_mappings')
    op.drop_table('nsxv_edge_vip_mappings')
    op.drop_table('nsxv_edge_monitor_mappings')
    op.drop_table('members')
    op.drop_table('poolstatisticss')
    op.drop_table('poolloadbalanceragentbindings')
    op.drop_table('poolmonitorassociations')
    op.drop_table('pools')
    op.drop_table('sessionpersistences')
    op.drop_table('vips')
    op.drop_table('healthmonitors')
