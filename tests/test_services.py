import time
import unittest
from unittest import mock

from werkzeug import exceptions as exc
import numpy as np
import pandas as pd
import porter.responses as porter_responses
from porter import __version__
from porter import constants as cn
from porter.services import (BaseService, ModelApp,
                             PredictionService,
                             StatefulRoute, serve_error_message)
from porter.schemas import openapi


class TestFunctionsUnit(unittest.TestCase):
    @mock.patch('porter.services.porter_responses.api.request_json')
    @mock.patch('porter.services.porter_responses.api.jsonify')
    @mock.patch('porter.services.porter_responses.api.request_id', lambda: 123)
    @mock.patch('porter.services.cf.return_message_on_error', True)
    @mock.patch('porter.services.cf.return_traceback_on_error', True)
    @mock.patch('porter.services.cf.return_user_data_on_error', True)
    @mock.patch('porter.responses.api.get_model_context', mock.MagicMock)
    def test_serve_error_message_status_codes_arbitrary_error(self, mock_flask_request, mock_flask_jsonify):
        # if the current error does not have an error code make sure
        # the response gets a 500
        error = ValueError('an error message')
        actual = serve_error_message(error)
        actual_status_code = 500
        expected_status_code = 500
        self.assertEqual(actual_status_code, expected_status_code)

    @mock.patch('porter.services.porter_responses.api.request_json')
    @mock.patch('porter.services.porter_responses.api.jsonify')
    @mock.patch('porter.services.porter_responses.api.request_id', lambda: 123)
    @mock.patch('porter.services.cf.return_message_on_error', True)
    @mock.patch('porter.services.cf.return_traceback_on_error', True)
    @mock.patch('porter.services.cf.return_user_data_on_error', True)
    @mock.patch('porter.responses.api.get_model_context', mock.MagicMock)
    def test_serve_error_message_status_codes_werkzeug_error(self, mock_flask_request, mock_flask_jsonify):
        # make sure that workzeug error codes get passed on to response
        error = ValueError('an error message')
        error.code = 123
        actual = serve_error_message(error)
        actual_status_code = 123
        expected_status_code = 123
        self.assertEqual(actual_status_code, expected_status_code)


class TestStatefulRoute(unittest.TestCase):
    def test_naming(self):
        class A(StatefulRoute):
            pass
        actual1 = A().__name__
        expected1 = 'a_1'
        actual2 = A().__name__
        expected2 = 'a_2'
        actual3 = A().__name__
        expected3 = 'a_3'
        self.assertEqual(actual1, expected1)
        self.assertEqual(actual2, expected2)
        self.assertEqual(actual3, expected3)


