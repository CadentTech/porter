class KEYS:
    """Container for key names of JSON objects for app input/output."""

    class PREDICTION:
        """Keys for requests received/sent from /<model>/prediction.

        Attributes:
            MODEL_ID: Model ID key.
            PREDICTIONS: Array of predictions key.
            ID: Unique record ID key.
            PREDICTION: Prediction for a given ID key.
        """
        MODEL_ID = 'model_id'
        ID = 'id'
        PREDICTIONS = 'predictions'
        PREDICTION = 'prediction'

    class ERROR:
        """Keys for for error responses.

        Attributes:
            ERROR: Name of error key.
            MESSAGE: Error message key.
            TRACEBACK: Error traceback key.
        """
        ERROR = 'error'
        MESSAGE = 'message'
        TRACEBACK = 'traceback'


class ENDPOINTS:
    PREDICTION_TEMPLATE = '/{endpoint}/prediction'
    LIVENESS = '/-/alive'
    READINESS = '/-/ready'
