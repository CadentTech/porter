"""
This code demonstrates how to expose a pickled sklearn model as a REST
API via porter.

The model predictions can be obtained by sending POST requests with a payload
such as


```javascript
[
    {
        "id": 101,
        "feature1": "foo",
        "feature2": "bar",
        "feature3": 1.0
    }
]
```

to the endpoint `/supa-dupa-model/v1/prediction/`. The corresponding output
has the format

```javascript
[
    "model_context": {
        "model_name": "supa-dupa-model-v0",
        "api_version": "v1,
        "model_meta": {}
    }
    "predicitons": [
        {"id": 101, "prediction": 1001.01}
    ]
]
```
"""

import os

from porter.datascience import WrappedModel, WrappedTransformer, BasePostProcessor
from porter.services import ModelApp, PredictionService
from porter.schemas import Object, Number

# Uncomment this and enter a directory with "preprocessor.pkl" and "model.h5"
# file to make this example working.
# 
# model_directory = ''

PREPROCESSOR_PATH = os.path.join(f'{model_directory}', 'preprocessor.pkl')
MODEL_PATH = os.path.join(f'{model_directory}', 'model.h5')

# define the expected input schema so the model can validate the POST
# request input
feature_schema = Object(
    properties={
        'feature1': Number(),
        'feature2': Number(),
        'column3': Number(),
    }
)

# Define a preprocessor, model and postprocessor for transforming the
# POST request data, predicting and transforming the model's predictions.
# Both processor instances are optional.
#
# For convenience we can load pickled `sklearn` objects as the preprocessor
# and model.
preprocessor = WrappedTransformer.from_file(path=PREPROCESSOR_PATH)
model = WrappedModel.from_file(path=MODEL_PATH)

class Postprocessor(BasePostProcessor):
    def process(self, X_input, X_preprocessed, predictions):
        # keras model returns an array with shape (n observations, 1)
        return predictions.reshape(-1)

# the service config contains everything needed for `model_app` to add a route
# for predictions when `model_app.add_service` is called.
prediction_service = PredictionService(
    model=model,                    # The value of model.predict() is
                                    # returned to the client.
                                    # Required.
                                    #
    name='supa-dupa-model',         # Name of the model. This determines
                                    # the route. E.g. send POST requests
                                    # for this model to
                                    #   host:port/supa-dupa-model/prediction/
                                    # Required.
                                    #
    api_version='v1',               # The version of the model. Returned
                                    # to client in the prediction response.
                                    # Required.
                                    #
    preprocessor=preprocessor,      # preprocessor.process() is
                                    # called on the POST request data
                                    # before predicting. Optional.
                                    #
    postprocessor=Postprocessor(),  # postprocessor.process() is
                                    # called on the model's predictions before
                                    # returning to user. Optional.
                                    #
    feature_schema=feature_schema,  # The input schema is used to validate
                                    # the payload of the POST request.
                                    # Optional.
    validate_request_data=True,     # Whether to validate the request data.
                                    #
    batch_prediction=True           # Whether the API will accept an array of
                                    # JSON objects to predict on or a single
                                    # JSON object only. 
)

# The model app is simply a wrapper around the `flask.Flask` object.
model_app = ModelApp([prediction_service])



if __name__ == '__main__':
    # you can run this with `gunicorn app:model_app`, or
    # simply execute this script with Python and send POST requests
    # to localhost:8000/supa-dupa-model/prediction/
    model_app.run(port=8000)