@mock.patch('porter.responses.api.request_id', lambda: 123)
@mock.patch('porter.services.api.request_id', lambda: 123)
class TestPredictionServiceCall(unittest.TestCase):
    """Test the call method of prediction service."""
    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.responses.api')
    @mock.patch('porter.services.api.set_model_context', lambda s: None)
    @mock.patch('porter.services.api.request_method', lambda: 'POST')
    @mock.patch('porter.services.BaseService._ids', set())
    def test_serve_success_batch(self, mock_responses_api, mock_request_json):
        mock_request_json.return_value = [
            {'id': 1, 'feature1': 10, 'feature2': 0},
            {'id': 2, 'feature1': 11, 'feature2': 1},
            {'id': 3, 'feature1': 12, 'feature2': 2},
            {'id': 4, 'feature1': 13, 'feature2': 3},
            {'id': 5, 'feature1': 14, 'feature2': 3},
        ]
        mock_responses_api.jsonify = lambda payload: payload
        mock_model = mock.Mock()
        test_model_name = 'model'
        test_api_version = '1.0.0'
        mock_preprocessor = mock.Mock()
        mock_postprocessor = mock.Mock()

        feature_values = {str(x): x for x in range(5)}
        mock_model.predict = lambda X: X['feature1'] + X['feature2'].map(feature_values) + X['feature3']
        def preprocess(X):
            X['feature2'] = X.feature2.astype(str)
            X['feature3'] = range(len(X))
            return X
        mock_preprocessor.process = preprocess
        def postprocess(X_in, X_pre, preds):
            return preds * 2
        mock_postprocessor.process = postprocess
        prediction_service = PredictionService(
            model=mock_model,
            name=test_model_name,
            api_version=test_api_version,
            meta={'1': '2', '3': '4'},
            preprocessor=mock_preprocessor,
            postprocessor=mock_postprocessor,
            batch_prediction=True,
            additional_checks=None
        )
        mock_responses_api.get_model_context.return_value = prediction_service
        actual = prediction_service()
        expected = {
            'request_id': 123,
            'model_context': {
                'model_name': test_model_name,
                'api_version': test_api_version,
                'model_meta': {
                    '1': '2',
                    '3': '4'
                }
            },
            'predictions': [
                {'id': 1, 'prediction': 20},
                {'id': 2, 'prediction': 26},
                {'id': 3, 'prediction': 32},
                {'id': 4, 'prediction': 38},
                {'id': 5, 'prediction': 42},
            ]
        }
        self.assertEqual(actual, expected)

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.responses.api')
    @mock.patch('porter.services.api.set_model_context', lambda s: None)
    @mock.patch('porter.services.api.request_method', lambda: 'POST')
    @mock.patch('porter.services.BaseService._ids', set())
    def test_serve_success_batch(self, mock_responses_api, mock_request_json):
        mock_request_json.return_value = {'id': 1, 'feature1': 10, 'feature2': 0}
        mock_responses_api.jsonify = lambda payload: payload
        mock_model = mock.Mock()
        test_model_name = 'model'
        test_api_version = '1.0.0'
        mock_preprocessor = mock.Mock()
        mock_postprocessor = mock.Mock()

        feature_values = {str(x): x for x in range(5)}
        mock_model.predict = lambda X: X['feature1'] + X['feature2'].map(feature_values) + X['feature3']
        def preprocess(X):
            X['feature2'] = X.feature2.astype(str)
            X['feature3'] = range(len(X))
            return X
        mock_preprocessor.process = preprocess
        def postprocess(X_in, X_pre, preds):
            return preds * 2
        mock_postprocessor.process = postprocess
        prediction_service = PredictionService(
            model=mock_model,
            name=test_model_name,
            api_version=test_api_version,
            meta={'1': '2', '3': '4'},
            preprocessor=mock_preprocessor,
            postprocessor=mock_postprocessor,
            batch_prediction=False,
            additional_checks=None
        )
        mock_responses_api.get_model_context.return_value = prediction_service
        actual = prediction_service()
        expected = {
            'request_id': 123,
            'model_context': {
                'model_name': test_model_name,
                'api_version': test_api_version,
                'model_meta': {
                    '1': '2',
                    '3': '4'
                }
            },
            'predictions': {'id': 1, 'prediction': 20}
        }
        self.assertEqual(actual, expected)

    @mock.patch('porter.services.PredictionService._predict')
    @mock.patch('porter.services.api')
    @mock.patch('porter.services.PredictionService.check_meta', lambda self, meta: meta)
    @mock.patch('porter.services.PredictionService.update_meta', lambda self, meta: meta)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_serve_fail(self, mock_api, mock__predict):
        mock__predict.side_effect = Exception
        name = 'my-model'
        version = '1.0'
        meta = {}
        with self.assertRaises(exc.InternalServerError) as ctx:
            sp = PredictionService(
                model=mock.Mock(), name=name, api_version=version,
                meta=meta, preprocessor=mock.Mock(), postprocessor=mock.Mock(),
                batch_prediction=mock.Mock(),
                additional_checks=mock.Mock())
            sp()
            # porter.responses.make_error_response counts on these attributes being filled out
            self.assertEqual(ctx.exception.model_name, name)
            self.assertEqual(ctx.exception.api_version, version)
            self.assertEqual(ctx.exception.model_meta, meta)


