# Copyright 2015 VMware, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

from neutron.db import model_base
import sqlalchemy as sql


class NsxvEdgePoolMapping(model_base.BASEV2):
    """Represents the connection between Edges and pools."""
    __tablename__ = 'nsxv_edge_pool_mappings'

    pool_id = sql.Column(sql.String(36),
                         sql.ForeignKey('pools.id', ondelete='CASCADE'),
                         primary_key=True)
    edge_id = sql.Column(sql.String(36), nullable=False)
    edge_pool_id = sql.Column(sql.String(36), nullable=False)


class NsxvEdgeVipMapping(model_base.BASEV2):
    """Represents the connection between Edges and VIPs."""
    __tablename__ = 'nsxv_edge_vip_mappings'

    pool_id = sql.Column(sql.String(36),
                         sql.ForeignKey('pools.id', ondelete='CASCADE'),
                         primary_key=True)
    edge_id = sql.Column(sql.String(36), nullable=False)
    edge_app_profile_id = sql.Column(sql.String(36), nullable=False)
    edge_vse_id = sql.Column(sql.String(36), nullable=False)
    edge_fw_rule_id = sql.Column(sql.String(36), nullable=False)


class NsxvEdgeMonitorMapping(model_base.BASEV2):
    """Represents the connection between Edges and pool monitors."""
    __tablename__ = 'nsxv_edge_monitor_mappings'

    __table_args__ = (sql.schema.UniqueConstraint(
        'monitor_id', 'edge_id',
        name='uniq_nsxv_edge_monitor_mappings'),)

    monitor_id = sql.Column(sql.String(36),
                            sql.ForeignKey('healthmonitors.id',
                                           ondelete='CASCADE'),
                            primary_key=True)
    edge_id = sql.Column(sql.String(36), nullable=False, primary_key=True)
    edge_monitor_id = sql.Column(sql.String(36), nullable=False)
