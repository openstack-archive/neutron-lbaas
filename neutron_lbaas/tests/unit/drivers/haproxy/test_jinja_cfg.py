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

import mock

from neutron.tests import base

from neutron_lbaas.common.cert_manager import cert_manager
from neutron_lbaas.common.tls_utils import cert_parser
from neutron_lbaas.drivers.haproxy import jinja_cfg
from neutron_lbaas.services.loadbalancer import constants
from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests.unit.drivers.haproxy.\
    sample_configs import sample_configs


class TestHaproxyCfg(base.BaseTestCase):
    def test_save_config(self):
        with mock.patch('neutron_lbaas.drivers.haproxy.'
                        'jinja_cfg.render_loadbalancer_obj') as r_t, \
                mock.patch('neutron_lib.utils.file.replace_file') as replace:
            r_t.return_value = 'fake_rendered_template'
            lb = mock.Mock()
            jinja_cfg.save_config('test_conf_path', lb, 'test_sock_path',
                                  'nogroup',
                                  'fake_state_path')
            r_t.assert_called_once_with(lb,
                                        'nogroup',
                                        'test_sock_path',
                                        'fake_state_path')
            replace.assert_called_once_with('test_conf_path',
                                            'fake_rendered_template')

    def test_get_template(self):
        template = jinja_cfg._get_template()
        self.assertEqual('haproxy.loadbalancer.j2', template.name)

    def test_render_template_tls_termination(self):
        lb = sample_configs.sample_loadbalancer_tuple(
            proto=constants.PROTOCOL_TERMINATED_HTTPS, tls=True, sni=True)

        fe = ("frontend sample_listener_id_1\n"
              "    option httplog\n"
              "    redirect scheme https if !{ ssl_fc }\n"
              "    maxconn 98\n"
              "    option forwardfor\n"
              "    bind 10.0.0.2:443"
              " ssl crt /v2/sample_listener_id_1/fakeCNM.pem"
              " crt /v2/sample_listener_id_1\n"
              "    mode http\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31s\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus %s\n"
              "    server sample_member_id_1 10.0.0.99:82"
              " weight 13 check inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82"
              " weight 13 check inter 30s fall 3 cookie "
              "sample_member_id_2\n\n"
              % sample_configs.PIPED_CODES)
        with mock.patch('os.makedirs'):
            with mock.patch('os.listdir'):
                with mock.patch.object(jinja_cfg, 'file_utils'):
                    with mock.patch.object(
                            jinja_cfg, '_process_tls_certificates') as crt:
                        crt.return_value = {
                            'tls_cert': lb.listeners[0]
                            .default_tls_container,
                            'sni_certs': [lb.listeners[0]
                                          .sni_containers[0].tls_container]}
                        rendered_obj = jinja_cfg.render_loadbalancer_obj(
                            lb, 'nogroup',
                            '/sock_path',
                            '/v2')
                        self.assertEqual(
                            sample_configs.sample_base_expected_config(
                                frontend=fe, backend=be),
                            rendered_obj)

    def test_render_template_tls_termination_no_sni(self):
        lb = sample_configs.sample_loadbalancer_tuple(
            proto=constants.PROTOCOL_TERMINATED_HTTPS, tls=True)

        fe = ("frontend sample_listener_id_1\n"
              "    option httplog\n"
              "    redirect scheme https if !{ ssl_fc }\n"
              "    maxconn 98\n"
              "    option forwardfor\n"
              "    bind 10.0.0.2:443"
              " ssl crt /v2/sample_listener_id_1/fakeCNM.pem\n"
              "    mode http\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31s\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus %s\n"
              "    server sample_member_id_1 10.0.0.99:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_2\n\n"
              % sample_configs.PIPED_CODES)
        with mock.patch('os.makedirs'):
            with mock.patch('neutron_lib.utils.file.replace_file'):
                with mock.patch('os.listdir'):
                    with mock.patch.object(jinja_cfg, 'file_utils'):
                        with mock.patch.object(
                                jinja_cfg, '_process_tls_certificates') as crt:
                            crt.return_value = {
                                'tls_cert': lb.listeners[0]
                                .default_tls_container,
                                'sni_certs': []}
                            rendered_obj = jinja_cfg.render_loadbalancer_obj(
                                lb, 'nogroup',
                                '/sock_path',
                                '/v2')
                            self.assertEqual(
                                sample_configs.sample_base_expected_config(
                                    frontend=fe, backend=be),
                                rendered_obj)

    def test_render_template_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31s\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus %s\n"
              "    server sample_member_id_1 10.0.0.99:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_2\n\n"
              % sample_configs.PIPED_CODES)
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(
            sample_configs.sample_base_expected_config(backend=be),
            rendered_obj)

    def test_render_template_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:443\n"
              "    mode tcp\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode tcp\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    timeout check 31s\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus %s\n"
              "    option ssl-hello-chk\n"
              "    server sample_member_id_1 10.0.0.99:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 "
              "weight 13 check inter 30s fall 3 cookie sample_member_id_2\n\n"
              % sample_configs.PIPED_CODES)
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(proto='HTTPS'),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_monitor_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    cookie SRV insert indirect nocache\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13 "
              "cookie sample_member_id_1\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13 "
              "cookie sample_member_id_2\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                proto=constants.PROTOCOL_HTTP, monitor=False),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(sample_configs.sample_base_expected_config(
            backend=be), rendered_obj)

    def test_render_template_no_monitor_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:443\n"
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
            sample_configs.sample_loadbalancer_tuple(
                proto='HTTPS', monitor=False),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_persistence_https(self):
        fe = ("frontend sample_listener_id_1\n"
              "    option tcplog\n"
              "    maxconn 98\n"
              "    bind 10.0.0.2:443\n"
              "    mode tcp\n"
              "    default_backend sample_pool_id_1\n\n")
        be = ("backend sample_pool_id_1\n"
              "    mode tcp\n"
              "    balance roundrobin\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                proto='HTTPS', monitor=False, persistence=False),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(sample_configs.sample_base_expected_config(
            frontend=fe, backend=be), rendered_obj)

    def test_render_template_no_persistence_http(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    server sample_member_id_1 10.0.0.99:82 weight 13\n"
              "    server sample_member_id_2 10.0.0.98:82 weight 13\n\n")
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                proto=constants.PROTOCOL_HTTP, monitor=False,
                persistence=False),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(sample_configs.sample_base_expected_config(
            backend=be), rendered_obj)

    def test_render_template_sourceip_persistence(self):
        be = ("backend sample_pool_id_1\n"
              "    mode http\n"
              "    balance roundrobin\n"
              "    stick-table type ip size 10k\n"
              "    stick on src\n"
              "    timeout check 31s\n"
              "    option httpchk GET /index.html\n"
              "    http-check expect rstatus %s\n"
              "    server sample_member_id_1 10.0.0.99:82 "
              "weight 13 check inter 30s fall 3\n"
              "    server sample_member_id_2 10.0.0.98:82 "
              "weight 13 check inter 30s fall 3\n\n"
              % sample_configs.PIPED_CODES)
        rendered_obj = jinja_cfg.render_loadbalancer_obj(
            sample_configs.sample_loadbalancer_tuple(
                persistence_type='SOURCE_IP'),
            'nogroup', '/sock_path', '/v2')
        self.assertEqual(
            sample_configs.sample_base_expected_config(backend=be),
            rendered_obj)

    def test_render_template_appsession_persistence(self):
        with mock.patch('os.makedirs') as md:
            with mock.patch.object(jinja_cfg, 'file_utils'):
                md.return_value = '/data/dirs/'
                be = ("backend sample_pool_id_1\n"
                      "    mode http\n"
                      "    balance roundrobin\n"
                      "    stick-table type string len 64 size 10k\n"
                      "    stick store-response res.cook(APP_COOKIE)\n"
                      "    stick match req.cook(APP_COOKIE)\n"
                      "    timeout check 31s\n"
                      "    option httpchk GET /index.html\n"
                      "    http-check expect rstatus %s\n"
                      "    server sample_member_id_1 10.0.0.99:82 "
                      "weight 13 check inter 30s fall 3\n"
                      "    server sample_member_id_2 10.0.0.98:82 "
                      "weight 13 check inter 30s fall 3\n\n"
                      % sample_configs.PIPED_CODES)
                rendered_obj = jinja_cfg.render_loadbalancer_obj(
                    sample_configs.sample_loadbalancer_tuple(
                        persistence_type='APP_COOKIE'),
                    'nogroup', '/sock_path',
                    '/v2')
                self.assertEqual(
                    sample_configs.sample_base_expected_config(backend=be),
                    rendered_obj)

    def test_retrieve_crt_path(self):
        with mock.patch('os.makedirs'):
            with mock.patch('os.path.isdir') as isdir:
                with mock.patch.object(jinja_cfg, '_retrieve_crt_path') as rcp:
                    isdir.return_value = True
                    rcp.return_value = '/v2/loadbalancers/lb_id_1/' \
                                       'cont_id_1.pem'
                    ret = jinja_cfg._retrieve_crt_path(
                        '/v2/loadbalancers', 'lb_id_1', 'cont_id_1')
                    self.assertEqual(
                        '/v2/loadbalancers/lb_id_1/cont_id_1.pem', ret)

    def test_store_listener_crt(self):
        l = sample_configs.sample_listener_tuple(tls=True, sni=True)
        with mock.patch('os.makedirs'):
            with mock.patch('neutron_lib.utils.file.replace_file'):
                    ret = jinja_cfg._store_listener_crt(
                        '/v2/loadbalancers', l, l.default_tls_container)
                    self.assertEqual(
                        '/v2/loadbalancers/sample_listener_id_1/fakeCNM.pem',
                        ret)

    def test_process_tls_certificates(self):
        sl = sample_configs.sample_listener_tuple(tls=True, sni=True)
        tls = data_models.TLSContainer(primary_cn='fakeCN',
                                       certificate='imaCert',
                                       private_key='imaPrivateKey',
                                       intermediates=['imainter1',
                                                      'imainter2'])
        cert = mock.Mock(spec=cert_manager.Cert)
        cert.get_private_key.return_value = tls.private_key
        cert.get_certificate.return_value = tls.certificate
        cert.get_intermediates.return_value = tls.intermediates

        with mock.patch.object(jinja_cfg, '_map_cert_tls_container') as map, \
                mock.patch.object(jinja_cfg,
                                  '_store_listener_crt') as store_cert, \
                mock.patch.object(cert_parser,
                                  'get_host_names') as get_host_names, \
                mock.patch.object(jinja_cfg,
                                  'CERT_MANAGER_PLUGIN') as cert_mgr:
            map.return_value = tls
            cert_mgr_mock = mock.Mock(spec=cert_manager.CertManager)
            cert_mgr_mock.get_cert.return_value = cert
            cert_mgr.CertManager.return_value = cert_mgr_mock
            get_host_names.return_value = {'cn': 'fakeCN'}
            jinja_cfg._process_tls_certificates(sl)

            # Ensure get_cert is called three times
            calls_certs = [
                mock.call(sl.default_tls_container.id),
                mock.call('cont_id_2'),
                mock.call('cont_id_3')]
            cert_mgr_mock.get_cert.call_args_list == calls_certs

            # Ensure store_cert is called three times
            calls_ac = [mock.call('/v2/',
                                  'sample_listener_id_1',
                                  tls),
                        mock.call('/v2/',
                                  'sample_listener_id_1',
                                  tls),
                        mock.call('/v2/',
                                  'sample_listener_id_1',
                                  tls)]
            store_cert.call_args_list == calls_ac

    def test_get_primary_cn(self):
        cert = mock.MagicMock()

        with mock.patch.object(cert_parser, 'get_host_names') as cp:
            cp.return_value = {'cn': 'fakeCN'}
            cn = jinja_cfg._get_primary_cn(cert.get_certificate())
            self.assertEqual('fakeCN', cn)

    def test_map_cert_tls_container(self):
        tls = data_models.TLSContainer(primary_cn='fakeCN',
                                       certificate='imaCert',
                                       private_key='imaPrivateKey',
                                       intermediates=['imainter1',
                                                      'imainter2'])
        cert = mock.MagicMock()
        cert.get_private_key.return_value = tls.private_key
        cert.get_certificate.return_value = tls.certificate
        cert.get_intermediates.return_value = tls.intermediates
        cert.get_private_key_passphrase.return_value = 'passphrase'
        with mock.patch.object(cert_parser, 'get_host_names') as cp:
            with mock.patch.object(cert_parser, 'dump_private_key') as dp:
                cp.return_value = {'cn': 'fakeCN'}
                dp.return_value = 'imaPrivateKey'
                self.assertEqual(tls.primary_cn,
                                 jinja_cfg._map_cert_tls_container(
                                     cert).primary_cn)
                self.assertEqual(tls.certificate,
                                 jinja_cfg._map_cert_tls_container(
                                     cert).certificate)
                self.assertEqual(tls.private_key,
                                 jinja_cfg._map_cert_tls_container(
                                     cert).private_key)
                self.assertEqual(tls.intermediates,
                                 jinja_cfg._map_cert_tls_container(
                                     cert).intermediates)

    def test_build_pem(self):
        expected = 'imainter\nimainter2\nimacert\nimakey'
        tls_tupe = sample_configs.sample_tls_container_tuple(
            certificate='imacert', private_key='imakey',
            intermediates=['imainter', 'imainter2'])
        self.assertEqual(expected, jinja_cfg._build_pem(tls_tupe))

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

    def test_transform_pool_admin_state_down(self):
        in_pool = sample_configs.sample_pool_tuple(hm_admin_state=False)
        ret = jinja_cfg._transform_pool(in_pool)
        result = sample_configs.RET_POOL
        result['health_monitor'] = ''
        self.assertEqual(result, ret)

    def test_transform_listener(self):
        in_listener = sample_configs.sample_listener_tuple()
        ret = jinja_cfg._transform_listener(in_listener, '/v2')
        self.assertEqual(sample_configs.RET_LISTENER, ret)

    def test_transform_loadbalancer(self):
        in_lb = sample_configs.sample_loadbalancer_tuple()
        ret = jinja_cfg._transform_loadbalancer(in_lb, '/v2')
        self.assertEqual(sample_configs.RET_LB, ret)

    def test_compute_global_connection_limit(self):
        lts = [
                sample_configs.sample_listener_tuple(connection_limit=None),
                sample_configs.sample_listener_tuple()]
        in_listeners = [jinja_cfg._transform_listener(x, '/v2') for x in lts]
        ret = jinja_cfg._compute_global_connection_limit(in_listeners)
        self.assertEqual(2098, ret)

    def test_include_member(self):
        ret = jinja_cfg._include_member(
            sample_configs.sample_member_tuple('sample_member_id_1',
                                               '10.0.0.99'))
        self.assertTrue(ret)

    def test_include_member_invalid_status(self):
        ret = jinja_cfg._include_member(
            sample_configs.sample_member_tuple('sample_member_id_1',
                                               '10.0.0.99', status='PENDING'))
        self.assertFalse(ret)

    def test_include_member_invalid_admin_state(self):
        ret = jinja_cfg._include_member(
            sample_configs.sample_member_tuple('sample_member_id_1',
                                               '10.0.0.99',
                                               admin_state_up=False))
        self.assertFalse(ret)

    def test_expand_expected_codes(self):
        exp_codes = ''
        self.assertEqual(set([]), jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200'
        self.assertEqual(set(['200']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200, 201'
        self.assertEqual(set(['200', '201']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200, 201,202'
        self.assertEqual(set(['200', '201', '202']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200-202'
        self.assertEqual(set(['200', '201', '202']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200-202, 205'
        self.assertEqual(set(['200', '201', '202', '205']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200, 201-203'
        self.assertEqual(set(['200', '201', '202', '203']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '200, 201-203, 205'
        self.assertEqual(set(['200', '201', '202', '203', '205']),
                         jinja_cfg._expand_expected_codes(exp_codes))
        exp_codes = '201-200, 205'
        self.assertEqual(set(['205']),
                         jinja_cfg._expand_expected_codes(exp_codes))

    def test_render_template_about_option_log(self):
        for proto in constants.LISTENER_SUPPORTED_PROTOCOLS:
            proto_mode = jinja_cfg.PROTOCOL_MAP[proto]
            _rendered_obj = jinja_cfg.render_loadbalancer_obj(
                sample_configs.sample_loadbalancer_tuple(
                    proto=proto, monitor=False),
                'nogroup', '/sock_path', '/v2')
            expected_be = \
                ("backend sample_pool_id_1\n"
                 "    mode %s\n"
                 "    balance roundrobin\n"
                 "    cookie SRV insert indirect nocache\n"
                 "    server sample_member_id_1 10.0.0.99:82 weight 13 "
                 "cookie sample_member_id_1\n"
                 "    server sample_member_id_2 10.0.0.98:82 weight 13 "
                 "cookie sample_member_id_2\n\n") % proto_mode
            self.assertEqual(sample_configs.sample_base_expected_config(
                backend=expected_be, fe_proto=proto), _rendered_obj)
