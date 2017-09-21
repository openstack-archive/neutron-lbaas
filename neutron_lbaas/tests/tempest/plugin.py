# Copyright 2016
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

import os

from tempest.test_discover import plugins

import neutron_lbaas
from neutron_lbaas.tests.tempest import config as lbaas_config


class NeutronLbaasTempestPlugin(plugins.TempestPlugin):
    def load_tests(self):
        base_path = os.path.split(os.path.dirname(
            os.path.abspath(neutron_lbaas.__file__)))[0]
        test_dir = "neutron_lbaas/tests/tempest/v2"
        full_test_dir = os.path.join(base_path, test_dir)
        return full_test_dir, base_path

    def register_opts(self, conf):
        conf.register_group(lbaas_config.lbaas_group)
        conf.register_opts(lbaas_config.lbaas_opts,
                           group=lbaas_config.lbaas_group)

    def get_opt_lists(self):
        return [
            (lbaas_config.lbaas_group.name, lbaas_config.lbaas_opts),
        ]
