from functools import partial

import flask
import pandas as pd
from werkzeug.exceptions import BadRequest

from ipa.responses import make_prediction_response, make_error_response
from ipa import utils


_ID_KEY = 'id'


def check_request(X, feature_names):
    required_keys = [_ID_KEY]
    required_keys.extend(feature_names)
    # checks that all columns are present and no nulls sent
    # (or missing values)
    try:
        if X[required_keys].isnull().any().any():
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

def serve_prediction(model, feature_engineer):
    data = flask.request.get_json(force=True)
    X = pd.DataFrame(data)
    try:
        check_request(X, feature_engineer.get_feature_names())
    except ValueError:
        raise BadRequest()
    X_tf = feature_engineer.transform(X)
    model_prediction = model.predict(X_tf)
    response = make_prediction_response(model.id, X[_ID_KEY], model_prediction)
    return response

def serve_error_message(error):
    """Return a response with JSON payload describing the most recent exception."""
    response = make_error_response(error)
    return response


class ModelService:
    _url_prediction_format = '/{model_name}/prediction/'
    _error_codes = (
        400,  # bad request
        404,  # not found
        405,  # method not allowed
        500   # internal server error
    )

    def __init__(self):
        self.app = self._build_app()

    def add_model(self, model, feature_engineer):
        model_url = self._make_model_url(model.name)
        fn = self._make_model_prediction_fn(model, feature_engineer)
        self.app.route(model_url, methods=['POST'])(fn)

    def _build_app(self):
        app = flask.Flask(__name__)
        app.json_encoder = utils.NumpyEncoder
        for error in self._error_codes:
            app.register_error_handler(error, serve_error_message)
        return app

    def _make_model_url(self, model_name):
        return self._url_prediction_format.format(model_name=model_name)

    def _make_model_prediction_fn(self, model, feature_engineer=None):
        partial_fn = partial(serve_prediction, model=model, feature_engineer=feature_engineer)
        # mimic function API
        partial_fn.__name__ = '{}_prediction'.format(model.name.replace('-', '_'))
        return partial_fn
