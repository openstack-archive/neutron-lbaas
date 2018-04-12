# Copyright 2015, Radware LTD. All rights reserved
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

import copy
import threading
import time

import netaddr
from neutron_lib import constants as n_constants
from neutron_lib import context
from neutron_lib.plugins import constants as pg_constants
from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_utils import excutils
from six.moves import queue as Queue

import neutron_lbaas.common.cert_manager
from neutron_lbaas.drivers.radware import base_v2_driver
from neutron_lbaas.drivers.radware import exceptions as r_exc
from neutron_lbaas.drivers.radware import rest_client as rest

CERT_MANAGER_PLUGIN = neutron_lbaas.common.cert_manager.get_backend()
TEMPLATE_HEADER = {'Content-Type':
                   'application/vnd.com.radware.vdirect.'
                   'template-parameters+json'}
PROVISION_HEADER = {'Content-Type':
                    'application/vnd.com.radware.'
                    'vdirect.status+json'}
CREATE_SERVICE_HEADER = {'Content-Type':
                         'application/vnd.com.radware.'
                         'vdirect.adc-service-specification+json'}

PROPERTY_DEFAULTS = {'type': 'none',
                     'cookie_name': 'none',
                     'url_path': '/',
                     'http_method': 'GET',
                     'expected_codes': '200',
                     'subnet': '255.255.255.255',
                     'mask': '255.255.255.255',
                     'gw': '255.255.255.255',
                     }
LOADBALANCER_PROPERTIES = ['vip_address', 'admin_state_up']
LISTENER_PROPERTIES = ['id', 'protocol_port', 'protocol',
                       'connection_limit', 'admin_state_up']
DEFAULT_CERT_PROPERTIES = ['id', 'certificate', 'intermediates',
                           'private_key', 'passphrase']
SNI_CERT_PROPERTIES = DEFAULT_CERT_PROPERTIES + ['position']
L7_RULE_PROPERTIES = ['id', 'type', 'compare_type',
                      'key', 'value', 'admin_state_up']
L7_POLICY_PROPERTIES = ['id', 'action', 'redirect_pool_id',
                        'redirect_url', 'position', 'admin_state_up']
DEFAULT_POOL_PROPERTIES = ['id']
POOL_PROPERTIES = ['id', 'protocol', 'lb_algorithm', 'admin_state_up']
MEMBER_PROPERTIES = ['id', 'address', 'protocol_port', 'weight',
                     'admin_state_up', 'subnet', 'mask', 'gw']
SESSION_PERSISTENCY_PROPERTIES = ['type', 'cookie_name']
HEALTH_MONITOR_PROPERTIES = ['type', 'delay', 'timeout', 'max_retries',
                             'admin_state_up', 'url_path', 'http_method',
                             'expected_codes', 'id']

LOG = logging.getLogger(__name__)


