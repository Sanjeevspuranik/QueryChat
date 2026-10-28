import httpx
import openai
import pytest

from app.agent.llm import _AdaptiveChatModel, supports_temperature


@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-3.5-turbo", "gpt-5-chat-latest"])
def test_classic_models_get_temperature(model):
    assert supports_temperature(model)
    assert _AdaptiveChatModel(model, "k", 10)._client.temperature == 0


@pytest.mark.parametrize("model", ["o1", "o3-mini", "gpt-5", "gpt-5.6-luna", "gpt-6-luna", "gpt-6-astra", "future-model"])
def test_everything_else_omits_temperature(model):
    assert not supports_temperature(model)
    client = _AdaptiveChatModel(model, "k", 10)._client
    sent = client._get_request_payload([("human", "hi")]).get("temperature")
    assert sent in (None, 1)  # LangChain itself pins o1 to the accepted default of 1


async def test_falls_back_when_api_rejects_temperature():
    """An unlisted classic-looking model that rejects temperature is retried without it."""
    model = _AdaptiveChatModel("gpt-4-weird", "k", 10)
    calls: list[bool] = []

    class Stub:
        def __init__(self, fail: bool) -> None:
            self.fail = fail

        async def ainvoke(self, messages):
            calls.append(self.fail)
            if self.fail:
                response = httpx.Response(400, request=httpx.Request("POST", "http://x"))
                raise openai.BadRequestError(
                    "Unsupported value: 'temperature' does not support 0.0 with this model.",
                    response=response, body=None,
                )
            return "ok"

    model._client = Stub(fail=True)  # type: ignore[assignment]
    model._build = lambda with_temperature: Stub(fail=False)  # type: ignore[method-assign]
    assert await model.ainvoke([("human", "hi")]) == "ok"
    assert calls == [True, False]
    assert await model.ainvoke([("human", "again")]) == "ok"  # stays on the fixed client
    assert calls == [True, False, False]


async def test_other_errors_propagate():
    model = _AdaptiveChatModel("gpt-4o", "k", 10)

    class Boom:
        async def ainvoke(self, messages):
            raise RuntimeError("network down")

    model._client = Boom()  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        await model.ainvoke([("human", "hi")])
