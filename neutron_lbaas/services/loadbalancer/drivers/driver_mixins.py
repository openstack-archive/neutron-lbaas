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
import six

from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron_lbaas.services.loadbalancer import data_models


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
        ACTIVE.  Also sets the operating status of obj to ONLINE.  Should be
        called last in the implementor's BaseManagerMixin methods for
        successful runs.

        :param context: neutron context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        :param delete: set True if being called from a delete method.  Will
                       most likely result in the obj being deleted from the db.
        """
        # TODO(blogan): Will need to decide what to do with all operating
        # statuses.  Update to ONLINE here, or leave the operating status
        # alone and let health checks update
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        if delete:
            self.db_delete_method(context, obj.id)
        if obj == obj.root_loadbalancer and delete:
            # Load balancer was deleted and no longer exists
            return
        lb_op_status = obj.root_loadbalancer.operating_status
        if obj == obj.root_loadbalancer:
            lb_op_status = lb_const.ONLINE
        self.driver.plugin.db.update_status(
            context, models.LoadBalancer, obj.root_loadbalancer.id,
            provisioning_status=constants.ACTIVE,
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
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ACTIVE,
            operating_status=obj_op_status)

    def failed_completion(self, context, obj):
        """
        Sets the provisioning status of the load balancer and obj to
        ERROR.  Should be called whenever something goes wrong (raised
        exception) in an implementor's BaseManagerMixin methods.

        :param context: neutron context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        """
        # TODO(blogan): Will need to decide what to do with all operating
        # statuses.  Update to ONLINE here, or leave the operating status
        # alone and let health checks update
        self.driver.plugin.db.update_status(
            context, models.LoadBalancer, obj.root_loadbalancer.id,
            provisioning_status=constants.ERROR)
        if obj == obj.root_loadbalancer:
            # Do not want to update the status of the load balancer again
            return
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ERROR,
            operating_status=lb_const.OFFLINE)


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
