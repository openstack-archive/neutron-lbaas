# Copyright 2014-2016 Rackspace US, Inc.
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
class BarbicanAuth(object):
    @abc.abstractmethod
    def get_barbican_client(self, project_id):
        """Creates a Barbican client object.

        :param project_id: Project ID that the request will be used for
        :return: a Barbican Client object
        :raises Exception: if the client cannot be created
        """