class RadwareLBaaSV2Driver(base_v2_driver.RadwareLBaaSBaseV2Driver):
    #
    # Assumptions:
    # 1) We have only one worflow that takes care of l2-l4 and service creation
    # 2) The workflow template exists on the vDirect server
    # 3) The workflow expose one operation named 'update' (plus ctor and dtor)
    # 4) The 'update' operation gets the loadbalancer object graph as input
    # 5) The object graph is enehanced by our code before it is sent to the
    #    workflow
    # 6) Async operations are handled by a different thread
    #
    def __init__(self, plugin):
        base_v2_driver.RadwareLBaaSBaseV2Driver.__init__(self, plugin)
        rad = cfg.CONF.radwarev2
        rad_debug = cfg.CONF.radwarev2_debug
        self.plugin = plugin
        self.service = {
            "name": "_REPLACE_",
            "tenantId": "_REPLACE_",
            "haPair": rad.service_ha_pair,
            "sessionMirroringEnabled": rad.service_session_mirroring_enabled,
            "primary": {
                "capacity": {
                    "throughput": rad.service_throughput,
                    "sslThroughput": rad.service_ssl_throughput,
                    "compressionThroughput":
                    rad.service_compression_throughput,
                    "cache": rad.service_cache
                },
                "network": {
                    "type": "portgroup",
                    "portgroups": '_REPLACE_'
                },
                "adcType": rad.service_adc_type,
                "acceptableAdc": "Exact"
            }
        }
        if rad.service_resource_pool_ids:
            ids = rad.service_resource_pool_ids
            self.service['resourcePoolIds'] = [
                {'id': id} for id in ids
            ]
        else:
            self.service['resourcePoolIds'] = []

        if rad.service_isl_vlan:
            self.service['islVlan'] = rad.service_isl_vlan
        self.workflow_template_name = rad.workflow_template_name
        self.child_workflow_template_names = rad.child_workflow_template_names
        self.workflow_params = rad.workflow_params
        self.workflow_action_name = rad.workflow_action_name
        self.stats_action_name = rad.stats_action_name
        vdirect_address = rad.vdirect_address
        sec_server = rad.ha_secondary_address
        self.rest_client = rest.vDirectRESTClient(
            server=vdirect_address,
            secondary_server=sec_server,
            user=rad.vdirect_user,
            password=rad.vdirect_password,
            port=rad.port,
            ssl=rad.ssl,
            ssl_verify_context=rad.ssl_verify_context,
            timeout=rad.timeout,
            base_uri=rad.base_uri)
        self.workflow_params['provision_service'] = rad_debug.provision_service
        self.workflow_params['configure_l3'] = rad_debug.configure_l3
        self.workflow_params['configure_l4'] = rad_debug.configure_l4
        self.configure_allowed_address_pairs =\
            rad.configure_allowed_address_pairs

        self.queue = Queue.Queue()
        self.completion_handler = OperationCompletionHandler(self.queue,
                                                             self.rest_client,
                                                             plugin)
        self.workflow_templates_exists = False
        self.completion_handler.setDaemon(True)
        self.completion_handler_started = False

    def _start_completion_handling_thread(self):
        if not self.completion_handler_started:
            LOG.info('Starting operation completion handling thread')
            self.completion_handler.start()
            self.completion_handler_started = True

    @staticmethod
    def _get_wf_name(lb):
        return 'LB_' + lb.id

    @log_helpers.log_method_call
    def _verify_workflow_templates(self):
        """Verify the existence of workflows on vDirect server."""
        resource = '/api/workflowTemplate/'
        workflow_templates = {self.workflow_template_name: False}
        for child_wf_name in self.child_workflow_template_names:
            workflow_templates[child_wf_name] = False
        response = _rest_wrapper(self.rest_client.call('GET',
                                                       resource,
                                                       None,
                                                       None), [200])
        for workflow_template in workflow_templates.keys():
            for template in response:
                if workflow_template == template['name']:
                    workflow_templates[workflow_template] = True
                    break
        for template, found in workflow_templates.items():
            if not found:
                raise r_exc.WorkflowTemplateMissing(
                    workflow_template=template)

    @log_helpers.log_method_call
    def workflow_exists(self, lb):
        """Create workflow for loadbalancer instance"""
        wf_name = self._get_wf_name(lb)
        wf_resource = '/api/workflow/%s' % (wf_name)
        try:
            _rest_wrapper(self.rest_client.call(
                'GET', wf_resource, None, None),
                [200])
        except Exception:
            return False
        return True

    @log_helpers.log_method_call
    def _create_workflow(self, lb, lb_network_id, proxy_network_id):
        """Create workflow for loadbalancer instance"""

        self._verify_workflow_templates()

        wf_name = self._get_wf_name(lb)
        service = copy.deepcopy(self.service)
        service['tenantId'] = lb.tenant_id
        service['name'] = 'srv_' + lb_network_id

        if lb_network_id != proxy_network_id:
            self.workflow_params["twoleg_enabled"] = True
            service['primary']['network']['portgroups'] = [
                lb_network_id, proxy_network_id]
        else:
            self.workflow_params["twoleg_enabled"] = False
            service['primary']['network']['portgroups'] = [lb_network_id]

        tmpl_resource = '/api/workflowTemplate/%s?name=%s' % (
            self.workflow_template_name, wf_name)
        _rest_wrapper(self.rest_client.call(
            'POST', tmpl_resource,
            {'parameters': dict(self.workflow_params,
                                service_params=service),
            'tenants': [lb.tenant_id]},
            TEMPLATE_HEADER))

    @log_helpers.log_method_call
    def get_stats(self, ctx, lb):

        wf_name = self._get_wf_name(lb)
        resource = '/api/workflow/%s/action/%s' % (
            wf_name, self.stats_action_name)
        response = _rest_wrapper(self.rest_client.call('POST', resource,
                                 None, TEMPLATE_HEADER), success_codes=[202])
        LOG.debug('stats_action  response: %s ', response)

        resource = '/api/workflow/%s/parameters' % (wf_name)
        response = _rest_wrapper(self.rest_client.call('GET', resource,
                                 None, TEMPLATE_HEADER), success_codes=[200])
        LOG.debug('stats_values  response: %s ', response)
        return response['stats']

    @log_helpers.log_method_call
    def execute_workflow(self, ctx, manager, data_model,
                         old_data_model=None, delete=False):
        lb = data_model.root_loadbalancer

        # Get possible proxy subnet.
        # Proxy subnet equals to LB subnet if no proxy
        # is necessary.
        # Get subnet id of any member located on different than
        # loadbalancer's network. If returned subnet id is the subnet id
        # of loadbalancer - all members are accessible from loadbalancer's
        # network, meaning no second leg or static routes are required.
        # Otherwise, create proxy port on found member's subnet and get its
        # address as a proxy address for loadbalancer instance
        lb_subnet = self.plugin.db._core_plugin.get_subnet(
            ctx, lb.vip_subnet_id)
        proxy_subnet = lb_subnet
        proxy_port_address = lb.vip_address

        if not self.workflow_exists(lb):
            # Create proxy port if needed
            proxy_port_subnet_id = self._get_proxy_port_subnet_id(lb)
            if proxy_port_subnet_id != lb.vip_subnet_id:
                proxy_port = self._create_proxy_port(
                    ctx, lb, proxy_port_subnet_id)
                proxy_subnet = self.plugin.db._core_plugin.get_subnet(
                    ctx, proxy_port['subnet_id'])
                proxy_port_address = proxy_port['ip_address']

            self._create_workflow(lb,
                                  lb_subnet['network_id'],
                                  proxy_subnet['network_id'])
        else:
            # Check if proxy port exists
            proxy_port = self._get_proxy_port(ctx, lb)
            if proxy_port:
                proxy_subnet = self.plugin.db._core_plugin.get_subnet(
                    ctx, proxy_port['subnet_id'])
                proxy_port_address = proxy_port['ip_address']

        # Build objects graph
        objects_graph = self._build_objects_graph(ctx, lb, data_model,
                                                  proxy_port_address,
                                                  proxy_subnet,
                                                  delete)
        LOG.debug("Radware vDirect LB object graph is " + str(objects_graph))

        wf_name = self._get_wf_name(lb)
        resource = '/api/workflow/%s/action/%s' % (
            wf_name, self.workflow_action_name)
        response = _rest_wrapper(self.rest_client.call('POST', resource,
                                 {'parameters': objects_graph},
                                 TEMPLATE_HEADER), success_codes=[202])
        LOG.debug('_update_workflow response: %s ', response)

        oper = OperationAttributes(
            manager, response['uri'], lb,
            data_model, old_data_model,
            delete=delete)

        LOG.debug('Pushing operation %s to the queue', oper)
        self._start_completion_handling_thread()
        self.queue.put_nowait(oper)

    def remove_workflow(self, ctx, manager, lb):
        wf_name = self._get_wf_name(lb)
        LOG.debug('Remove the workflow %s', wf_name)
        resource = '/api/workflow/%s' % (wf_name)
        rest_return = self.rest_client.call('DELETE', resource, None, None)
        response = _rest_wrapper(rest_return, [204, 202, 404])
        if rest_return[rest.RESP_STATUS] in [404]:
            try:
                self._delete_proxy_port(ctx, lb)
                LOG.debug('Proxy port for LB %s was deleted', lb.id)
            except Exception:
                with excutils.save_and_reraise_exception():
                    LOG.error('Proxy port deletion for LB %s failed', lb.id)
            manager.successful_completion(ctx, lb, delete=True)
        else:
            oper = OperationAttributes(
                manager, response['uri'], lb,
                lb, old_data_model=None,
                delete=True,
                post_operation_function=self._delete_proxy_port)

            self._start_completion_handling_thread()
            self.queue.put_nowait(oper)

    def _build_objects_graph(self, ctx, lb, data_model,
                             proxy_port_address, proxy_subnet,
                             deleted):
        """Iterate over the LB model starting from root lb entity
        and build its JSON representtaion for vDirect
        """
        deleted_ids = []
        if deleted:
            deleted_ids.append(data_model.id)

        graph = {}
        for prop in LOADBALANCER_PROPERTIES:
            graph[prop] = getattr(lb, prop, PROPERTY_DEFAULTS.get(prop))

        graph['pip_address'] = proxy_port_address
        graph['configure_allowed_address_pairs'] =\
            self.configure_allowed_address_pairs

        graph['listeners'] = []
        listeners = [
            listener for listener in lb.listeners
            if listener.provisioning_status != n_constants.PENDING_DELETE and
            (listener.default_pool and
             listener.default_pool.provisioning_status !=
             n_constants.PENDING_DELETE and
             listener.default_pool.id not in deleted_ids and
             listener.default_pool.members)]
        for listener in listeners:
            listener_dict = {}
            for prop in LISTENER_PROPERTIES:
                listener_dict[prop] = getattr(
                    listener, prop, PROPERTY_DEFAULTS.get(prop))

            cert_mgr = CERT_MANAGER_PLUGIN.CertManager()

            if listener.default_tls_container_id:
                default_cert = cert_mgr.get_cert(
                    project_id=listener.tenant_id,
                    cert_ref=listener.default_tls_container_id,
                    resource_ref=cert_mgr.get_service_url(
                        listener.loadbalancer_id),
                    service_name='Neutron LBaaS v2 Radware provider')
                def_cert_dict = {
                    'id': listener.default_tls_container_id,
                    'certificate': default_cert.get_certificate(),
                    'intermediates': default_cert.get_intermediates(),
                    'private_key': default_cert.get_private_key(),
                    'passphrase': default_cert.get_private_key_passphrase()}
                listener_dict['default_tls_certificate'] = def_cert_dict

            if listener.sni_containers:
                listener_dict['sni_tls_certificates'] = []
                for sni_container in listener.sni_containers:
                    sni_cert = cert_mgr.get_cert(
                        project_id=listener.tenant_id,
                        cert_ref=sni_container.tls_container_id,
                        resource_ref=cert_mgr.get_service_url(
                            listener.loadbalancer_id),
                        service_name='Neutron LBaaS v2 Radware provider')
                    listener_dict['sni_tls_certificates'].append(
                        {'id': sni_container.tls_container_id,
                         'position': sni_container.position,
                         'certificate': sni_cert.get_certificate(),
                         'intermediates': sni_cert.get_intermediates(),
                         'private_key': sni_cert.get_private_key(),
                         'passphrase': sni_cert.get_private_key_passphrase()})

            listener_dict['l7_policies'] = []
            policies = [
                policy for policy in listener.l7_policies
                if policy.provisioning_status != n_constants.PENDING_DELETE and
                policy.id not in deleted_ids]
            for policy in policies:
                policy_dict = {}
                for prop in L7_POLICY_PROPERTIES:
                    policy_dict[prop] = getattr(
                        policy, prop, PROPERTY_DEFAULTS.get(prop))
                policy_dict['rules'] = []
                rules = [
                    rule for rule in policy.rules
                    if rule.provisioning_status !=
                    n_constants.PENDING_DELETE and
                    rule.id not in deleted_ids]
                for rule in rules:
                    rule_dict = {}
                    for prop in L7_RULE_PROPERTIES:
                        rule_dict[prop] = getattr(
                            rule, prop, PROPERTY_DEFAULTS.get(prop))
                    policy_dict['rules'].append(rule_dict)
                if policy_dict['rules']:
                    listener_dict['l7_policies'].append(policy_dict)

            def_pool_dict = {'id': listener.default_pool.id}

            if listener.default_pool.session_persistence:
                sess_pers_dict = {}
                for prop in SESSION_PERSISTENCY_PROPERTIES:
                    sess_pers_dict[prop] = getattr(
                        listener.default_pool.session_persistence, prop,
                        PROPERTY_DEFAULTS.get(prop))
                def_pool_dict['sessionpersistence'] = sess_pers_dict
            listener_dict['default_pool'] = def_pool_dict

            graph['listeners'].append(listener_dict)

        graph['pools'] = []
        pools = [
            pool for pool in lb.pools
            if pool.provisioning_status != n_constants.PENDING_DELETE and
            pool.id not in deleted_ids]
        for pool in pools:
            pool_dict = {}
            for prop in POOL_PROPERTIES:
                pool_dict[prop] = getattr(
                    pool, prop,
                    PROPERTY_DEFAULTS.get(prop))

            if (pool.healthmonitor and
                pool.healthmonitor.provisioning_status !=
                n_constants.PENDING_DELETE and
                pool.healthmonitor.id not in deleted_ids):
                hm_dict = {}
                for prop in HEALTH_MONITOR_PROPERTIES:
                    hm_dict[prop] = getattr(
                        pool.healthmonitor, prop,
                        PROPERTY_DEFAULTS.get(prop))
                pool_dict['healthmonitor'] = hm_dict

            pool_dict['members'] = []
            members = [
                member for member in pool.members
                if member.provisioning_status != n_constants.PENDING_DELETE and
                member.id not in deleted_ids]
            for member in members:
                member_dict = {}
                for prop in MEMBER_PROPERTIES:
                    member_dict[prop] = getattr(
                        member, prop,
                        PROPERTY_DEFAULTS.get(prop))
                if (proxy_port_address != lb.vip_address and
                    netaddr.IPAddress(member.address)
                    not in netaddr.IPNetwork(proxy_subnet['cidr'])):
                    self._accomplish_member_static_route_data(
                        ctx, member, member_dict,
                        proxy_subnet['gateway_ip'])
                pool_dict['members'].append(member_dict)
            graph['pools'].append(pool_dict)

        return graph

    def _get_proxy_port_subnet_id(self, lb):
        """Look for at least one member of any listener's pool
        that is located on subnet different than loabalancer's subnet.
        If such member found, return its subnet id.
        Otherwise, return loadbalancer's subnet id
        """
        for listener in lb.listeners:
            if listener.default_pool:
                for member in listener.default_pool.members:
                    if lb.vip_subnet_id != member.subnet_id:
                        return member.subnet_id
        return lb.vip_subnet_id

    def _create_proxy_port(self,
        ctx, lb, proxy_port_subnet_id):
        """Check if proxy port was created earlier.
        If not, create a new port on proxy subnet and return its ip address.
        Returns port IP address
        """
        proxy_port = self._get_proxy_port(ctx, lb)
        if proxy_port:
            LOG.info('LB %(lb_id)s proxy port exists on subnet '
                     '%(subnet_id)s with ip address %(ip_address)s' %
                     {'lb_id': lb.id, 'subnet_id': proxy_port['subnet_id'],
                      'ip_address': proxy_port['ip_address']})
            return proxy_port

        proxy_port_name = 'proxy_' + lb.id
        proxy_port_subnet = self.plugin.db._core_plugin.get_subnet(
            ctx, proxy_port_subnet_id)
        proxy_port_data = {
            'tenant_id': lb.tenant_id,
            'name': proxy_port_name,
            'network_id': proxy_port_subnet['network_id'],
            'mac_address': n_constants.ATTR_NOT_SPECIFIED,
            'admin_state_up': False,
            'device_id': '',
            'device_owner': 'neutron:' + pg_constants.LOADBALANCERV2,
            'fixed_ips': [{'subnet_id': proxy_port_subnet_id}]
        }
        proxy_port = self.plugin.db._core_plugin.create_port(
            ctx, {'port': proxy_port_data})
        proxy_port_ip_data = proxy_port['fixed_ips'][0]

        LOG.info('LB %(lb_id)s proxy port created on subnet %(subnet_id)s '
                 'with ip address %(ip_address)s' %
                 {'lb_id': lb.id, 'subnet_id': proxy_port_ip_data['subnet_id'],
                  'ip_address': proxy_port_ip_data['ip_address']})

        return proxy_port_ip_data

    def _get_proxy_port(self, ctx, lb):
        ports = self.plugin.db._core_plugin.get_ports(
            ctx, filters={'name': ['proxy_' + lb.id], })
        if not ports:
            return None

        proxy_port = ports[0]
        return proxy_port['fixed_ips'][0]

    def _delete_proxy_port(self, ctx, lb):
        port_filter = {
            'name': ['proxy_' + lb.id],
        }
        ports = self.plugin.db._core_plugin.get_ports(
            ctx, filters=port_filter)
        if ports:
            proxy_port = ports[0]
            proxy_port_ip_data = proxy_port['fixed_ips'][0]
            try:
                LOG.info('Deleting LB %(lb_id)s proxy port on subnet  '
                         '%(subnet_id)s with ip address %(ip_address)s' %
                         {'lb_id': lb.id,
                          'subnet_id': proxy_port_ip_data['subnet_id'],
                          'ip_address': proxy_port_ip_data['ip_address']})
                self.plugin.db._core_plugin.delete_port(
                    ctx, proxy_port['id'])

            except Exception as exception:
                # stop exception propagation, nport may have
                # been deleted by other means
                LOG.warning('Proxy port deletion failed: %r',
                            exception)

    def _accomplish_member_static_route_data(self,
        ctx, member, member_data, proxy_gateway_ip):
        member_ports = self.plugin.db._core_plugin.get_ports(
            ctx,
            filters={'fixed_ips': {'ip_address': [member.address]},
                     'tenant_id': [member.tenant_id]})
        if len(member_ports) == 1:
            member_port = member_ports[0]
            member_port_ip_data = member_port['fixed_ips'][0]
            LOG.debug('member_port_ip_data:' + repr(member_port_ip_data))
            member_subnet = self.plugin.db._core_plugin.get_subnet(
                ctx,
                member_port_ip_data['subnet_id'])
            LOG.debug('member_subnet:' + repr(member_subnet))
            member_network = netaddr.IPNetwork(member_subnet['cidr'])
            member_data['subnet'] = str(member_network.network)
            member_data['mask'] = str(member_network.netmask)
        else:
            member_data['subnet'] = member_data['address']
        member_data['gw'] = proxy_gateway_ip


