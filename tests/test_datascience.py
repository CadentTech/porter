import unittest
from unittest import mock

from porter.datascience import (BaseProcessor, BaseModel,
                                WrappedTransformer, WrappedModel)
from tests.utils import (KERAS_MODEL_PATH, KERAS_VALIDATE_PATH,
                         SKLEARN_MODEL_PATH, SKLEARN_VALIDATE_PATH)


class TestBaseModel(unittest.TestCase):
    def test_abc(self):
        class A(BaseModel): pass
        with self.assertRaises(NotImplementedError):
            A().predict(None)


class TestWrappedModel(unittest.TestCase):
    def test_predict(self):
        mock_model = mock.Mock()
        mock_model.predict = lambda x: x+1
        model = WrappedModel(mock_model)
        actual = model.predict(1)
        expected = 2
        self.assertEqual(actual, expected)

    def test_from_file_sklearn(self):
        pass

    def test_from_file_keras(self):
        pass


class TestBaseProcessor(unittest.TestCase):
    def test_abc(self):
        class A(BaseProcessor): pass
        with self.assertRaises(NotImplementedError):
            A().process(None)


class TestWrappedTransformer(unittest.TestCase):
    def test_transform(self):
        class MockTransformer:
            def transform(self, X):
                return X + 1
        processor = WrappedTransformer(MockTransformer())
        actual = processor.process(1)
        expected = 2
        self.assertEqual(actual, expected)


class TestLoadFunctions(unittest.TestCase):
    def test_load_pkl(self):
        pass

    def test_load_h5(self):
        pass

    def test_load_file(self):
        pass


if __name__ == '__main__':
    unittest.main()
