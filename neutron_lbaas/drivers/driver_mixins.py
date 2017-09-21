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

from neutron_lib import constants
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

    def _successful_completion_lb_graph(self, context, obj):
        listeners = obj.listeners
        obj.listeners = []
        for listener in listeners:
            # need to maintain the link from the child to the load balancer
            listener.loadbalancer = obj
            pool = listener.default_pool
            l7_policies = listener.l7_policies
            if pool:
                pool.listener = listener
                hm = pool.healthmonitor
                if hm:
                    hm.pool = pool
                    self.successful_completion(context, hm)
                for member in pool.members:
                    member.pool = pool
                    self.successful_completion(context, member)
                self.successful_completion(context, pool)
            if l7_policies:
                for l7policy in l7_policies:
                    l7policy.listener = listener
                    l7rules = l7policy.rules
                    for l7rule in l7rules:
                        l7rule.l7policy = l7policy
                        self.successful_completion(context, l7rule)
                    redirect_pool = l7policy.redirect_pool
                    if redirect_pool:
                        redirect_pool.listener = listener
                        rhm = redirect_pool.healthmonitor
                        if rhm:
                            rhm.pool = redirect_pool
                            self.successful_completion(context, rhm)
                        for rmember in redirect_pool.members:
                            rmember.pool = redirect_pool
                            self.successful_completion(context, rmember)
                        self.successful_completion(context, redirect_pool)
                    self.successful_completion(context, l7policy)
            self.successful_completion(context, listener)
        self.successful_completion(context, obj)

    def successful_completion(self, context, obj, delete=False,
                              lb_create=False):
        """
        Sets the provisioning_status of the load balancer and obj to
        ACTIVE.  Should be called last in the implementor's BaseManagerMixin
        methods for successful runs.

        :param context: neutron_lib context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        :param delete: set True if being called from a delete method.  Will
                       most likely result in the obj being deleted from the db.
        :param lb_create: set True if this is being called after a successful
                          load balancer create.
        """
        LOG.debug("Starting successful_completion method after a successful "
                  "driver action.")
        if lb_create and obj.listeners:
            self._successful_completion_lb_graph(context, obj)
            return
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        if delete:
            # Check if driver is responsible for vip allocation.  If the driver
            # is responsible, then it is also responsible for cleaning it up.
            # At this point, the VIP should already be cleaned up, so we are
            # just doing neutron lbaas db cleanup.
            if (obj == obj.root_loadbalancer and
                    self.driver.load_balancer.allocates_vip):
                # NOTE(blogan): this is quite dumb to do but it is necessary
                # so that a false negative pep8 error does not get thrown. An
                # "unexpected-keyword-argument" pep8 error occurs bc
                # self.db_delete_method is a @property method that returns a
                # method.
                kwargs = {'delete_vip_port': False}
                self.db_delete_method(context, obj.id, **kwargs)
            else:
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

        # Update the load balancer's vip address and vip port id if the driver
        # was responsible for allocating the vip.
        if (self.driver.load_balancer.allocates_vip and lb_create and
                isinstance(obj, data_models.LoadBalancer)):
            self.driver.plugin.db.update_loadbalancer(
                context, obj.id, {'vip_address': obj.vip_address,
                                  'vip_port_id': obj.vip_port_id})
        if delete:
            # We cannot update the status of obj if it was deleted but if the
            # obj is not a load balancer, the root load balancer should be
            # updated
            if not isinstance(obj, data_models.LoadBalancer):
                self.driver.plugin.db.update_status(
                    context, models.LoadBalancer, obj.root_loadbalancer.id,
                    provisioning_status=lb_p_status,
                    operating_status=lb_op_status)
            return
        obj_op_status = lb_const.ONLINE
        if isinstance(obj, data_models.HealthMonitor):
            # Health Monitor does not have an operating status
            obj_op_status = None
        LOG.debug("Updating object of type %s with id of %s to "
                  "provisioning_status = %s, operating_status = %s",
                  obj.__class__, obj.id, constants.ACTIVE, obj_op_status)
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ACTIVE,
            operating_status=obj_op_status)
        if not isinstance(obj, data_models.LoadBalancer):
            # Only update the status of the root_loadbalancer if the previous
            # update was not the root load balancer so we are not updating
            # it twice.
            self.driver.plugin.db.update_status(
                context, models.LoadBalancer, obj.root_loadbalancer.id,
                provisioning_status=lb_p_status,
                operating_status=lb_op_status)

    def failed_completion(self, context, obj):
        """
        Sets the provisioning status of the obj to ERROR.  If obj is a
        loadbalancer it will be set to ERROR, otherwise set to ACTIVE. Should
        be called whenever something goes wrong (raised exception) in an
        implementor's BaseManagerMixin methods.

        :param context: neutron_lib context
        :param obj: instance of a
                    neutron_lbaas.services.loadbalancer.data_model
        """
        LOG.debug("Starting failed_completion method after a failed driver "
                  "action.")
        if isinstance(obj, data_models.LoadBalancer):
            LOG.debug("Updating load balancer %s to provisioning_status = "
                      "%s, operating_status = %s.",
                      obj.root_loadbalancer.id, constants.ERROR,
                      lb_const.OFFLINE)
            self.driver.plugin.db.update_status(
                context, models.LoadBalancer, obj.root_loadbalancer.id,
                provisioning_status=constants.ERROR,
                operating_status=lb_const.OFFLINE)
            return
        obj_sa_cls = data_models.DATA_MODEL_TO_SA_MODEL_MAP[obj.__class__]
        LOG.debug("Updating object of type %s with id of %s to "
                  "provisioning_status = %s, operating_status = %s",
                  obj.__class__, obj.id, constants.ERROR,
                  lb_const.OFFLINE)
        self.driver.plugin.db.update_status(
            context, obj_sa_cls, obj.id,
            provisioning_status=constants.ERROR,
            operating_status=lb_const.OFFLINE)
        LOG.debug("Updating load balancer %s to "
                  "provisioning_status = %s", obj.root_loadbalancer.id,
                  constants.ACTIVE)
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
