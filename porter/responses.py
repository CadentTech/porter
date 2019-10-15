import traceback

from . import __version__ as VERSION
from . import config as cf
from . import constants as cn
from . import exceptions as exc
from . import api


# NOTE: private functions make testing easier as they bypass `flask` methods
# that require a context, e.g. `api.jsonify`


class Response:
    def __init__(self, data, *, service_class=None, status_code=None):
        if isinstance(data, dict):
            self.data = self._init_payload(service_class, data)
        else:
            self.data = data
        self.status_code = status_code

    def jsonify(self):
        jsonified = api.jsonify(self.data)
        if self.status_code is not None:
            jsonified.status_code = self.status_code
        return jsonified

    def _init_payload(self, service_class, data):
        payload = self._init_base_response()
        if service_class is not None:
            payload[cn.PREDICTION_KEYS.MODEL_CONTEXT] = self._init_model_context(service_class)
        payload.update(data)
        return payload

    @staticmethod
    def _init_base_response():
        payload = {}
        if cf.return_request_id:
            payload[cn.BASE_KEYS.REQUEST_ID] = api.request_id()
        return payload

    @staticmethod
    def _init_model_context(service_class):
        model_context = {
            cn.MODEL_CONTEXT_KEYS.MODEL_NAME: service_class.name,
            cn.MODEL_CONTEXT_KEYS.API_VERSION: service_class.api_version,
        }
        model_context[cn.MODEL_CONTEXT_KEYS.MODEL_META] = service_class.meta
        return model_context

_init_model_context = Response._init_model_context


def make_prediction_response(model_service, id_value, prediction):
    payload = {
        cn.PREDICTION_KEYS.PREDICTIONS: {
            cn.PREDICTION_PREDICTIONS_KEYS.ID: id_value,
            cn.PREDICTION_PREDICTIONS_KEYS.PREDICTION: prediction
        }
    }
    return Response(payload, service_class=model_service)


def make_batch_prediction_response(model_service, id_values, predictions):
    payload = {
        cn.PREDICTION_KEYS.PREDICTIONS: [
            {
                cn.PREDICTION_PREDICTIONS_KEYS.ID: id,
                cn.PREDICTION_PREDICTIONS_KEYS.PREDICTION: p
            }
            for id, p in zip(id_values, predictions)
        ]
    }
    return Response(payload, service_class=model_service)


def make_error_response(error):
    payload = {}
    payload[cn.GENERIC_ERROR_KEYS.ERROR] = error_dict = {}

    # all errors should at least return the name
    error_dict[cn.ERROR_BODY_KEYS.NAME] = type(error).__name__

    # include optional attributes

    ## these are "error specific" attributes
    if cf.return_message_on_error:
        # getattr() is used to work around werkzeug's bad implementation of
        # HTTPException (i.e. HTTPException inherits from Exception but exposes a
        # different API, namely Exception.message -> HTTPException.description).
        messages = [error.description] if hasattr(error, 'description') else error.args
        error_dict[cn.ERROR_BODY_KEYS.MESSAGES] = messages

    if cf.return_traceback_on_error:
        error_dict[cn.ERROR_BODY_KEYS.TRACEBACK] = traceback.format_exc()

    if cf.return_user_data_on_error:
        # silent=True -> flask.request.get_json(...) returns None if user did not
        error_dict[cn.ERROR_BODY_KEYS.USER_DATA] = api.request_json(silent=True, force=True)

    return Response(payload, service_class=getattr(error, 'model_service', None), status_code=getattr(error, 'code', 500))


def make_alive_response(app):
    app_state = _build_app_state(app)
    return Response(app_state, status_code=200)


def make_ready_response(app):
    app_state = _build_app_state(app)
    ready = _is_ready(app_state)
    response = Response(app_state, status_code=200 if ready else 503)
    return response


def _is_ready(app_state):
    services = app_state[cn.HEALTH_CHECK_KEYS.SERVICES]
    # app must define services and all services must be ready
    all_services_ready = all(
        svc[cn.HEALTH_CHECK_SERVICES_KEYS.STATUS] is cn.HEALTH_CHECK_VALUES.IS_READY
        for svc in services.values())
    return services and all_services_ready


def _build_app_state(app):
    """Return the app state as a "jsonify-able" object."""
    top_keys = cn.HEALTH_CHECK_KEYS
    svc_keys = cn.HEALTH_CHECK_SERVICES_KEYS
    return {
        top_keys.PORTER_VERSION: VERSION,
        top_keys.DEPLOYED_ON: cn.HEALTH_CHECK_VALUES.DEPLOYED_ON,
        top_keys.APP_META: app.meta,
        top_keys.SERVICES: {
            service.id: {
                svc_keys.MODEL_CONTEXT: _init_model_context(service),
                svc_keys.STATUS: service.status,
                svc_keys.ENDPOINT: service.endpoint,
            }
            for service in app._services
        }
    }
 