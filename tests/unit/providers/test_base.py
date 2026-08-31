import pytest

from jaime.providers.base import AIProvider


class TestAIProvider:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            AIProvider()

    def test_subclass_must_implement_generate(self):
        class IncompleteProvider(AIProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_concrete_subclass_works(self):
        class ConcreteProvider(AIProvider):
            def generate(self, prompt: str) -> str:
                return "response"

        provider = ConcreteProvider()
        assert provider.generate("hello") == "response"