class OperationCompletionHandler(threading.Thread):

    """Update DB with operation status or delete the entity from DB."""

    def __init__(self, queue, rest_client, plugin):
        threading.Thread.__init__(self)
        self.queue = queue
        self.rest_client = rest_client
        self.plugin = plugin
        self.stoprequest = threading.Event()
        self.opers_to_handle_before_rest = 0

    def join(self, timeout=None):
        self.stoprequest.set()
        super(OperationCompletionHandler, self).join(timeout)

    def handle_operation_completion(self, oper):
        result = self.rest_client.call('GET',
                                       oper.operation_url,
                                       None,
                                       None)
        LOG.debug('Operation completion requested %(uri)s and got: %(result)s',
                  {'uri': oper.operation_url, 'result': result})
        completed = result[rest.RESP_DATA]['complete']
        reason = result[rest.RESP_REASON],
        description = result[rest.RESP_STR]
        if completed:
            # operation is done - update the DB with the status
            # or delete the entire graph from DB
            success = result[rest.RESP_DATA]['success']
            sec_to_completion = time.time() - oper.creation_time
            debug_data = {'oper': oper,
                          'sec_to_completion': sec_to_completion,
                          'success': success}
            LOG.debug('Operation %(oper)s is completed after '
                      '%(sec_to_completion)d sec '
                      'with success status: %(success)s :',
                      debug_data)
            if not success:
                # failure - log it and set the return ERROR as DB state
                if reason or description:
                    msg = 'Reason:%s. Description:%s' % (reason, description)
                else:
                    msg = "unknown"
                error_params = {"operation": oper, "msg": msg}
                LOG.error(
                    'Operation %(operation)s failed. Reason: %(msg)s',
                    error_params)
                oper.status = n_constants.ERROR
                OperationCompletionHandler._run_post_failure_function(oper)
            else:
                oper.status = n_constants.ACTIVE
                OperationCompletionHandler._run_post_success_function(oper)

        return completed

    def run(self):
        while not self.stoprequest.isSet():
            try:
                oper = self.queue.get(timeout=1)

                # Get the current queue size (N) and set the counter with it.
                # Handle N operations with no intermission.
                # Once N operations handles, get the size again and repeat.
                if self.opers_to_handle_before_rest <= 0:
                    self.opers_to_handle_before_rest = self.queue.qsize() + 1

                LOG.debug('Operation consumed from the queue: ' +
                          str(oper))
                # check the status - if oper is done: update the db ,
                # else push the oper again to the queue
                if not self.handle_operation_completion(oper):
                    LOG.debug('Operation %s is not completed yet..' % oper)
                    # Not completed - push to the queue again
                    self.queue.put_nowait(oper)

                self.queue.task_done()
                self.opers_to_handle_before_rest -= 1

                # Take one second rest before start handling
                # new operations or operations handled before
                if self.opers_to_handle_before_rest <= 0:
                    time.sleep(1)

            except Queue.Empty:
                continue
            except Exception:
                LOG.error(
                    "Exception was thrown inside OperationCompletionHandler")

    @staticmethod
    def _run_post_success_function(oper):
        try:
            ctx = context.get_admin_context()
            if oper.post_operation_function:
                oper.post_operation_function(ctx, oper.data_model)
            oper.manager.successful_completion(ctx, oper.data_model,
                                               delete=oper.delete)
            LOG.debug('Post-operation success function completed '
                      'for operation %s',
                      repr(oper))
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error('Post-operation success function failed '
                          'for operation %s',
                          repr(oper))

    @staticmethod
    def _run_post_failure_function(oper):
        try:
            ctx = context.get_admin_context()
            oper.manager.failed_completion(ctx, oper.data_model)
            LOG.debug('Post-operation failure function completed '
                      'for operation %s',
                      repr(oper))
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error('Post-operation failure function failed '
                          'for operation %s',
                          repr(oper))


