import pytest

from minicode.core.model import (
    ModelResponse,
    ModelResponseDone,
    ModelTextDelta,
)


def test_model_text_delta_preserves_text() -> None:
    delta = ModelTextDelta(
        text="MINI",
    )

    assert delta.text == "MINI"


@pytest.mark.parametrize(
    "text",
    [
        None,
        123,
        b"MINI",
    ],
)
def test_model_text_delta_rejects_non_string_text(
    text: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="text must be a string",
    ):
        ModelTextDelta(
            text=text,  # type: ignore[arg-type]
        )


def test_model_text_delta_preserves_whitespace() -> None:
    delta = ModelTextDelta(
        text=" ",
    )

    assert delta.text == " "


def test_model_text_delta_rejects_empty_text() -> None:
    with pytest.raises(
        ValueError,
        match="text must not be empty",
    ):
        ModelTextDelta(
            text="",
        )


def test_model_response_done_preserves_response() -> None:
    response = ModelResponse(
        content="MINICODE_OK",
    )

    event = ModelResponseDone(
        response=response,
    )

    assert event.response is response


@pytest.mark.parametrize(
    "response",
    [
        "MINICODE_OK",
        {},
        None,
    ],
)
def test_model_response_done_rejects_non_model_response(
    response: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="response must be a ModelResponse",
    ):
        ModelResponseDone(
            response=response,  # type: ignore[arg-type]
        )
