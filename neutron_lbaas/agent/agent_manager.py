# Copyright 2013 New Dream Network, LLC (DreamHost)
# Copyright 2015 Rackspace
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

from neutron.agent.linux import external_process
from neutron.agent import rpc as agent_rpc
from neutron.services import provider_configuration as provconfig
from neutron_lib import constants
from neutron_lib import context as ncontext
from neutron_lib import exceptions as n_exc
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging
from oslo_service import loopingcall
from oslo_service import periodic_task
from oslo_utils import importutils

from neutron_lbaas._i18n import _
from neutron_lbaas.agent import agent_api
from neutron_lbaas.drivers.common import agent_driver_base
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models

LOG = logging.getLogger(__name__)

DEVICE_DRIVERS = 'device_drivers'

OPTS = [
    cfg.MultiStrOpt(
        'device_driver',
        default=['neutron_lbaas.drivers.haproxy.'
                 'namespace_driver.HaproxyNSDriver'],
        deprecated_for_removal=True,
        deprecated_since='Queens',
        deprecated_reason='The neutron-lbaas project is now deprecated. '
                          'See: https://wiki.openstack.org/wiki/Neutron/LBaaS/'
                          'Deprecation',
        help=_('Drivers used to manage loadbalancing devices'),
    ),
]


class DeviceNotFoundOnAgent(n_exc.NotFound):
    message = _('Unknown device with loadbalancer_id %(loadbalancer_id)s')


