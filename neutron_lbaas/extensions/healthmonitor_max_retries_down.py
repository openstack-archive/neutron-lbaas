# Copyright 2016 Rackspace
# All Rights Reserved
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

from neutron_lib.api import converters
from neutron_lib.api import extensions

EXTENDED_ATTRIBUTES_2_0 = {
    'healthmonitors': {
        'max_retries_down': {
            'allow_post': True, 'allow_put': True,
            'default': 3, 'validate': {'type:range': [1, 10]},
            'convert_to': converters.convert_to_int, 'is_visible': True
        }
    }
}


class Healthmonitor_max_retries_down(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Add a fall threshold to health monitor"

    @classmethod
    def get_alias(cls):
        return "hm_max_retries_down"

    @classmethod
    def get_description(cls):
        return "Add a fall threshold to health monitor"

    @classmethod
    def get_updated(cls):
        return "2016-04-19T16:00:00-00:00"

    def get_required_extensions(self):
        return ["lbaasv2"]

    def get_extended_resources(self, version):
        if version == "2.0":
            return EXTENDED_ATTRIBUTES_2_0
        else:
            return {}
