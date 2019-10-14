# Copyright (c) 2019 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.tests import base


LB_ID = '099f29cd-4727-46a4-ae34-d9e05f3677dc'


class LbaasLoadBalancerModelTests(base.NeutronDbPluginV2TestCase):
    def test_loadbalancerstatistics_good(self):
        stats_db = models.LoadBalancerStatistics(
            loadbalancer_id=LB_ID,
            bytes_in='0',
            bytes_out='1',
            active_connections='2',
            total_connections='3'
        )
        self.assertEqual(LB_ID, stats_db.loadbalancer_id)
        self.assertEqual('0', stats_db.bytes_in)
        self.assertEqual('1', stats_db.bytes_out)
        self.assertEqual('2', stats_db.active_connections)
        self.assertEqual('3', stats_db.total_connections)

    def test_loadbalancerstatistics_bad(self):
        params = {
            'loadbalancer_id': LB_ID,
            'bytes_in': '-1',
            'bytes_out': '0',
            'active_connections': '0',
            'total_connections': '0'
        }
        self.assertRaises(ValueError,
            models.LoadBalancerStatistics,
            **params)
