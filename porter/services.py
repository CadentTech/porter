from functools import partial

import flask
import pandas as pd
from werkzeug.exceptions import BadRequest

from porter.responses import make_prediction_response, make_error_response
from porter import utils


_ID_KEY = 'id'


def check_request(X, feature_names, allow_nulls=False):
    required_keys = [_ID_KEY]
    required_keys.extend(feature_names)
    # checks that all columns are present and no nulls sent
    # (or missing values)
    try:
        # check for allow_nulls first to avoid computation if possible
        if not allow_nulls and X[required_keys].isnull().any().any():
            null_counts = X[required_keys].isnull().sum()
            null_columns = null_counts[null_counts > 0].index.tolist()
            raise ValueError(
                'request payload had null values in the following fields: %s'
                % null_columns)
    except KeyError:
        missing = [c for c in required_keys if not c in X.columns]
        raise ValueError(
            'request payload is missing the following fields: %s'
            % missing)

def serve_prediction(model, model_id, feature_engineer, input_schema, validate_input,
                     allow_nulls):
    data = flask.request.get_json(force=True)
    X = pd.DataFrame(data)
    if validate_input:
        check_request(X, input_schema.keys(), allow_nulls)
    X_tf = X if feature_engineer is None else feature_engineer.transform(X)
    model_prediction = model.predict(X_tf)
    response = make_prediction_response(model_id, X[_ID_KEY], model_prediction)
    return response

def serve_error_message(error):
    """Return a response with JSON payload describing the most recent exception."""
    response = make_error_response(error)
    return response

def serve_alive():
    message = (
        "I'm alive.<br>"
        'Send POST requests to /&lt model-name &gt/prediction/'
    )
    return message, 200


class ServiceConfig:
    def __init__(self, model, model_id, endpoint, feature_engineer=None,
                 input_schema=None, validate_input=False, allow_nulls=False):
        self.model = model
        self.endpoint = endpoint
        self.model_id = model_id
        self.feature_engineer = feature_engineer
        self.input_schema = input_schema
        if validate_input and not self.input_schema:
            raise ValueError('input_schema is required when validate_input=True')
        self.validate_input = validate_input
        self.allow_nulls = allow_nulls


class ModelApp:
    _url_prediction_format = '/{endpoint}/prediction/'
    _error_codes = (
        400,  # bad request
        404,  # not found
        405,  # method not allowed
        500   # internal server error
    )

    def __init__(self):
        self.app = self._build_app()

    def add_service(self, service_config):
        model_url = self._make_model_url(service_config)
        fn = self._make_prediction_fn(service_config)
        self.app.route(model_url, methods=['POST'])(fn)  # calling flask route decorator directly

    def _build_app(self):
        app = flask.Flask(__name__)
        # register a custom JSON encoder that handles numpy data types.
        app.json_encoder = utils.NumpyEncoder
        # register error handlers
        for error in self._error_codes:
            app.register_error_handler(error, serve_error_message)
        # create a route that can be used to check if the app is running
        # usefule for kubernetes/helm integration
        app.route('/alive/', methods=['GET'])(serve_alive)
        return app

    def _make_model_url(self, service_config):
        return self._url_prediction_format.format(endpoint=service_config.endpoint)

    def _make_prediction_fn(self, service_config):
        cf = service_config  # just an alias for convenience
        fn = partial(serve_prediction, model=cf.model, model_id=cf.model_id,
            feature_engineer=cf.feature_engineer, input_schema=cf.input_schema,
            validate_input=cf.validate_input, allow_nulls=cf.allow_nulls)
        # mimic function API - assumed in flask implementation
        fn.__name__ = '{}_prediction'.format(cf.endpoint.replace('-', '_'))
        return fn
