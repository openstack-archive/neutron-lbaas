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

from functools import wraps

from neutron_lib import context as ncontext
from oslo_utils import excutils

from neutron_lbaas.common import exceptions
from neutron_lbaas.db.loadbalancer import models
from neutron_lbaas.drivers import driver_mixins
from neutron_lbaas.services.loadbalancer import constants


class NotImplementedManager(object):
    """Helper class to make any subclass of LoadBalancerBaseDriver explode if
    it is missing any of the required object managers.
    """

    def create(self, context, obj):
        raise NotImplementedError()

    def update(self, context, old_obj, obj):
        raise NotImplementedError()

    def delete(self, context, obj):
        raise NotImplementedError()


class LoadBalancerBaseDriver(object):
    """LBaaSv2 object model drivers should subclass LoadBalancerBaseDriver,
    and initialize the following manager classes to create, update, and delete
    the various load balancer objects.
    """

    model_map = {constants.LOADBALANCER_EVENT: models.LoadBalancer,
                 constants.LISTENER_EVENT: models.Listener,
                 constants.POOL_EVENT: models.PoolV2,
                 constants.MEMBER_EVENT: models.MemberV2}

    load_balancer = NotImplementedManager()
    listener = NotImplementedManager()
    pool = NotImplementedManager()
    member = NotImplementedManager()
    health_monitor = NotImplementedManager()
    l7policy = NotImplementedManager()
    l7rule = NotImplementedManager()

    def __init__(self, plugin):
        self.plugin = plugin

    def handle_streamed_event(self, container):
        if container.info_type not in LoadBalancerBaseDriver.model_map:
            if container.info_type == constants.LOADBALANCER_STATS_EVENT:
                context = ncontext.get_admin_context()
                self.plugin.db.update_loadbalancer_stats(
                    context, container.info_id, container.info_payload)
            elif container.info_type == constants.LISTENER_STATS_EVENT:
                return
            else:
                exc = exceptions.ModelMapException(
                    target_name=container.info_type)
                raise exc
        else:
            model_class = LoadBalancerBaseDriver.model_map[
                container.info_type]
            context = ncontext.get_admin_context()
            self.plugin.db.update_status(context, model_class,
                                         container.info_id,
                                         **container.info_payload)


class BaseLoadBalancerManager(driver_mixins.BaseRefreshMixin,
                              driver_mixins.BaseStatsMixin,
                              driver_mixins.BaseManagerMixin):
    model_class = models.LoadBalancer

    @property
    def allows_create_graph(self):
        """
        Can this driver create a load balancer graph in one call.

        Return True if this driver has the capability to create a load balancer
        and any of its children in one driver call.  If this returns True and
        the user requests the creation of a load balancer graph, then the
        create_graph method will be called to create the load balancer.
        """
        return False

    @property
    def allows_healthmonitor_thresholds(self):
        """Does this driver support thresholds for health monitors"""
        return False

    @property
    def allocates_vip(self):
        """Does this driver need to allocate its own virtual IPs"""
        return False

    def create_and_allocate_vip(self, context, obj):
        """Create the load balancer and allocate a VIP

        If this method is implemented AND allocates_vip returns True, then
        this method will be called instead of the create method.  Any driver
        that implements this method is responsible for allocating a virtual IP
        and updating at least the vip_address attribute in the loadbalancer
        database table.
        """
        raise NotImplementedError

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_loadbalancer


class BaseListenerManager(driver_mixins.BaseManagerMixin):
    model_class = models.Listener

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_listener


class BasePoolManager(driver_mixins.BaseManagerMixin):
    model_class = models.PoolV2

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_pool


class BaseMemberManager(driver_mixins.BaseManagerMixin):
    model_class = models.MemberV2

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_member


class BaseHealthMonitorManager(driver_mixins.BaseManagerMixin):
    model_class = models.HealthMonitorV2

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_healthmonitor


class BaseL7PolicyManager(driver_mixins.BaseManagerMixin):
    model_class = models.L7Policy

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_l7policy


class BaseL7RuleManager(driver_mixins.BaseManagerMixin):
    model_class = models.L7Rule

    @property
    def db_delete_method(self):
        return self.driver.plugin.db.delete_l7policy_rule


# A decorator for wrapping driver operations, which will automatically
# set the neutron object's status based on whether it sees an exception

def driver_op(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        d = (func.__name__ == 'delete')
        lb_create = ((func.__name__ == 'create') and
                     isinstance(args[0], BaseLoadBalancerManager))
        try:
            r = func(*args, **kwargs)
            args[0].successful_completion(
                args[1], args[2], delete=d, lb_create=lb_create)
            return r
        except Exception:
            with excutils.save_and_reraise_exception():
                args[0].failed_completion(args[1], args[2])
    return func_wrapper
