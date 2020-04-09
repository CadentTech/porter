"""Exceptions that can be raised by ``porter``."""

class PorterError(Exception):
    """Base Exception class for errors raised by ``porter``."""


class ModelContextError(PorterError):
    """Base Exception class for errors that happen with a model context."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_service = None

    # users are not meant to call this - method simply exists to put the
    # responsibility on porter to properly set these values which pass
    # through to error responses
    def update_model_context(self, model_service):
        self.model_service = model_service


class BadRequest(ModelContextError):
    code = 400


class InvalidModelInput(ModelContextError):
    """Exception class to raise when the POST JSON is not valid for
    predicting.
    """
    code = 422


class PredictionError(ModelContextError):
    """Exception raised when an error occurs during prediction."""
    code = 500
