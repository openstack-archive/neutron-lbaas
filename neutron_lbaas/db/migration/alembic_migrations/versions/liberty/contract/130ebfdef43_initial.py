# Copyright 2015 OpenStack Foundation
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

"""Initial Liberty no-op contract revision.

Revision ID: 130ebfdef43
Revises: kilo
Create Date: 2015-07-18 14:35:22.242794

"""

from neutron.db import migration
from neutron.db.migration import cli


# revision identifiers, used by Alembic.
revision = '130ebfdef43'
down_revision = 'kilo'
branch_labels = (cli.CONTRACT_BRANCH,)

# milestone identifier, used by neutron-db-manage
neutron_milestone = [migration.LIBERTY, migration.MITAKA]


def upgrade():
    pass
