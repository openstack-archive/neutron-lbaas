# Copyright 2014 OpenStack Foundation.
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

from neutron.api import extensions

from neutron_lbaas.extensions import loadbalancerv2


class Cascade_delete(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "LoadBalancing Cascade Delete"

    @classmethod
    def get_alias(cls):
        return "n-lbaasv2-cascade-delete"

    @classmethod
    def get_description(cls):
        return "Extension for LoadBalancing service v2 Cascade Delete"

    @classmethod
    def get_namespace(cls):
        return "http://wiki.openstack.org/neutron/LBaaS/API_2.0"

    @classmethod
    def get_updated(cls):
        return "2016-01-18T10:00:00-00:00"

    @classmethod
    def get_resources(cls):
        return []

    @classmethod
    def get_plugin_interface(cls):
        return loadbalancerv2.LoadBalancerPluginBaseV2

    def get_extended_resources(self, version):
        return {}