class LbaasAgentManager(periodic_task.PeriodicTasks):

    # history
    #   1.0 Initial version
    target = oslo_messaging.Target(version='1.0')

    def __init__(self, conf):
        super(LbaasAgentManager, self).__init__(conf)
        self.conf = conf
        self.context = ncontext.get_admin_context_without_session()
        self.serializer = agent_driver_base.DataModelSerializer()
        self.plugin_rpc = agent_api.LbaasAgentApi(
            lb_const.LOADBALANCER_PLUGINV2,
            self.context,
            self.conf.host
        )
        self._process_monitor = external_process.ProcessMonitor(
            config=self.conf, resource_type='loadbalancer')
        self._load_drivers()

        self.agent_state = {
            'binary': 'neutron-lbaasv2-agent',
            'host': conf.host,
            'topic': lb_const.LOADBALANCER_AGENTV2,
            'configurations': {'device_drivers': self.device_drivers.keys()},
            'agent_type': lb_const.AGENT_TYPE_LOADBALANCERV2,
            'start_flag': True}
        self.admin_state_up = True

        self._setup_state_rpc()
        self.needs_resync = False
        # pool_id->device_driver_name mapping used to store known instances
        self.instance_mapping = {}

    def _load_drivers(self):
        self.device_drivers = {}
        for driver in self.conf.device_driver:
            driver = provconfig.get_provider_driver_class(driver,
                                                          DEVICE_DRIVERS)
            try:
                driver_inst = importutils.import_object(
                    driver,
                    self.conf,
                    self.plugin_rpc,
                    self._process_monitor
                )
            except ImportError:
                msg = _('Error importing loadbalancer device driver: %s')
                raise SystemExit(msg % driver)

            driver_name = driver_inst.get_name()
            if driver_name not in self.device_drivers:
                self.device_drivers[driver_name] = driver_inst
            else:
                msg = _('Multiple device drivers with the same name found: %s')
                raise SystemExit(msg % driver_name)

    def _setup_state_rpc(self):
        self.state_rpc = agent_rpc.PluginReportStateAPI(
            lb_const.LOADBALANCER_PLUGINV2)
        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            heartbeat.start(interval=report_interval)

    def _report_state(self):
        try:
            instance_count = len(self.instance_mapping)
            self.agent_state['configurations']['instances'] = instance_count
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.exception("Failed reporting state!")

    def initialize_service_hook(self, started_by):
        self.sync_state()

    @periodic_task.periodic_task
    def periodic_resync(self, context):
        if self.needs_resync:
            self.needs_resync = False
            self.sync_state()

    @periodic_task.periodic_task(spacing=6)
    def collect_stats(self, context):
        for loadbalancer_id, driver_name in self.instance_mapping.items():
            driver = self.device_drivers[driver_name]
            try:
                stats = driver.loadbalancer.get_stats(loadbalancer_id)
                if stats:
                    self.plugin_rpc.update_loadbalancer_stats(
                        loadbalancer_id, stats)
            except Exception:
                LOG.exception('Error updating statistics on loadbalancer %s',
                              loadbalancer_id)
                self.needs_resync = True

    def sync_state(self):
        known_instances = set(self.instance_mapping.keys())
        try:
            ready_instances = set(self.plugin_rpc.get_ready_devices())

            for deleted_id in known_instances - ready_instances:
                self._destroy_loadbalancer(deleted_id)

            for loadbalancer_id in ready_instances:
                self._reload_loadbalancer(loadbalancer_id)

        except Exception:
            LOG.exception('Unable to retrieve ready devices')
            self.needs_resync = True

        self.remove_orphans()

    def _get_driver(self, loadbalancer_id):
        if loadbalancer_id not in self.instance_mapping:
            raise DeviceNotFoundOnAgent(loadbalancer_id=loadbalancer_id)

        driver_name = self.instance_mapping[loadbalancer_id]
        return self.device_drivers[driver_name]

    def _reload_loadbalancer(self, loadbalancer_id):
        try:
            loadbalancer_dict = self.plugin_rpc.get_loadbalancer(
                loadbalancer_id)
            loadbalancer = data_models.LoadBalancer.from_dict(
                loadbalancer_dict)
            driver_name = loadbalancer.provider.device_driver
            if driver_name not in self.device_drivers:
                LOG.error('No device driver on agent: %s.', driver_name)
                self.plugin_rpc.update_status(
                    'loadbalancer', loadbalancer_id, constants.ERROR)
                return

            self.device_drivers[driver_name].deploy_instance(loadbalancer)
            self.instance_mapping[loadbalancer_id] = driver_name
            self.plugin_rpc.loadbalancer_deployed(loadbalancer_id)
        except Exception:
            LOG.exception('Unable to deploy instance for loadbalancer: %s',
                          loadbalancer_id)
            self.needs_resync = True

    def _destroy_loadbalancer(self, lb_id):
        driver = self._get_driver(lb_id)
        try:
            driver.undeploy_instance(lb_id, delete_namespace=True)
            del self.instance_mapping[lb_id]
            self.plugin_rpc.loadbalancer_destroyed(lb_id)
        except Exception:
            LOG.exception('Unable to destroy device for loadbalancer: %s',
                          lb_id)
            self.needs_resync = True

    def remove_orphans(self):
        for driver_name in self.device_drivers:
            lb_ids = [lb_id for lb_id in self.instance_mapping
                      if self.instance_mapping[lb_id] == driver_name]
            try:
                self.device_drivers[driver_name].remove_orphans(lb_ids)
            except NotImplementedError:
                pass  # Not all drivers will support this

    def _handle_failed_driver_call(self, operation, obj, driver):
        obj_type = obj.__class__.__name__.lower()
        LOG.exception('%(operation)s %(obj)s %(id)s failed on device '
                      'driver %(driver)s',
                      {'operation': operation.capitalize(), 'obj': obj_type,
                       'id': obj.id, 'driver': driver})
        self._update_statuses(obj, error=True)

    def agent_updated(self, context, payload):
        """Handle the agent_updated notification event."""
        if payload['admin_state_up'] != self.admin_state_up:
            self.admin_state_up = payload['admin_state_up']
            if self.admin_state_up:
                self.needs_resync = True
            else:
                # Copy keys since the dictionary is modified in the loop body
                for loadbalancer_id in list(self.instance_mapping.keys()):
                    LOG.info("Destroying loadbalancer %s due to agent "
                             "disabling", loadbalancer_id)
                    self._destroy_loadbalancer(loadbalancer_id)
            LOG.info("Agent_updated by server side %s!", payload)

    def _update_statuses(self, obj, error=False):
        lb_p_status = constants.ACTIVE
        lb_o_status = None
        obj_type = obj.__class__.__name__.lower()
        obj_p_status = constants.ACTIVE
        obj_o_status = lb_const.ONLINE
        if error:
            obj_p_status = constants.ERROR
            obj_o_status = lb_const.OFFLINE
        if isinstance(obj, data_models.HealthMonitor):
            obj_o_status = None
        if isinstance(obj, data_models.LoadBalancer):
            lb_o_status = lb_const.ONLINE
            if error:
                lb_p_status = constants.ERROR
                lb_o_status = lb_const.OFFLINE
            lb = obj
        else:
            lb = obj.root_loadbalancer
            self.plugin_rpc.update_status(obj_type, obj.id,
                                          provisioning_status=obj_p_status,
                                          operating_status=obj_o_status)
        self.plugin_rpc.update_status('loadbalancer', lb.id,
                                      provisioning_status=lb_p_status,
                                      operating_status=lb_o_status)

    def create_loadbalancer(self, context, loadbalancer, driver_name):
        loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
        if driver_name not in self.device_drivers:
            LOG.error('No device driver on agent: %s.', driver_name)
            self.plugin_rpc.update_status('loadbalancer', loadbalancer.id,
                                          provisioning_status=constants.ERROR)
            return
        driver = self.device_drivers[driver_name]
        try:
            driver.loadbalancer.create(loadbalancer)
        except Exception:
            self._handle_failed_driver_call('create', loadbalancer,
                                            driver.get_name())
        else:
            self.instance_mapping[loadbalancer.id] = driver_name
            self._update_statuses(loadbalancer)

    def update_loadbalancer(self, context, old_loadbalancer, loadbalancer):
        loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
        old_loadbalancer = data_models.LoadBalancer.from_dict(old_loadbalancer)
        driver = self._get_driver(loadbalancer.id)
        try:
            driver.loadbalancer.update(old_loadbalancer, loadbalancer)
        except Exception:
            self._handle_failed_driver_call('update', loadbalancer,
                                            driver.get_name())
        else:
            self._update_statuses(loadbalancer)

    def delete_loadbalancer(self, context, loadbalancer):
        loadbalancer = data_models.LoadBalancer.from_dict(loadbalancer)
        driver = self._get_driver(loadbalancer.id)
        driver.loadbalancer.delete(loadbalancer)
        del self.instance_mapping[loadbalancer.id]

    def create_listener(self, context, listener):
        listener = data_models.Listener.from_dict(listener)
        driver = self._get_driver(listener.loadbalancer.id)
        try:
            driver.listener.create(listener)
        except Exception:
            self._handle_failed_driver_call('create', listener,
                                            driver.get_name())
        else:
            self._update_statuses(listener)

    def update_listener(self, context, old_listener, listener):
        listener = data_models.Listener.from_dict(listener)
        old_listener = data_models.Listener.from_dict(old_listener)
        driver = self._get_driver(listener.loadbalancer.id)
        try:
            driver.listener.update(old_listener, listener)
        except Exception:
            self._handle_failed_driver_call('update', listener,
                                            driver.get_name())
        else:
            self._update_statuses(listener)

    def delete_listener(self, context, listener):
        listener = data_models.Listener.from_dict(listener)
        driver = self._get_driver(listener.loadbalancer.id)
        driver.listener.delete(listener)

    def create_pool(self, context, pool):
        pool = data_models.Pool.from_dict(pool)
        driver = self._get_driver(pool.loadbalancer.id)
        try:
            driver.pool.create(pool)
        except Exception:
            self._handle_failed_driver_call('create', pool, driver.get_name())
        else:
            self._update_statuses(pool)

    def update_pool(self, context, old_pool, pool):
        pool = data_models.Pool.from_dict(pool)
        old_pool = data_models.Pool.from_dict(old_pool)
        driver = self._get_driver(pool.loadbalancer.id)
        try:
            driver.pool.update(old_pool, pool)
        except Exception:
            self._handle_failed_driver_call('create', pool, driver.get_name())
        else:
            self._update_statuses(pool)

    def delete_pool(self, context, pool):
        pool = data_models.Pool.from_dict(pool)
        driver = self._get_driver(pool.loadbalancer.id)
        driver.pool.delete(pool)

    def create_member(self, context, member):
        member = data_models.Member.from_dict(member)
        driver = self._get_driver(member.pool.loadbalancer.id)
        try:
            driver.member.create(member)
        except Exception:
            self._handle_failed_driver_call('create', member,
                                            driver.get_name())
        else:
            self._update_statuses(member)

    def update_member(self, context, old_member, member):
        member = data_models.Member.from_dict(member)
        old_member = data_models.Member.from_dict(old_member)
        driver = self._get_driver(member.pool.loadbalancer.id)
        try:
            driver.member.update(old_member, member)
        except Exception:
            self._handle_failed_driver_call('create', member,
                                            driver.get_name())
        else:
            self._update_statuses(member)

    def delete_member(self, context, member):
        member = data_models.Member.from_dict(member)
        driver = self._get_driver(member.pool.loadbalancer.id)
        driver.member.delete(member)

    def create_healthmonitor(self, context, healthmonitor):
        healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
        driver = self._get_driver(healthmonitor.pool.loadbalancer.id)
        try:
            driver.healthmonitor.create(healthmonitor)
        except Exception:
            self._handle_failed_driver_call('create', healthmonitor,
                                            driver.get_name())
        else:
            self._update_statuses(healthmonitor)

    def update_healthmonitor(self, context, old_healthmonitor,
                             healthmonitor):
        healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
        old_healthmonitor = data_models.HealthMonitor.from_dict(
            old_healthmonitor)
        driver = self._get_driver(healthmonitor.pool.loadbalancer.id)
        try:
            driver.healthmonitor.update(old_healthmonitor, healthmonitor)
        except Exception:
            self._handle_failed_driver_call('create', healthmonitor,
                                            driver.get_name())
        else:
            self._update_statuses(healthmonitor)

    def delete_healthmonitor(self, context, healthmonitor):
        healthmonitor = data_models.HealthMonitor.from_dict(healthmonitor)
        driver = self._get_driver(healthmonitor.pool.loadbalancer.id)
        driver.healthmonitor.delete(healthmonitor)
