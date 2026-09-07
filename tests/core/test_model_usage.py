import pytest

from minicode.core.model import (
    ModelResponse,
    ModelUsage,
)


def test_model_usage_preserves_token_counts() -> None:
    usage = ModelUsage(
        input_tokens=12,
        output_tokens=5,
    )

    assert usage.input_tokens == 12
    assert usage.output_tokens == 5
    assert usage.total_tokens == 17


@pytest.mark.parametrize(
    "input_tokens",
    [
        None,
        "12",
        1.5,
        True,
    ],
)
def test_model_usage_rejects_non_integer_input_tokens(
    input_tokens: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="input_tokens must be an integer",
    ):
        ModelUsage(
            input_tokens=input_tokens,  # type: ignore[arg-type]
            output_tokens=5,
        )


@pytest.mark.parametrize(
    "output_tokens",
    [
        None,
        "5",
        1.5,
        True,
    ],
)
def test_model_usage_rejects_non_integer_output_tokens(
    output_tokens: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="output_tokens must be an integer",
    ):
        ModelUsage(
            input_tokens=12,
            output_tokens=output_tokens,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    (
        "input_tokens",
        "output_tokens",
        "error_message",
    ),
    [
        (
            -1,
            0,
            "input_tokens must not be negative",
        ),
        (
            0,
            -1,
            "output_tokens must not be negative",
        ),
    ],
)
def test_model_usage_rejects_negative_token_counts(
    input_tokens: int,
    output_tokens: int,
    error_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def test_model_response_preserves_usage() -> None:
    usage = ModelUsage(
        input_tokens=12,
        output_tokens=5,
    )

    response = ModelResponse(
        content="Done.",
        usage=usage,
    )

    assert response.usage is usage


@pytest.mark.parametrize(
    "usage",
    [
        {},
        "usage",
        17,
    ],
)
def test_model_response_rejects_invalid_usage(
    usage: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="usage must be a ModelUsage or None",
    ):
        ModelResponse(
            content="Done.",
            usage=usage,  # type: ignore[arg-type]
        )
