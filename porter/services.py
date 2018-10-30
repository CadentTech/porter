"""Tools for building RESTful services that exposes machine learning models.

Building and running an app with the tools in this module is as simple as

1. Instantiating `ModelApp`.
2. Instantiating `ServiceConfig` once for each model you wish to add to the
    service.
3. Use the config(s) created in 2. to add models to the app with either
    `ModelApp.add_service()` or `ModelApp.add_services()`.

For example,

    >>> model_app = ModelApp()
    >>> service_config1 = ServiceConfig(...)
    >>> service_config2 = ServiceConfig(...)
    >>> model_app.add_services(service_config1, service_config2)

Now the model app can be run with `model_app.run()` for development, or as an
example of running the app in production `$ gunicorn my_module:model_app`.
"""

import abc
import concurrent.futures
import json
import logging
import warnings

import pandas as pd
import werkzeug.exceptions

from . import __version__ as VERSION
from . import api
from . import config as cf
from . import constants as cn
from . import exceptions as exc
from . import responses as porter_responses

# alias for convenience
_ID = cn.PREDICTION.RESPONSE.KEYS.ID

_logger = logging.getLogger(__name__)


def serve_error_message(error):
    """Return a response with JSON payload describing the most recent
    exception."""
    response = porter_responses.make_error_response(error)
    _logger.exception(response.data)
    return response


def serve_root():
    """Return a helpful description of how to use the app."""

    message = (
        'Send POST requests to /&lt model-name &gt/prediction/'
    )
    return message, 200


class StatefulRoute:
    """Helper class to ensure that classes defining __call__() intended to be
    routed satisfy the flask interface.
    """
    def __new__(cls, *args, **kwargs):
        # flask looks for the __name__ attribute of the routed callable,
        # and each name of a routed object must be unique.
        # Therefore we define a unique name here to meet flask's expectations.
        instance = super().__new__(cls)
        if not hasattr(cls, '_instances'):
            cls._instances = 0
        cls._instances += 1
        instance.__name__ = '%s_%s' % (cls.__name__.lower(), cls._instances)
        return instance