class OperationAttributes(object):

    """Holds operation attributes"""

    def __init__(self,
                 manager,
                 operation_url,
                 lb,
                 data_model=None,
                 old_data_model=None,
                 delete=False,
                 post_operation_function=None):
        self.manager = manager
        self.operation_url = operation_url
        self.lb = lb
        self.data_model = data_model
        self.old_data_model = old_data_model
        self.delete = delete
        self.post_operation_function = post_operation_function
        self.creation_time = time.time()

    def __repr__(self):
        attrs = self.__dict__
        items = ("%s = %r" % (k, v) for k, v in attrs.items())
        return "<%s: {%s}>" % (self.__class__.__name__, ', '.join(items))


def _rest_wrapper(response, success_codes=None):
    """Wrap a REST call and make sure a valido status is returned."""
    success_codes = success_codes or [202]
    if not response:
        raise r_exc.RESTRequestFailure(
            status=-1,
            reason="Unknown",
            description="Unknown",
            success_codes=success_codes
        )
    elif response[rest.RESP_STATUS] not in success_codes:
        raise r_exc.RESTRequestFailure(
            status=response[rest.RESP_STATUS],
            reason=response[rest.RESP_REASON],
            description=response[rest.RESP_STR],
            success_codes=success_codes
        )
    else:
        LOG.debug("this is a respone: %s" % (response,))
        return response[rest.RESP_DATA]
