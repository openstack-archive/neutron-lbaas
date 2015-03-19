#
# Copyright 2014 Brocade Communications Systems, Inc.  All rights reserved.
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
#
# Pattabi Ayyasami (pattabi), Brocade Communications Systems,Inc.
#

from brocade_neutron_lbaas import adx_device_driver_v2 as device_driver

from neutron_lbaas.drivers import driver_base


class BrocadeLoadBalancerDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(BrocadeLoadBalancerDriver, self).__init__(plugin)

        self.load_balancer = BrocadeLoadBalancerManager(self)
        self.listener = BrocadeListenerManager(self)
        self.pool = BrocadePoolManager(self)
        self.member = BrocadeMemberManager(self)
        self.health_monitor = BrocadeHealthMonitorManager(self)
        self.device_driver = device_driver.BrocadeAdxDeviceDriverV2(plugin)


class BrocadeLoadBalancerManager(driver_base.BaseLoadBalancerManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_loadbalancer(obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_loadbalancer(obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_loadbalancer(obj)
        except Exception:
            # Ignore the exception
            pass

        self.successful_completion(context, obj, delete=True)

    def refresh(self, context, lb_obj):
        # This is intended to trigger the backend to check and repair
        # the state of this load balancer and all of its dependent objects
        self.driver.device_driver.refresh(lb_obj)

    def stats(self, context, lb_obj):
        return self.driver.device_driver.stats(lb_obj)


class BrocadeListenerManager(driver_base.BaseListenerManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_listener(obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_listener(obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_listener(obj)
        except Exception:
            # Ignore the exception
            pass

        self.successful_completion(context, obj, delete=True)


class BrocadePoolManager(driver_base.BasePoolManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_pool(obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_pool(obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_pool(obj)
        except Exception:
            # Ignore the exception
            pass

        self.successful_completion(context, obj, delete=True)


class BrocadeMemberManager(driver_base.BaseMemberManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_member(obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_member(obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_member(obj)
        except Exception:
            # Ignore the exception
            pass

        self.successful_completion(context, obj, delete=True)


class BrocadeHealthMonitorManager(driver_base.BaseHealthMonitorManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_healthmonitor(obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_healthmonitor(obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_healthmonitor(obj)
        except Exception:
            # Ignore the exception
            pass

        self.successful_completion(context, obj, delete=True)
