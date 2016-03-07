# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import inspect

import mock
import testscenarios

from neutron_lbaas.services.loadbalancer import data_models
from neutron_lbaas.tests import base
from neutron_lbaas.tests import tools

load_tests = testscenarios.load_tests_apply_scenarios


class TestBaseDataModel(base.BaseTestCase):

    def _get_fake_model_cls(self, fields_):
        class FakeModel(data_models.BaseDataModel):
            fields = fields_

            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        return FakeModel

    def test_from_dict(self):

        fields_ = ['field1', 'field2']
        dict_ = {field: tools.get_random_string()
                 for field in fields_}

        model_cls = self._get_fake_model_cls(fields_)
        model = model_cls.from_dict(dict_)

        for field in fields_:
            self.assertEqual(dict_[field], getattr(model, field))

    def test_from_dict_filters_by_fields(self):

        fields_ = ['field1', 'field2']
        dict_ = {field: tools.get_random_string()
                 for field in fields_}
        dict_['foo'] = 'bar'

        model_cls = self._get_fake_model_cls(fields_)
        model = model_cls.from_dict(dict_)
        self.assertFalse(hasattr(model, 'foo'))


def _get_models():
    models = []
    for name, obj in inspect.getmembers(data_models):
        if inspect.isclass(obj):
            if issubclass(obj, data_models.BaseDataModel):
                if type(obj) != data_models.BaseDataModel:
                    models.append(obj)
    return models


class TestModels(base.BaseTestCase):

    scenarios = [
        (model.__name__, {'model': model})
        for model in _get_models()
    ]

    @staticmethod
    def _get_iterable_mock(*args, **kwargs):
        m = mock.create_autospec(dict, spec_set=True)

        def _get_empty_iterator(*args, **kwargs):
            return iter([])

        m.__iter__ = _get_empty_iterator
        m.pop = _get_empty_iterator
        return m

    def test_from_dict_filters_by_fields(self):

        dict_ = {field: self._get_iterable_mock()
                 for field in self.model.fields}
        dict_['foo'] = 'bar'

        model = self.model.from_dict(dict_)
        self.assertFalse(hasattr(model, 'foo'))
