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

"""lbaasv2 TLS

Revision ID: lbaasv2_tls
Revises: 364f9b6064f0
Create Date: 2015-01-18 10:00:00

"""

from alembic import op
import sqlalchemy as sa

from neutron.db import migration

# revision identifiers, used by Alembic.
revision = 'lbaasv2_tls'
down_revision = '364f9b6064f0'


old_listener_protocols = sa.Enum("HTTP", "HTTPS", "TCP",
                             name="listener_protocolsv2")
new_listener_protocols = sa.Enum("HTTP", "HTTPS", "TCP", "TERMINATED_HTTPS",
                             name="listener_protocolsv2")


def upgrade():
    migration.alter_enum('lbaas_listeners', 'protocol', new_listener_protocols,
                         nullable=False)
    op.create_table(
        u'lbaas_sni',
        sa.Column(u'listener_id', sa.String(36), nullable=False),
        sa.Column(u'tls_container_id', sa.String(128), nullable=False),
        sa.Column(u'position', sa.Integer),
        sa.ForeignKeyConstraint(['listener_id'], [u'lbaas_listeners.id'], ),
        sa.PrimaryKeyConstraint(u'listener_id', u'tls_container_id')
    )

    op.add_column('lbaas_listeners',
                  sa.Column(u'default_tls_container_id', sa.String(128),
                            nullable=True))