@mock.patch('porter.responses.api.request_id', lambda: 123)
@mock.patch('porter.services.api.request_id', lambda: 123)
class TestPredictionServicePredict(unittest.TestCase):
    """Test the _predict() method of PredictionService."""
    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    def test_serve_with_processing_batch(self, mock_request_json):
        mock_model = mock.Mock()
        mock_request_json.return_value = [{'id': None}]
        mock_model.predict.return_value = []
        mock_preprocessor = mock.Mock()
        mock_preprocessor.process.return_value = {}
        mock_postprocessor = mock.Mock()
        mock_postprocessor.process.return_value = []
        model_name = api_version = mock.MagicMock()
        prediction_service = PredictionService(
            model=mock_model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=mock_preprocessor,
            postprocessor=mock_postprocessor,
            batch_prediction=True,
            additional_checks=None
        )
        _ = prediction_service._predict()
        mock_preprocessor.process.assert_called()
        mock_postprocessor.process.assert_called()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_serve_no_processing_batch(self, mock_request_json):
        # make sure it doesn't break when processors are None
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_request_json.return_value = [{'id': 1}]
        model.predict.return_value = []
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            additional_checks=None
        )
        _ = prediction_service._predict()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    def test_serve_with_processing_single(self, mock_request_json):
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_request_json.return_value = {'id': None}
        model.predict.return_value = [1]
        mock_preprocessor = mock.Mock()
        mock_preprocessor.process.return_value = {}
        mock_postprocessor = mock.Mock()
        mock_postprocessor.process.return_value = [1]
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=mock_preprocessor,
            postprocessor=mock_postprocessor,
            batch_prediction=False,
            additional_checks=None
        )
        _ = prediction_service._predict()
        mock_preprocessor.process.assert_called()
        mock_postprocessor.process.assert_called()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_serve_no_processing_single(self, mock_request_json):
        # make sure it doesn't break when processors are None
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_request_json.return_value = {'id': None}
        model.predict.return_value = [1]
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=False,
            additional_checks=None
        )
        _ = prediction_service._predict()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test__predict_additional_checks(self, mock_request_json):
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_request_json.return_value = {'id': 1}
        model.predict.return_value = [1]
        mock_additional_checks = mock.Mock()
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=False,
            additional_checks=mock_additional_checks
        )
        _ = prediction_service._predict()
        mock_additional_checks.assert_called()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_get_post_data_batch_prediction(self, mock_request_json):
        mock_model = mock.Mock()
        mock_model.predict.return_value = []
        mock_name = mock_version = mock.MagicMock()

        # Succeed
        mock_request_json.return_value = [{'id': 1}]
        prediction_service = PredictionService(
            model=mock_model,
            name=mock_name,
            api_version=mock_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            additional_checks=None
        )
        _ = prediction_service._predict()

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_get_post_data_instance_prediction(self, mock_request_json):
        mock_model = mock.Mock()
        mock_model.predict.return_value = [1]

        # Succeed
        mock_request_json.return_value = {'id': None}
        prediction_service = PredictionService(
            model=mock_model,
            name=mock.MagicMock(),
            api_version=mock.MagicMock(),
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=False,
            additional_checks=None
        )
        _ = prediction_service._predict()

    @mock.patch('porter.services.BaseService._ids', set())
    def test_constructor(self):
        prediction_service = PredictionService(
            model=None, name='foo', api_version='bar', meta={'1': '2', '3': 4})

    @mock.patch('porter.services.BaseService._ids', set())
    def test_constructor_fail(self):
        with self.assertRaisesRegex(ValueError, '`meta` does not follow the proper schema'):
            with mock.patch('porter.services.cf.json_encoder', spec={'encode.side_effect': TypeError}) as mock_encoder:
                prediction_service = PredictionService(
                    model=None, name='foo', api_version='bar', meta=object())
        with self.assertRaisesRegex(ValueError, '.*callable.*'):
            prediction_service = PredictionService(model=None, additional_checks=1)


