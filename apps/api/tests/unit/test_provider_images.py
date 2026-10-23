"""Images reach each provider inline (base64 bytes), never as fetched URLs."""

import base64

from ezo_api.providers.anthropic_provider import AnthropicProvider
from ezo_api.providers.gemini_provider import GeminiProvider
from ezo_api.providers.openai_provider import OpenAIProvider
from ezo_api.providers.types import ChatMessage, ChatRequest, ImageInput, normalize_turns

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
IMAGE = ImageInput("image/png", PNG)


def _request(*messages: ChatMessage) -> ChatRequest:
    return ChatRequest(model="m", messages=list(messages))


def test_text_only_messages_keep_their_plain_shape():
    params = OpenAIProvider("k", 10, client=object())._params(
        _request(ChatMessage("user", "Salom"))
    )
    assert params["messages"] == [{"role": "user", "content": "Salom"}]


def test_openai_receives_a_data_url_and_the_question():
    params = OpenAIProvider("k", 10, client=object())._params(
        _request(ChatMessage("user", "Bu nima?", (IMAGE,)))
    )
    image, text = params["messages"][0]["content"]
    assert image["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert text == {"type": "text", "text": "Bu nima?"}


def test_anthropic_receives_a_base64_image_block_before_the_text():
    params = AnthropicProvider("k", 10, client=object())._params(
        _request(ChatMessage("user", "Bu nima?", (IMAGE,)))
    )
    image, text = params["messages"][0]["content"]
    assert image["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(PNG).decode(),
    }
    assert text["text"] == "Bu nima?"


def test_gemini_receives_inline_bytes_then_text():
    contents = GeminiProvider("k", 10, client=object())._contents(
        _request(ChatMessage("user", "Bu nima?", (IMAGE,)))
    )
    parts = contents[0].parts
    assert parts[0].inline_data.data == PNG and parts[0].inline_data.mime_type == "image/png"
    assert parts[1].text == "Bu nima?"


def test_normalize_keeps_image_only_turns_and_merges_images():
    turns = normalize_turns(
        [ChatMessage("user", "", (IMAGE,)), ChatMessage("user", "Tushuntir", (IMAGE,))]
    )
    assert len(turns) == 1
    assert turns[0].content == "Tushuntir" and turns[0].images == (IMAGE, IMAGE)
