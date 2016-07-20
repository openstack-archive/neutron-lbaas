# Copyright 2013 OpenStack Foundation.  All rights reserved
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

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class AgentDeviceDriver(object):
    """Abstract device driver that defines the API required by LBaaS agent."""

    def __init__(self, conf, plugin_rpc, process_monitor=None):
        self.conf = conf
        self.plugin_rpc = plugin_rpc
        self.process_monitor = process_monitor

    @abc.abstractproperty
    def loadbalancer(self):
        pass

    @abc.abstractproperty
    def listener(self):
        pass

    @abc.abstractproperty
    def pool(self):
        pass

    @abc.abstractproperty
    def member(self):
        pass

    @abc.abstractproperty
    def healthmonitor(self):
        pass

    @abc.abstractmethod
    def get_name(self):
        """Returns unique name across all LBaaS device drivers."""
        pass

    @abc.abstractmethod
    def deploy_instance(self, loadbalancer):
        """Fully deploys a loadbalancer instance from a given loadbalancer."""
        pass

    @abc.abstractmethod
    def undeploy_instance(self, loadbalancer_id, **kwargs):
        """Fully undeploys the loadbalancer instance."""
        pass

    def remove_orphans(self, known_loadbalancer_ids):
        # Not all drivers will support this
        raise NotImplementedError()


@six.add_metaclass(abc.ABCMeta)
class BaseManager(object):

    def __init__(self, driver):
        self.driver = driver

    @abc.abstractmethod
    def create(self, obj):
        pass

    @abc.abstractmethod
    def update(self, old_obj, obj):
        pass

    @abc.abstractmethod
    def delete(self, obj):
        pass


class BaseLoadBalancerManager(BaseManager):

    @abc.abstractmethod
    def get_stats(self, loadbalancer_id):
        pass


class BaseListenerManager(BaseManager):
    pass


class BasePoolManager(BaseManager):
    pass


class BaseMemberManager(BaseManager):
    pass


class BaseHealthMonitorManager(BaseManager):
    pass