@mock.patch('porter.responses.api.request_id', lambda: 123)
@mock.patch('porter.services.api.request_id', lambda: 123)
class TestPredictionServiceSchemas(unittest.TestCase):
    """Test the schema methods of PredictionService."""
    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test__add_feature_schema_instance(self, mock_request_json):
        # this test also implicitly covers BaseService.add_request_schema
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_additional_checks = mock.Mock()
        feature_schema = openapi.Object(properties=dict(x=openapi.Integer()))
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=False,
            feature_schema=feature_schema,
        )
        # check _request_schemas
        self.assertIsInstance(prediction_service._request_schemas['POST'], openapi.Object)
        # check request_schemas
        request_schema = prediction_service.request_schemas['POST']
        self.assertIsInstance(request_schema, openapi.RequestSchema)
        # check that id field was inserted
        self.assertIn('id', request_schema.api_obj.properties)

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test__add_feature_schema_batch(self, mock_request_json):
        # this test also implicitly covers BaseService.add_request_schema
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_additional_checks = mock.Mock()
        feature_schema = openapi.Object(properties=dict(x=openapi.Integer()))
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            feature_schema=feature_schema,
        )
        # check _request_schemas
        self.assertIsInstance(prediction_service._request_schemas['POST'], openapi.Array)
        # check request_schemas
        request_schema = prediction_service.request_schemas['POST']
        self.assertIsInstance(request_schema, openapi.RequestSchema)
        # check that id field was inserted
        self.assertIn('id', request_schema.api_obj.item_type.properties)

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test__add_prediction_schema_instance(self, mock_request_json):
        # this test also implicitly covers BaseService.add_response_schema
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_additional_checks = mock.Mock()
        prediction_schema = openapi.Object(properties=dict(x=openapi.Integer()))
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=False,
            prediction_schema=prediction_schema,
        )
        # check _response_schemas
        self.assertIsInstance(prediction_service._response_schemas['POST', 200], openapi.Object)
        # check for one corresponding element in response_schemas
        n = 0
        for schema in prediction_service.response_schemas['POST']:
            if schema.status_code == 200:
                n += 1
                response_obj = schema.api_obj
        self.assertEqual(n, 1)
        # check properties of relevant response
        self.assertIn('request_id', response_obj.properties)
        self.assertIn('model_context', response_obj.properties)
        self.assertIn('id', response_obj.properties['predictions'].properties)
        self.assertIn('prediction', response_obj.properties['predictions'].properties)

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test__add_prediction_schema_batch(self, mock_request_json):
        # this test also implicitly covers BaseService.add_response_schema
        model = mock.Mock()
        model_name = api_version = mock.MagicMock()
        mock_additional_checks = mock.Mock()
        prediction_schema = openapi.Object(properties=dict(x=openapi.Integer()))
        prediction_service = PredictionService(
            model=model,
            name=model_name,
            api_version=api_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            prediction_schema=prediction_schema,
        )
        # check _response_schemas
        self.assertIsInstance(prediction_service._response_schemas['POST', 200], openapi.Object)
        # check for one corresponding element in response_schemas
        n = 0
        for schema in prediction_service.response_schemas['POST']:
            if schema.status_code == 200:
                n += 1
                response_obj = schema.api_obj
        self.assertEqual(n, 1)
        # check properties of relevant response
        self.assertIn('request_id', response_obj.properties)
        self.assertIn('model_context', response_obj.properties)
        self.assertIsInstance(response_obj.properties['predictions'], openapi.Array)

    @mock.patch('porter.services.api.request_json')
    @mock.patch('porter.services.api.get_model_context', lambda: None)
    @mock.patch('porter.services.BaseService._ids', set())
    def test_get_post_data_validation(self, mock_request_json):
        # this test also implicitly covers BaseService.get_post_data
        mock_model = mock.Mock()
        mock_model.predict.return_value = []
        mock_name = mock_version = mock.MagicMock()
        feature_schema = openapi.Object(properties=dict(x=openapi.Integer()))
        prediction_service = PredictionService(
            model=mock_model,
            name=mock_name,
            api_version=mock_version,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            feature_schema=feature_schema,
            additional_checks=None
        )

        # Succeed
        mock_request_json.return_value = [{'id': 1, 'x': 37}]
        prediction_service.get_post_data()

        # Succeed
        mock_request_json.return_value = [{'id': 1, 'x': 3.7}]
        prediction_service.get_post_data()

        # Fail
        prediction_service = PredictionService(
            model=mock_model,
            name=mock_name,
            api_version=mock_version + 1,
            meta={},
            preprocessor=None,
            postprocessor=None,
            batch_prediction=True,
            feature_schema=feature_schema,
            validate_request_data=True,
            additional_checks=None)
        # TODO: recent changes here, but could make this more specific
        with self.assertRaises(Exception):
            prediction_service.get_post_data()


