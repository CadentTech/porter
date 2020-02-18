"""Definitions of interfaces for data science objects expected by `porter.services`."""

import abc

from porter.loading import load_file
from porter import utils


class BaseModel(abc.ABC):
    """Class defining the model interface required by
        `porter.services.ModelApp.add_service`."""
    @abc.abstractmethod
    def predict(self, X):
        """Return predictions corresponding to the data in `X`."""


class BasePreProcessor(abc.ABC):
    """Class defining the preprocessor interface required by
        `porter.services.ModelApp.add_service`."""
    @abc.abstractmethod
    def process(self, X_input):
        """Process and return `X_input`.

        Args:
            X_input (`pandas.DataFrame`): The raw input from a POST request
                converted to a `pandas.DataFrame`.

        Returns:
            `X_input` processed as desired.
        """


class BasePostProcessor(abc.ABC):
    """Class defining the postprocessor interface required by
        `porter.services.ModelApp.add_service`."""
    @abc.abstractmethod
    def process(self, X_input, X_preprocessed, predictions):
        """Process and return `predictions`.

        Args:
            X_input (`pandas.DataFrame`): The raw input from a POST request
                converted to a `pandas.DataFrame`.
            X_preprocessed: The POST request data with preprocessing applied.
            predictions: The output of an instance of `BaseModel`.

        Returns:
            `predictions` processed as desired.

        Note: `X_input` and `X_preprocessed` are included to provide additional
        context for postprocessing predictions if necessary.
        """


class WrappedModel(BaseModel):
    """A convenience class that exposes a model persisted to disk with the
    `BaseModel` interface.
    """
    def __init__(self, model):
        if not hasattr(model, 'predict'):
            raise TypeError('.predict() method missing for model:\n{}'
                            .format(model))
        elif not callable(model.predict):
            raise TypeError('model.predict() is not callable for model:\n{}'
                            .format(model))
        self.model = model
        super(WrappedModel, self).__init__()

    def predict(self, X):
        return self.model.predict(X)

    @classmethod
    def from_file(cls, path, *args, s3_access_key_id=None,
                  s3_secret_access_key=None, **kwargs):
        model = load_file(path, s3_access_key_id, s3_secret_access_key)
        return cls(model, *args, **kwargs)


class WrappedTransformer(BasePreProcessor):
    """A convenience class that exposes a transformer persisted to disk with
    the `BasePreProcessor` interface.
    """
    def __init__(self, transformer):
        self.transformer = transformer
        super(WrappedTransformer, self).__init__()

    def process(self, X):
        return self.transformer.transform(X)

    @classmethod
    def from_file(cls, path, *args, s3_access_key_id=None,
                  s3_secret_access_key=None, **kwargs):
        transformer = load_file(path, s3_access_key_id, s3_secret_access_key)
        return cls(transformer, *args, **kwargs)
