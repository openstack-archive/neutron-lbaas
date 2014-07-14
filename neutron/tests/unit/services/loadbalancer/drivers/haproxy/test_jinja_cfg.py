# Copyright 2014 OpenStack Foundation
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

import contextlib
import mock

from neutron.services.loadbalancer.drivers.haproxy import jinja_cfg
from neutron.tests import base
from neutron.tests.unit.services.loadbalancer.drivers.haproxy.sample_configs \
    import sample_configs


class TestHaproxyCfg(base.BaseTestCase):
    def test_save_config(self):
        with contextlib.nested(
            mock.patch('neutron.services.loadbalancer.'
                       'drivers.haproxy.jinja_cfg.render_loadbalancer_obj'),
            mock.patch('neutron.agent.linux.utils.replace_file')
        ) as (r_t, replace):
            r_t.return_value = 'fake_rendered_template'
            lb = mock.Mock()
            jinja_cfg.save_config('test_conf_path', lb, 'test_sock_path')
            r_t.assert_called_once_with(lb, 'nogroup', 'test_sock_path')
            replace.assert_called_once_with('test_conf_path',
                                            'fake_rendered_template')

    def test_get_template_v14(self):
        template = jinja_cfg._get_template()
        self.assertEqual('haproxy_v1.4.template', template.name)

    def test_render_template_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus 405|404|500\n"
              "    option forwardfor\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 check "
              "inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 check "
              "inter 30s fall 3 cookie sample_member_id_2\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(),
            'nogroup', '/sock_path')
        self.assertEqual(
            sample_configs.sample_base_expected_config(backend=be),
            rendered_obj)

    def test_render_template_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:80\n"
              "    mode tcp\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode tcp\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus 405|404|500\n"
              "    option ssl-hello-chk\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 check "
              "inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 check "
              "inter 30s fall 3 cookie sample_member_id_2\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTPS'),
            'nogroup', '/sock_path')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_monitor_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    option forwardfor\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 "
              "cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 "
              "cookie sample_member_id_2\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTP',
                                                     monitor=False),
            'nogroup', '/sock_path')
        self.assertEqual(sample_configs.sample_base_expected_config(
            backend=be), rendered_obj)

    def test_render_template_no_monitor_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:80\n"
              "    mode tcp\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode tcp\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 "
              "cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 "
              "cookie sample_member_id_2\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTPS',
                                                     monitor=False),
            'nogroup', '/sock_path')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_persistence_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:80\n"
              "    mode tcp\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode tcp\n"
              "    balance roundrobin\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTPS',
                                                     monitor=False,
                                                     persistence=False),
            'nogroup', '/sock_path')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_persistence_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    option forwardfor\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTP',
                                                     monitor=False,
                                                     persistence=False),
            'nogroup', '/sock_path')
        self.assertEqual(sample_configs.sample_base_expected_config(
            backend=be), rendered_obj)

    def test_render_template_sourceip_persistence(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    stick-table type ip size 10k\n"
              "    stick on src\n"
              "    timeout check 31\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus 405|404|500\n"
              "    option forwardfor\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 check "
              "inter 30s fall 3\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 check "
              "inter 30s fall 3\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                persistence_type='SOURCE_IP'),
            'nogroup', '/sock_path')
        self.assertEqual(
            sample_configs.sample_base_expected_config(backend=be),
            rendered_obj)

    def test_render_template_appsession_persistence(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    appsession APP_COOKIE len 56 timeout 3h\n"
              "    timeout check 31\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus 405|404|500\n"
              "    option forwardfor\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 check "
              "inter 30s fall 3\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 check "
              "inter 30s fall 3\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                persistence_type='APP_COOKIE'),
            'nogroup', '/sock_path')
        self.assertEqual(
            sample_configs.sample_base_expected_config(backend=be),
            rendered_obj)

    def test_transform_session_persistence(self):
        in_persistence = sample_configs.sample_session_persistence_tuple()
        ret = jinja_cfg._transform_session_persistence(in_persistence)
        self.assertEqual(sample_configs.RET_PERSISTENCE, ret)

    def test_transform_health_monitor(self):
        in_persistence = sample_configs.sample_health_monitor_tuple()
        ret = jinja_cfg._transform_health_monitor(in_persistence)
        self.assertEqual(sample_configs.RET_MONITOR, ret)

    def test_transform_member(self):
        in_member = sample_configs.sample_member_tuple('sample_member_id_1',
                                                       '10.0.0.99')
        ret = jinja_cfg._transform_member(in_member)
        self.assertEqual(sample_configs.RET_MEMBER_1, ret)

    def test_transform_pool(self):
        in_pool = sample_configs.sample_pool_tuple()
        ret = jinja_cfg._transform_pool(in_pool)
        self.assertEqual(sample_configs.RET_POOL, ret)

    def test_transform_listener(self):
        in_listener = sample_configs.sample_listener_tuple()
        ret = jinja_cfg._transform_listener(in_listener)
        self.assertEqual(sample_configs.RET_LISTENER, ret)

    def test_transform_loadbalancer(self):
        in_lb = sample_configs.sample_loadbalancer_tuple()
        ret = jinja_cfg._transform_loadbalancer(in_lb)
        self.assertEqual(sample_configs.RET_LB, ret)