class TestModelApp(unittest.TestCase):
    @mock.patch('porter.services.ModelApp._build_app')
    @mock.patch('porter.services.ModelApp.add_service')
    def test_add_services(self, mock_add_service, mock__build_app):
        configs = [object(), object(), object()]
        model_app = ModelApp()
        model_app.add_services(configs[0], configs[1], configs[2])
        expected_calls = [mock.call(obj) for obj in configs]
        mock_add_service.assert_has_calls(expected_calls)

    @mock.patch('porter.services.ModelApp._build_app')
    @mock.patch('porter.services.api.App')
    def test_add_service(self, mock_app, mock__build_app):
        class service1:
            id = 'service1'
            endpoint = '/an/endpoint'
            route_kwargs = {'foo': 1, 'bar': 'baz'}
            request_schemas = object()
            response_schemas = object()
            name = 'service1'
        class service2:
            id = 'service2'
            endpoint = '/foobar'
            route_kwargs = {'methods': ['GET', 'POST']}
            request_schemas = object()
            response_schemas = object()
            name = 'service2'
        class service3:
            id = 'service3'
            endpoint = '/supa/dupa'
            route_kwargs = {'methods': ['GET'], 'strict_slashes': True}
            request_schemas = object()
            response_schemas = object()
            name = 'service3'
        model_app = ModelApp()
        model_app._request_schemas = {}
        model_app._response_scheams = {}

        # add the services and validate they were routed with the correct
        # parameters.
        model_app.add_services(service1, service2, service3)
        expected_calls = [
            mock.call('/an/endpoint', foo=1, bar='baz'),
            mock.call()(service1),
            mock.call('/foobar', methods=['GET', 'POST']),
            mock.call()(service2),
            mock.call('/supa/dupa', methods=['GET'], strict_slashes=True),
            mock.call()(service3),
        ]
        model_app.app.route.assert_has_calls(expected_calls)

        # verify that the schemas were correctly registered
        expected_request_schemas = {
            service1.endpoint: service1.request_schemas,
            service2.endpoint: service2.request_schemas,
            service3.endpoint: service3.request_schemas
        }
        self.assertEqual(model_app._request_schemas, expected_request_schemas)

        expected_response_schemas = {
            service1.endpoint: service1.response_schemas,
            service2.endpoint: service2.response_schemas,
            service3.endpoint: service3.response_schemas
        }
        self.assertEqual(model_app._response_schemas, expected_response_schemas)

    @mock.patch('porter.services.ModelApp._build_app')
    @mock.patch('porter.services.api.App')
    def test_add_service_fail(self, mock_app, mock__build_app):
        class service1:
            id = 'service1'
            endpoint = '/an/endpoint'
            route_kwargs = {}
            request_schemas = {}
            response_schemas = {}
            name = 'service1'
        class service2:
            id = 'service1'
            endpoint = '/foobar'
            route_kwargs = {}
            request_schemas = {}
            response_schemas = {}
            name = 'service2'
        model_app = ModelApp()
        model_app.add_service(service1)
        with self.assertRaisesRegex(ValueError, 'service has already been added'):
            model_app.add_service(service2)


