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


class BaseProcessor(abc.ABC):
    """Class defining the [pre|post]processor interface required by
        `porter.services.ModelApp.add_service`."""
    @abc.abstractmethod
    def process(self, X):
        """Process and return `X`."""


class WrappedModel(BaseModel):
    """A convenience class that exposes a model persisted to disk with the
    `BaseModel` interface.
    """
    def __init__(self, model):
        self.model = model
        super(WrappedModel, self).__init__()

    def predict(self, X):
        return self.model.predict(X)

    @classmethod
    def from_file(cls, path, *args, s3_access_key_id=None,
                  s3_secret_access_key=None, **kwargs):
        model = load_file(path, s3_access_key_id, s3_secret_access_key)
        return cls(model, *args, **kwargs)


class WrappedTransformer(BaseProcessor):
    """A convenience class that exposes a transformer persisted to disk with
    the `BaseProcessor` interface.
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
