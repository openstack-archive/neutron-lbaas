# Copyright 2014 A10 Networks
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

import abc
from neutron.plugins.common import constants
from oslo_log import log as logging
import six

from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models


LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class BaseManagerMixin(object):

    def __init__(self, driver):
        self.driver = driver

    @abc.abstractproperty
    def db_delete_method(self):
        pass

    @abc.abstractmethod
    def create(self, context, obj):
        pass

    @abc.abstractmethod
    def update(self, context, obj_old, obj):
        pass

    @abc.abstractmethod
    def delete(self, context, obj):
        pass

    def successful_completion(self, context, obj, delete=False):
        """
        Sets the provisioning_status of the load balancer and obj to
        ACTIVE.  Should be called last in the implementor's BaseManagerMixin
        methods for successful runs.

        :param context: neutron context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        :param delete: set True if being called from a delete method.  Will
                       most likely result in the obj being deleted from the db.
        """
        LOG.debug("Starting successful_completion method after a successful "
                  "driver action.")
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        if delete:
            LOG.debug("Deleting object type {0} with id of {1}.".format(
                obj.__class__, obj.id))
            self.db_delete_method(context, obj.id)
        if obj == obj.root_loadbalancer and delete:
            # Load balancer was deleted and no longer exists
            return
        lb_op_status = None
        lb_p_status = constants.ACTIVE
        if obj == obj.root_loadbalancer:
            # only set the status to online if this an operation on the
            # load balancer
            lb_op_status = lb_const.ONLINE
        LOG.debug("Updating load balancer {0} to provisioning_status = {1}, "
                  "operating_status = {2}.".format(obj.root_loadbalancer.id,
                                                   lb_p_status, lb_op_status))
        self.driver.plugin.db.update_status(
            context, models.LoadBalancer, obj.root_loadbalancer.id,
            provisioning_status=lb_p_status,
            operating_status=lb_op_status)
        if obj == obj.root_loadbalancer or delete:
            # Do not want to update the status of the load balancer again
            # Or the obj was deleted from the db so no need to update the
            # statuses
            return
        obj_op_status = lb_const.ONLINE
        if isinstance(obj, data_models.HealthMonitor):
            # Health Monitor does not have an operating status
            obj_op_status = None
        LOG.debug("Updating object of type {0} with id of {1} to "
                  "provisioning_status = {2}, operating_status = {3}".format(
                      obj.__class__, obj.id, constants.ACTIVE, obj_op_status))
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ACTIVE,
            operating_status=obj_op_status)

    def failed_completion(self, context, obj):
        """
        Sets the provisioning status of the obj to ERROR.  If obj is a
        loadbalancer it will be set to ERROR, otherwise set to ACTIVE. Should
        be called whenever something goes wrong (raised exception) in an
        implementor's BaseManagerMixin methods.

        :param context: neutron context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        """
        LOG.debug("Starting failed_completion method after a failed driver "
                  "action.")
        if isinstance(obj, data_models.LoadBalancer):
            LOG.debug("Updating load balancer {0} to provisioning_status = "
                      "{1}, operating_status = {2}.".format(
                          obj.root_loadbalancer.id, constants.ERROR,
                          lb_const.OFFLINE))
            self.driver.plugin.db.update_status(
                context, models.LoadBalancer, obj.root_loadbalancer.id,
                provisioning_status=constants.ERROR,
                operating_status=lb_const.OFFLINE)
            return
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        LOG.debug("Updating object of type {0} with id of {1} to "
                  "provisioning_status = {2}, operating_status = {3}".format(
                      obj.__class__, obj.id, constants.ERROR,
                      lb_const.OFFLINE))
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ERROR,
            operating_status=lb_const.OFFLINE)
        LOG.debug("Updating load balancer {0} to "
                  "provisioning_status = {1}".format(obj.root_loadbalancer.id,
                                                     constants.ACTIVE))
        self.driver.plugin.db.update_status(
            context, models.LoadBalancer, obj.root_loadbalancer.id,
            provisioning_status=constants.ACTIVE)

    def update_vip(self, context, loadbalancer_id, vip_address,
                   vip_port_id=None):
        lb_update = {'vip_address': vip_address}
        if vip_port_id:
            lb_update['vip_port_id'] = vip_port_id
        self.driver.plugin.db.update_loadbalancer(context, loadbalancer_id,
                                                  lb_update)


@six.add_metaclass(abc.ABCMeta)
class BaseRefreshMixin(object):

    @abc.abstractmethod
    def refresh(self, context, obj):
        pass


@six.add_metaclass(abc.ABCMeta)
class BaseStatsMixin(object):

    @abc.abstractmethod
    def stats(self, context, obj):
        pass