class TestBaseService(unittest.TestCase):
    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.BaseService.define_endpoint')
    @mock.patch('porter.services.BaseService.action', None)
    def test_constructor(self, mock_define_endpoint):
        # test ABC
        with self.assertRaisesRegex(TypeError, 'abstract methods'):
            class SC(BaseService):
                def define_endpoint(self):
                    return '/an/endpoint'
            SC()

        class SC(BaseService):
            def define_endpoint(self):
                return '/an/endpoint'
            def serve(self): pass
            def status(self): pass


        with self.assertRaisesRegex(ValueError, '`meta` does not follow the proper schema'):
            with mock.patch('porter.services.cf.json_encoder', spec={'encode.side_effect': TypeError}) as mock_encoder:
                SC(name='foo', api_version='bar', meta=object())
        prediction_service = SC(name='foo', api_version='bar', meta=None)
        self.assertEqual(prediction_service.endpoint, '/an/endpoint')
        # make sure this gets set -- shouldn't raise AttributeError
        prediction_service.id
        # make sure that creating a config with same name and version raises
        # error
        with self.assertRaisesRegex(ValueError, '.*likely means that you tried to instantiate a service.*'):
            prediction_service = SC(name='foo', api_version='bar', meta=None)

    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.api.request_json', lambda: {'foo': 1, 'bar': {'p': 10}})
    @mock.patch('porter.services.api.request_id', lambda: 123)
    @mock.patch('porter.services.BaseService.action', None)
    @mock.patch('porter.services.api.set_model_context', lambda service: None)
    @mock.patch('porter.responses.api.get_model_context', mock.MagicMock(name='Service', api_version='v1', meta={}))
    def test_api_logging_no_exception(self):
        class Service(BaseService):
            def serve(self):
                m = mock.Mock(spec=porter_responses.Response)
                m.jsonify.side_effect = lambda: {'foo': '1', 'p': {10: '10'}}
                return m
            def status(self):
                return 'ready'

        with mock.patch('porter.services.BaseService._logger') as mock__logger:
            service1 = Service(name='name1', api_version='version1', log_api_calls=True)
            served = service1()
            mock__logger.info.assert_called_with(
                'api logging',
                extra={'request_id': 123,
                       'request_data': {'foo': 1, 'bar': {'p': 10}},
                       'response_data': {'foo': '1', 'p': {10: '10'}},
                       'service_class': 'Service',
                       'event': 'api_call'}
                )

        with mock.patch('porter.services.BaseService._logger') as mock__logger:
            service2 = Service(name='name2', api_version='version2', log_api_calls=False)
            service2()
            mock__logger.assert_not_called()

    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.api.request_json', lambda: {'foo': 1, 'bar': {'p': 10}})
    @mock.patch('porter.services.api.request_id', lambda: 123)
    @mock.patch('porter.services.BaseService.action', None)
    @mock.patch('porter.services.api.set_model_context', lambda service: None)
    @mock.patch('porter.responses.api.get_model_context', mock.MagicMock(name='Service', api_version='v1', meta={}))
    def test_api_logging_exception(self):
        class Service(BaseService):
            def serve(self):
                raise Exception('testing')
            def status(self):
                return 'ready'

        with mock.patch('porter.services.BaseService._logger') as mock__logger:
            service1 = Service(name='name1', api_version='version1', log_api_calls=True)
            # unhandled exceptions should always get wrapped as a prediction error
            with self.assertRaisesRegex(exc.InternalServerError, 'Could not serve model results successfully.'):
                service1()
            mock__logger.info.assert_called_with(
                'api logging',
                extra={'request_id': 123,
                       'request_data': {'foo': 1, 'bar': {'p': 10}},
                       'response_data': None,
                       'service_class': 'Service',
                       'event': 'api_call'}
                )

        with mock.patch('porter.services.BaseService._logger') as mock__logger:
            service2 = Service(name='name2', api_version='version2', log_api_calls=False)
            # unhandled exceptions should always get wrapped as a prediction error
            with self.assertRaisesRegex(exc.InternalServerError, 'Could not serve model results successfully.'):
                service2()
            mock__logger.assert_not_called()

    @mock.patch('porter.services.BaseService._logger')
    @mock.patch('porter.api.request_id', lambda: 123)
    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.BaseService.action', None)
    @mock.patch('porter.services.api.set_model_context', lambda service: None)
    @mock.patch('porter.responses.api.get_model_context', mock.MagicMock(name='Service', api_version='v1', meta={}))
    def test_serve_logging_with_exception(self, mock__logger):
        e = Exception('testing')
        class Service(BaseService):
            def define_endpoint(self):
                return '/foo'
            def serve(self):
                raise e
            def status(self):
                return 'ready'

        service = Service(name='name', api_version='version')
        with self.assertRaisesRegex(exc.InternalServerError, 'Could not serve model results successfully.'):
            service()
        mock__logger.exception.assert_called_with(
            e,
            extra={'request_id': 123,
                   'service_class': 'Service',
                   'event': 'exception'})

    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.BaseService.serve', None)
    @mock.patch('porter.services.BaseService.status', None)
    def test_define_endpoint_with_namespace(self):
        class Service(BaseService):
            action = 'foo'
        service = Service(name='my-service', api_version='v11', namespace='/my/namespace')
        expected = '/my/namespace/my-service/v11/foo'
        self.assertEqual(service.endpoint, expected)

    @mock.patch('porter.services.BaseService._ids', set())
    @mock.patch('porter.services.BaseService.serve', None)
    @mock.patch('porter.services.BaseService.status', None)
    def test_define_endpoint_with_namespace(self):
        class Service(BaseService):
            action = 'bar'
        # test without namespace (since it's optional)
        service = Service(name='my-service', api_version='v11')
        expected = '/my-service/v11/bar'
        self.assertEqual(service.endpoint, expected)

    @mock.patch('porter.services.BaseService.serve', None)
    @mock.patch('porter.services.BaseService.status', None)
    def test_define_endpoint_with_bad_namespace(self):
        class Service(BaseService):
            action = 'bar'

        with mock.patch('porter.services.BaseService._ids', set()):
            # no /
            service = Service(name='my-service', api_version='v11', namespace='ns')
            expected = '/ns/my-service/v11/bar'
            self.assertEqual(service.endpoint, expected)

        with mock.patch('porter.services.BaseService._ids', set()):
            # trailing /
            service = Service(name='my-service', api_version='v11', namespace='n/s/')
            expected = '/n/s/my-service/v11/bar'
            self.assertEqual(service.endpoint, expected)

        with mock.patch('porter.services.BaseService._ids', set()):
            # both /
            service = Service(name='my-service', api_version='v11', namespace='/n/s/')
            expected = '/n/s/my-service/v11/bar'
            self.assertEqual(service.endpoint, expected)


if __name__ == '__main__':
    unittest.main()
