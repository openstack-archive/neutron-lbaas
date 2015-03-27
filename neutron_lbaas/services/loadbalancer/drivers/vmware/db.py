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

from neutron_lbaas.services.loadbalancer.drivers.vmware import models


def add_nsxv_edge_pool_mapping(context, pool_id, edge_id, edge_pool_id):
    session = context.session
    with session.begin(subtransactions=True):
        mapping = models.NsxvEdgePoolMapping()
        mapping.pool_id = pool_id
        mapping.edge_id = edge_id
        mapping.edge_pool_id = edge_pool_id
        session.add(mapping)


def get_nsxv_edge_pool_mapping(context, pool_id):
    return(context.session.query(models.NsxvEdgePoolMapping).
           filter_by(pool_id=pool_id).first())


def get_nsxv_edge_pool_mapping_by_edge(context, edge_id):
    return(context.session.query(models.NsxvEdgePoolMapping).
           filter_by(edge_id=edge_id).all())


def delete_nsxv_edge_pool_mapping(context, pool_id):
    session = context.session
    mapping = (session.query(models.NsxvEdgePoolMapping).filter_by(
        pool_id=pool_id))
    for m in mapping:
        session.delete(m)


def add_nsxv_edge_vip_mapping(context, pool_id, edge_id, edge_app_profile_id,
                              edge_vse_id, edge_fw_rule_id):
    session = context.session
    with session.begin(subtransactions=True):
        mapping = models.NsxvEdgeVipMapping()
        mapping.pool_id = pool_id
        mapping.edge_id = edge_id
        mapping.edge_app_profile_id = edge_app_profile_id
        mapping.edge_vse_id = edge_vse_id
        mapping.edge_fw_rule_id = edge_fw_rule_id
        session.add(mapping)


def get_nsxv_edge_vip_mapping(context, pool_id):
    return(context.session.query(models.NsxvEdgeVipMapping).
           filter_by(pool_id=pool_id).first())


def delete_nsxv_edge_vip_mapping(context, pool_id):
    session = context.session
    mapping = (session.query(models.NsxvEdgeVipMapping).filter_by(
        pool_id=pool_id))
    for m in mapping:
        session.delete(m)


def add_nsxv_edge_monitor_mapping(context, monitor_id, edge_id,
                                  edge_monitor_id):
    session = context.session
    with session.begin(subtransactions=True):
        mapping = models.NsxvEdgeMonitorMapping()
        mapping.monitor_id = monitor_id
        mapping.edge_id = edge_id
        mapping.edge_monitor_id = edge_monitor_id
        session.add(mapping)


def get_nsxv_edge_monitor_mapping(context, monitor_id, edge_id):
    return(context.session.query(models.NsxvEdgeMonitorMapping).
           filter_by(monitor_id=monitor_id, edge_id=edge_id).first())


def get_nsxv_edge_monitor_mapping_all(context, monitor_id):
    return(context.session.query(models.NsxvEdgeMonitorMapping).
           filter_by(monitor_id=monitor_id).all())


def delete_nsxv_edge_monitor_mapping(context, monitor_id, edge_id):
    session = context.session
    mapping = (session.query(models.NsxvEdgeMonitorMapping).filter_by(
        monitor_id=monitor_id, edge_id=edge_id))
    for m in mapping:
        session.delete(m)