class ServeAlive(StatefulRoute):
    """Class for building stateful liveness routes.

    Args:
        app_state (object): An `AppState` instance containing the state of a
            ModelApp. Instances of this class inspect app_state` when called to
            determine if the app is alive.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, app_state):
        self.app_state = app_state

    def __call__(self):
        """Serve liveness response."""
        self.logger.info(self.app_state.json)
        return porter_responses.make_alive_response(self.app_state.json)


class ServeReady(StatefulRoute):
    """Class for building stateful readiness routes.

    Args:
        app_state (object): An `AppState` instance containing the state of a
            ModelApp. Instances of this class inspect app_state` when called to
            determine if the app is ready.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, app_state):
        self.app_state = app_state

    def __call__(self):
        """Serve readiness response."""
        self.logger.info(self.app_state)
        return porter_responses.make_ready_response(self.app_state.json)


class PredictSchema:
    """
    A simple container that represents a model's schema.

    Args:
        input_features (list of str): A list of the features input to the
            model service. If the service defines a preprocessor these are the
            features expected by the preprocessor.

    Attributes:
        input_columns (list of str): A list of all columns expected in the
            POST request payload.
        input_features (list of str): A list of the features input to the
            model service. If the service defines a preprocessor these are the
            features expected by the preprocessor.
    """
    def __init__(self, *, input_features):
        if input_features is not None:
            self.input_columns = [_ID] + input_features
        else:
            self.input_columns = input_features
        self.input_features = input_features


class AppState:
    """Mutable mapping object containing the state of a `ModelApp`.

    Mutability of this object is a requirement. This is assumed elsewhere in
    the code base, e.g. in `ServeAlive` and `ServeReady` instances.
    """

    def __init__(self):
        super().__init__()
        self._services = {}

    def add_service(self, service):
        if service.id in self._services:
             raise exc.PorterError(f'a service has already been added using id={service.id}')
        self._services[service.id] = service

    @property
    def json(self):
        return {
            cn.HEALTH_CHECK.RESPONSE.KEYS.PORTER_VERSION: VERSION,
            cn.HEALTH_CHECK.RESPONSE.KEYS.DEPLOYED_ON: cn.HEALTH_CHECK.RESPONSE.VALUES.DEPLOYED_ON,
            cn.HEALTH_CHECK.RESPONSE.KEYS.SERVICES: {
                service.id: {
                    cn.HEALTH_CHECK.RESPONSE.KEYS.NAME: service.name,
                    cn.HEALTH_CHECK.RESPONSE.KEYS.MODEL_VERSION: service.version,
                    cn.HEALTH_CHECK.RESPONSE.KEYS.ENDPOINT: service.endpoint,
                    cn.HEALTH_CHECK.RESPONSE.KEYS.META: service.meta,
                    cn.HEALTH_CHECK.RESPONSE.KEYS.STATUS: service.status
                }
                for service in self._services.values()
            }
        }


class BaseService(abc.ABC, StatefulRoute):
    """
    Base container that holds configurations for services that can be added to
    an instance of `ModelApp`.

    Args:
        id (str): A unique ID for the service.

    Attributes:
        id (str): A unique ID for the service.
    """
    _ids = set()

    def __init__(self, *, name, version, meta=None):
        self.name = name
        self.version = version
        self.meta = {} if meta is None else meta
        self.check_meta(self.meta)
        # Assign endpoint and ID last so they can be determined from other
        # instance attributes.
        self.id = self.define_id()
        self.endpoint = self.define_endpoint()
        self.meta = self.update_meta(self.meta)

    def __call__(self):
        """Serve a response to the user."""
        return self.serve()

    @abc.abstractmethod
    def define_endpoint(self):
        """Return the service endpoint derived from instance attributes."""

    @abc.abstractmethod
    def serve(self):
        """Serve a response to the user."""

    @abc.abstractproperty
    def status(self):
        """Return `str` representing the status of the service."""

    def define_id(self):
        return f'{self.name}:{self.version}'

    def check_meta(self, meta):
        """Raise `ValueError` if `meta` contains invalid values, e.g. `meta`
        cannot be converted to JSON properly.

        Subclasses overriding this method should always use super() to call
        this method on the superclass unless they have a good reason not to.
        """
        try:
            # sort_keys=True tests the flask.jsonify implementation
            _ = json.dumps(meta, cls=cf.json_encoder, sort_keys=True)
        except TypeError:
            raise exc.PorterError(
                'Could not jsonify meta data. Make sure that meta data is '
                'valid JSON and that all keys are of the same type.')

    def update_meta(self, meta):
        """Update meta data with instance state if desired and return."""
        return meta

    @property
    def id(self):
        """A unique ID for the instance."""
        return self._id

    @id.setter
    def id(self, value):
        if value in self._ids:
            raise exc.PorterError(
                f'The id={value} has already been used. '
                'This likely means that you tried to instantiate a service '
                'with parameters that were already used.')
        self._ids.add(value)
        self._id = value


class PredictionService(BaseService):
    """
    A simple container that holds all necessary data for an instance of
    `ModelApp` to route a model.

    Args:
        model (object): An object implementing the interface defined by
            `porter.datascience.BaseModel`.
        name (str): The model name. The final routed endpoint will become
            "/<endpoint>/prediction/".
        version (str): The model version.
        preprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the POST
            request data and its output will be passed to `model.predict()`.
            Optional.
        postprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the output of
            `model.predict()` and its return value will be used to populate
            the predictions returned to the user. Optional.
        input_features (list-like or None): A list (or list like object)
            containing the feature names required in the POST data. Will be
            used to validate the POST request if not `None`. Optional.            
        allow_nulls (bool): Are nulls allowed in the POST request data? If
            `False` an error is raised when nulls are found. Optional.
        batch_prediction (bool): Whether or not batch predictions are
            supported or not. If `True` the API will accept an array of objects
            to predict on. If `False` the API will only accept a single object
            per request. Optional.
        additional_checks (callable): Raises `InvalidModelInput` or subclass thereof
            if POST request is invalid.

    Attributes:
        id (str): A unique ID for the model. Composed of `name` and `version`.
        model (object): An object implementing the interface defined by
            `porter.datascience.BaseModel`.
        name (str): The model's name. The final routed endpoint will become
            "/<endpoint>/prediction/".
        version (str): The model version.
        endpoint (str): The endpoint exposing the model predictions.
        preprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the POST
            request data and its output will be passed to `model.predict()`.
            Optional.
        postprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the output of
            `model.predict()` and its return value will be used to populate
            the predictions returned to the user. Optional.
        schema (object): An instance of `porter.services.Schema`.
        allow_nulls (bool): Are nulls allowed in the POST request data? If
            `False` an error is raised when nulls are found. Optional.
        batch_prediction (bool): Whether or not the endpoint supports batch
            predictions or not. If `True` the API will accept an array of
            objects to predict on. If `False` the API will only accept a
            single object per request. Optional.
        additional_checks (callable): Raises `InvalidModelInput` or subclass thereof
            if POST request is invalid.
    """

    # response keys that model meta data cannot override
    reserved_keys = (cn.PREDICTION.RESPONSE.KEYS.MODEL_NAME,
                     cn.PREDICTION.RESPONSE.KEYS.MODEL_VERSION,
                     cn.PREDICTION.RESPONSE.KEYS.PREDICTIONS,
                     cn.PREDICTION.RESPONSE.KEYS.ERROR)

    route_kwargs = {'methods': ['GET', 'POST'], 'strict_slashes': False}

    def __init__(self, *, model, preprocessor=None, postprocessor=None,
                 input_features=None, allow_nulls=False,
                 batch_prediction=False, additional_checks=None, **kwargs):
        self.model = model
        self.preprocessor = preprocessor
        self.postprocessor = postprocessor
        self.schema = PredictSchema(input_features=input_features)
        self.allow_nulls = allow_nulls
        self.batch_prediction = batch_prediction
        if additional_checks is not None and not callable(additional_checks):
            raise exc.PorterError('`additional_checks` must be callable')
        self.additional_checks = additional_checks
        self.validate_input = self.schema.input_columns is not None
        self.preprocess_model_input = self.preprocessor is not None
        self.postprocess_model_output = self.postprocessor is not None
        super().__init__(**kwargs)

    def define_endpoint(self):
        return cn.PREDICTION.ENDPOINT_TEMPLATE.format(model_name=self.name)

    def check_meta(self, meta):
        super().check_meta(meta)
        invalid_keys = [key for key in meta if key in self.reserved_keys]
        if invalid_keys:
            raise exc.PorterError(
                'the following keys are reserved for prediction response payloads '
                f'and cannot be used in `meta`: {invalid_keys}')

    @property
    def status(self):
        return cn.HEALTH_CHECK.RESPONSE.VALUES.STATUS_IS_READY

    def serve(self):
        """Retrive POST request data from flask and return a response
        containing the corresponding predictions.

        Returns:
            object: A `flask` object representing the response to return to
                the user.

        Raises:
            porter.exceptions.PredictionError: Raised whenever an error
                occurs during prediction. The error contains information
                about the model context which a custom error handler can
                use to add to the errors response.
        """
        if api.request_method() == 'GET':
            return 'please send POST requests for predictions'
        try:
            response = self._predict()
        except exc.ModelContextError as err:
            err.update_model_context(model_name=self.name,
                model_version=self.version, model_meta=self.meta)
            raise err
        except Exception as err:
            error = exc.PredictionError('an error occurred during prediction')
            error.update_model_context(
                model_name=self.name, model_version=self.version,
                model_meta=self.meta)
            raise error from err
        return response

    def _predict(self):
        X_input = self.get_post_data()
        if self.validate_input:
            self.check_request(X_input, self.schema.input_columns,
                self.allow_nulls, self.additional_checks)
            X_preprocessed = X_input.loc[:,self.schema.input_features]
        else:
            X_preprocessed = X_input
        if self.preprocess_model_input:
            X_preprocessed = self.preprocessor.process(X_preprocessed)
        preds = self.model.predict(X_preprocessed)
        if self.postprocess_model_output:
            preds = self.postprocessor.process(X_input, X_preprocessed, preds)
        response = self.make_response(X_input, preds)
        return response

    def make_response(self, X, preds):
        return porter_responses.make_prediction_response(
            self.name, self.version, self.meta, X[_ID], preds,
            self.batch_prediction)

    @classmethod
    def check_request(cls, X_input, input_columns, allow_nulls=False, additional_checks=None):
        """Check the POST request data raising an error if a check fails.

        Checks include

        1. `X` contains all columns in `feature_names`.
        2. `X` does not contain nulls (only if allow_nulls == True).

        Args:
            X (`pandas.DataFrame`): A `pandas.DataFrame` created from the POST
                request.
            feature_names (list): All feature names expected in `X`.
            allow_nulls (bool): Whether nulls are allowed in `X`. False by
                default.

        Returns:
            None

        Raises:
            porter.exceptions.RequestContainsNulls: If the input contains nulls
                and `allow_nulls` is False.
            porter.exceptions.RequestMissingFields: If the input is missing
                required fields.
            porter.InvalidModelInput: If user defined `additional_checks` fails.
        """
        cls._default_checks(X_input, input_columns, allow_nulls)
        # Only perform user checks after the standard checks have been passed.
        # This allows the user to assume that all columns are present and there
        # are no nulls present (if allow_nulls is False).
        if additional_checks is not None:
            additional_checks(X_input)

    @staticmethod
    def _default_checks(X, input_columns, allow_nulls):
        # checks that all columns are present and no nulls sent
        # (or missing values)
        try:
            # check for allow_nulls first to avoid computation if possible
            if not allow_nulls and X[input_columns].isnull().any().any():
                null_counts = X[input_columns].isnull().sum()
                null_columns = null_counts[null_counts > 0].index.tolist()
                raise exc.RequestContainsNulls(null_columns)
        except KeyError:
            missing_fields = [c for c in input_columns if not c in X.columns]
            raise exc.RequestMissingFields(missing_fields)

    def get_post_data(self):
        """Return data from the most recent POST request as a `pandas.DataFrame`.

        Returns:
            `pandas.DataFrame`. Each `row` represents a single instance to
            predict on. If `self.batch_prediction` is `False` the `DataFrame`
            will only contain one `row`.

        Raises:
            porter.exceptions.PorterError: If the request data does not
                follow the API format.
        """
        data = api.request_json(force=True)
        if not self.batch_prediction:
            # if API is not supporting batch prediction user's must send
            # a single JSON object.
            if not isinstance(data, dict):
                raise exc.InvalidModelInput(f'input must be a single JSON object')
            # wrap the `dict` in a list to convert to a `DataFrame`
            data = [data]
        elif not isinstance(data, list):
            raise exc.InvalidModelInput(f'input must be an array of objects')
        return pd.DataFrame(data)
 

class MiddlewareService(BaseService):
    """A simple container that holds all necessary data for an instance of
    `ModelApp` to run the middleware for a model.

    Here we define a model's middleware follows.

    1. The middleware is an app that takes a POST request with an array of
        objects as its input. Each object in the array represents a single
        instance for the model to predict on.
    2. The middleware obtains predictions for each object in the input array
        by making a POST request for each object to the underlying model API.
    3. The results from the individual POST requests are concatenated into an
        array and returned to the user.

    Args:
        model_endpoint (str): The URL of the model API.
        max_workers (int): The maximum number of workers to use per POST
            request to concurrently send prediction requests to the model
            API.
    """

    reserved_keys = (
        cn.BATCH_PREDICTION.RESPONSE.KEYS.MODEL_ENDPOINT,
        cn.BATCH_PREDICTION.RESPONSE.KEYS.MAX_WORKERS
    )

    route_kwargs = {'methods': ['POST'], 'strict_slashes': False}

    def __init__(self, *, model_endpoint, max_workers, **kwargs):
        self.model_endpoint = model_endpoint
        self.max_workers = max_workers
        super().__init__(**kwargs)

    def define_id(self):
        return f'{self.name}:middleware:{self.version}'

    def define_endpoint(self):
        return cn.BATCH_PREDICTION.ENDPOINT_TEMPLATE.format(model_name=self.name)

    def check_meta(self, meta):
        super().check_meta(meta)
        invalid_keys = [key for key in meta if key in self.reserved_keys]
        if invalid_keys:
            raise exc.PorterError(
                'the following keys are reserved for middleware response payloads '
                f'and cannot be used in `meta`: {invalid_keys}')

    def update_meta(self, meta):
        meta['model_endpoint'] = self.model_endpoint
        meta['max_workers'] = self.max_workers
        return meta

    @property
    def status(self):
        error = None
        try:
            model_status = api.get(self.model_endpoint).status_code
        except Exception as err:
            error = err
        else:
            if model_status == 200:
                return cn.HEALTH_CHECK.RESPONSE.VALUES.STATUS_IS_READY
            return f'GET {self.model_endpoint} returned {model_status}'
        return f'cannot communicate with {self.model_endpoint}: {error}'

    def serve(self):
        """Serve the bulk predictions"""
        data = self.get_post_data()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(api.post, self.model_endpoint, data=instance) for instance in data]
            results = [future.result().json() for future in concurrent.futures.as_completed(futures)]
        response = porter_responses.make_middleware_response(results)
        return response

    def get_post_data(self):
        data = api.request_json(force=True)
        if not isinstance(data, list):
            raise exc.InvalidModelInput(f'input must be an array of objects')
        return data


class PredictionServiceConfig(PredictionService):
    def __init__(self, *args, **kwargs):
        warnings.warn('PredictionServiceConfig is deprecated. Use PredictionService.')
        super().__init__(*args, **kwargs)


class MiddlewareServiceConfig(MiddlewareService):
    def __init__(self, *args, **kwargs):
        warnings.warn('MiddlewareServiceConfig is deprecated. Use MiddlewareService.')
        super().__init__(*args, **kwargs)


class ModelApp:
    """
    Abstraction used to simplify building REST APIs that expose predictive
    models.

    Essentially this class is a wrapper around an instance of `flask.Flask`.
    """

    def __init__(self):
        self.state = AppState()
        self.app = self._build_app()

    def __call__(self, *args, **kwargs):
        """Return a WSGI interface to the model app."""
        return self.app(*args, **kwargs)

    def add_services(self, *services):
        """Add services to the app from `*services`.

        Args:
            *services (list): List of `porter.services.BaseService` instances
                to add to the model.

        Returns:
            None
        """
        for service in services:
            self.add_service(service)

    def add_service(self, service):
        """Add a service to the app from `service`.

        Args:
            service (object): Instance of `porter.services.BaseService`.

        Returns:
            None

        Raises:
            porter.exceptions.PorterError: If the type of
                `service` is not recognized.
        """
        self.app.route(service.endpoint, **service.route_kwargs)(service)
        self.state.add_service(service)

    def run(self, *args, **kwargs):
        """
        Run the app.

        Args:
            *args: Positional arguments passed on to the wrapped `flask` app.
            **kwargs: Keyword arguments passed on to the wrapped `flask` app.
        """
        self.app.run(*args, **kwargs)

    def _build_app(self):
        """Build and return the `flask` app.

        Any global properties of the app, such as error handling and response
        formatting, are added here.

        Returns:
            An instance of `flask.Flask`.
        """
        app = api.App(__name__)
        # register a custom JSON encoder that handles numpy data types.
        app.json_encoder = cf.json_encoder
        # register error handler for all werkzeug default exceptions
        for error in werkzeug.exceptions.default_exceptions:
            app.register_error_handler(error, serve_error_message)
        app.register_error_handler(exc.PredictionError, serve_error_message)
        # This route that can be used to check if the app is running.
        # Useful for kubernetes/helm integration
        app.route('/', methods=['GET'])(serve_root)
        app.route(cn.LIVENESS.ENDPOINT, methods=['GET'])(ServeAlive(self.state))
        app.route(cn.READINESS.ENDPOINT, methods=['GET'])(ServeReady(self.state))
        return app
