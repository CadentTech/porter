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
"""

# TODO: add endpoints to alive/ready

import json

import flask
import numpy as np
import pandas as pd

from . import responses as porter_responses
from .constants import APP, ENDPOINTS, KEYS
from .utils import NumpyEncoder

# alias for convenience
_ID = KEYS.PREDICTION.ID


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


class ServePrediction(StatefulRoute):
    """Class for building stateful prediction routes.

    Instances of this class are intended to be routed to endpoints in a `flask`
    app. E.g.

        >>> app = flask.Flask(__name__)
        >>> serve_prediction = ServePrediction(...)
        >>> app.route('/prediction/', methods=['POST'])(serve_prediction)

    Instances of this class can hold all required state necessary for making
    predictions at runtime and when called will return predictions corresponding
    POST requests sent to the app.

    Initialize an instance of ServePrediction.

    Args:
        model (object): An object implementing the interface defined by
            `porter.datascience.BaseModel`.
        model_id (str): A unique identifier for the model. Returned to the
            user alongside the model predictions.
        preprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the POST
            request data and its output will be passed to `model.predict()`.
        postprocessor (object or None): An object implementing the interface
            defined by `porter.datascience.BaseProcessor`. If not `None`, the
            `.process()` method of this object will be called on the output of
            `model.predict()` and its return value will be used to populate
            the predictions returned to the user.
        schema (object): An instance of `porter.datascience.Schema`. The
            `feature_names` attribute is used to validate the the POST request
            if not `None`.
        allow_nulls (bool): Are nulls allowed in the POST request data? If
            `False` an error is raised when nulls are found.
    """

    def __init__(self, model, model_id, preprocessor, postprocessor, schema,
                 allow_nulls):
        self.model = model
        self.model_id = model_id
        self.preprocessor = preprocessor
        self.postprocessor = postprocessor
        self.schema = schema
        self.allow_nulls = allow_nulls
        self.validate_input = self.schema.input_columns is not None
        self.preprocess_model_input = self.preprocessor is not None
        self.postprocess_model_output = self.postprocessor is not None

    def __call__(self):
        """Retrive POST request data from flask and return a response
        containing the corresponding predictions.

        Returns:
            object: A `flask` object representing the response to return to
                the user.
        """
        data = flask.request.get_json(force=True)
        X = pd.DataFrame(data)
        if self.validate_input:
            self.check_request(X, self.schema.input_columns, self.allow_nulls)
            Xt = X.loc[:,self.schema.input_features]
        else:
            Xt = X
        if self.preprocess_model_input:
            Xt = self.preprocessor.process(Xt)
        preds = self.model.predict(Xt)
        if self.postprocess_model_output:
            preds = self.postprocessor.process(preds)
        response = porter_responses.make_prediction_response(self.model_id, X[_ID], preds)
        return response

    @staticmethod
    def check_request(X, input_columns, allow_nulls=False):
        """Check the POST request data raising an error if a check fails.

        Checks include

        1. `X` contains all columns in `feature_names`.
        2. `X` does not contain nulls (only if allow_nulls == True).

        Args:
            X (pandas.DataFrame): A `pandas.DataFrame` created from the POST
                request.
            feature_names (list): All feature names expected in `X`.
            allow_nulls (bool): Whether nulls are allowed in `X`. False by
                default.

        Returns:
            None

        Raises:
            ValueError: If a given check fails.
        """
        # checks that all columns are present and no nulls sent
        # (or missing values)
        try:
            # check for allow_nulls first to avoid computation if possible
            if not allow_nulls and X[input_columns].isnull().any().any():
                null_counts = X[input_columns].isnull().sum()
                null_columns = null_counts[null_counts > 0].index.tolist()
                raise ValueError(
                    'request payload had null values in the following fields: %s'
                    % null_columns)
        except KeyError:
            missing = [c for c in input_columns if not c in X.columns]
            raise ValueError(
                'request payload is missing the following fields: %s'
                % missing)


def serve_error_message(error):
    """Return a response with JSON payload describing the most recent
    exception."""
    response = porter_responses.make_error_response(error)
    return response


def serve_root():
    """Return a helpful description of how to use the app."""

    message = (
        'Send POST requests to /&lt model-name &gt/prediction/'
    )
    return message, 200


class ServeABTest(StatefulRoute):
    def __init__(self, routes, probs):
        self.routes = routes
        self.probs = probs

    def __call__(self):
        route = np.random.choice(self.routes, p=self.probs)
        return route()


class ServeAlive(StatefulRoute):
    """Class for building stateful liveness routes.

    Args:
        app_state (object): An `AppState` instance containing the state of a
            ModelApp. Instances of this class inspect app_state` when called to
            determine if the app is alive.
    """
    def __init__(self, app_state):
        self.app_state = app_state

    def __call__(self):
        """Serve liveness response."""
        return porter_responses.make_alive_response(self.app_state)


class ServeReady(StatefulRoute):
    """Class for building stateful readiness routes.

    Args:
        app_state (object): An `AppState` instance containing the state of a
            ModelApp. Instances of this class inspect app_state` when called to
            determine if the app is ready.
    """
    def __init__(self, app_state):
        self.app_state = app_state

    def __call__(self):
        """Serve readiness response."""
        return porter_responses.make_ready_response(self.app_state)


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
        self.input_columns = [_ID] + input_features
        self.input_features = input_features


class AppState(dict):
    """Mutable mapping object containing the state of a `ModelApp`.

    Mutability of this object is a requirement. This is assumed elsewhere in
    the code base, e.g. in `ServeAlive` and `ServeReady` instances.

    The nested mapping interface of this class is also a requirement.
    elsewhere in the code base we assume that instances of this class can be
    "jsonified".
    """

    def __init__(self):
        super().__init__([
            (APP.STATE.SERVICES, {})
        ])

    def update_service_status(self, name, status):
        """Update the status of a service."""
        services = self[APP.STATE.SERVICES]
        if services.get(name, None) is None:
            services[name] = {}
        services[name][APP.STATE.STATUS] = status


class BaseServiceConfig:
    """
    Base container that holds configurations for services that can be added to
    an instance of `ModelApp`.

    Args:
        name (str): The service name.

    Attributes:
        name (str): The service name.
    """
    def __init__(self, name):
        self.name = name


class PredictionServiceConfig(BaseServiceConfig):
    """
    A simple container that holds all necessary data for an instance of
    `ModelApp` to route a model.

    Args:
        model (object): An object implementing the interface defined by
            `porter.datascience.BaseModel`.
        model_id (str): A unique identifier for the model. Returned to the
            user alongside the model predictions.
        endpoint (str): Name of the model endpoint. The final routed endpoint
            will become "/<endpoint>/prediction/".
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

    Attributes:
        model (object): An object implementing the interface defined by
            `porter.datascience.BaseModel`.
        model_id (str): A unique identifier for the model. Returned to the
            user alongside the model predictions.
        endpoint (str): Name of the model endpoint. The final routed endpoint
            will become "/<endpoint>/prediction/".
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
    """
    def __init__(self, *, model, model_id, endpoint=None, preprocessor=None,
                 postprocessor=None, input_features=None, allow_nulls=False):
        self.model = model
        self.model_id = model_id
        self.endpoint = model_id if endpoint is None else endpoint
        self.preprocessor = preprocessor
        self.postprocessor = postprocessor
        self.schema = PredictSchema(input_features=input_features)
        self.allow_nulls = allow_nulls
        super().__init__(name=model_id)


class ABTestConfig(BaseServiceConfig):
    def __init__(self, prediction_service_configs, probs, model_id, endpoint):
        self.prediction_service_configs = prediction_service_configs
        assert sum(probs) == 1, 'probs must sum to 1'
        self.probs = probs
        self.model_id = model_id
        self.endpoint = endpoint
        super().__init__(name=model_id)


class ModelApp:
    """
    Abstraction used to simplify building REST APIs that expose predictive
    models.

    Essentially this class is a wrapper around an instance of `flask.Flask`.
    """

    _error_codes = (
        400,  # bad request
        404,  # not found
        405,  # method not allowed
        500,  # internal server error
    )

    def __init__(self):
        self.state = AppState()
        self.app = self._build_app()

    def add_services(self, *service_configs):
        """Add services to the app from `*service_configs`.

        Args:
            *service_configs (list): List of `porter.services.ServiceConfig`
                instances to add to the model.

        Returns:
            None
        """
        for service_config in service_configs:
            self.add_service(service_config)

    def add_service(self, service_config):
        """Add a service to the app from `service_config`.

        Args:
            service_config (object): Instance of `porter.services.ServiceConfig`.

        Returns:
            None

        Raises:
            ValueError: If the type of `service_config` is not recognized.         
        """
        if isinstance(service_config, PredictionServiceConfig):
            self.add_prediction_service(service_config)
        elif isinstance(service_config, ABTestConfig):
            self.add_ab_test_service(service_config)
        else:
            raise ValueError('unkown service type')
        self.update_state(service_config)

    def add_prediction_service(self, service_config):
        """
        Add a model service to the API.

        Args:
            service_config (object): Instance of `porter.services.ServiceConfig`.

        Returns:
            None
        """
        prediction_endpoint = ENDPOINTS.PREDICTION_TEMPLATE.format(
            endpoint=service_config.endpoint)
        serve_prediction = ServePrediction(
            model=service_config.model,
            model_id=service_config.model_id,
            preprocessor=service_config.preprocessor,
            postprocessor=service_config.postprocessor,
            schema=service_config.schema,
            allow_nulls=service_config.allow_nulls)
        route_kwargs = {'methods': ['POST'], 'strict_slashes': False}
        self.app.route(prediction_endpoint, **route_kwargs)(serve_prediction)

    def add_ab_test_service(self, service_config):
        routes = []
        for predict_config in service_config.prediction_service_configs:
            serve_prediction = ServePrediction(
                model=predict_config.model,
                model_id=predict_config.model_id,
                preprocessor=predict_config.preprocessor,
                postprocessor=predict_config.postprocessor,
                schema=predict_config.schema,
                allow_nulls=predict_config.allow_nulls)
            routes.append(serve_prediction)
        ab_endpoint = ENDPOINTS.PREDICTION_TEMPLATE.format(
            endpoint=service_config.endpoint)
        serve_ab_test = ServeABTest(routes, probs=service_config.probs)
        route_kwargs = {'methods': ['POST'], 'strict_slashes': False}
        self.app.route(ab_endpoint, **route_kwargs)(serve_ab_test)

    def update_state(self, service_config):
        self.state.update_service_status(name=service_config.name, status=APP.STATE.READY)

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
        app = flask.Flask(__name__)
        # register a custom JSON encoder that handles numpy data types.
        app.json_encoder = NumpyEncoder
        # register error handlers
        for error in self._error_codes:
            app.register_error_handler(error, serve_error_message)
        # This route that can be used to check if the app is running.
        # Useful for kubernetes/helm integration
        app.route('/', methods=['GET'])(serve_root)
        app.route(ENDPOINTS.LIVENESS, methods=['GET'])(ServeAlive(self.state))
        app.route(ENDPOINTS.READINESS, methods=['GET'])(ServeReady(self.state))
        return app
