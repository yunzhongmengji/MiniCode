import asyncio

import pytest

from minicode.core.messages import (
    Message,
    MessageRole,
)
from minicode.core.model import (
    ModelAccessDeniedError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelError,
    ModelProtocolError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelServiceError,
    ModelUsage,
)
from minicode.core.model_metrics import (
    ModelCallRecord,
    ModelErrorKind,
    RecordingModel,
)
from minicode.core.query_loop import (
    QueryLoop,
    StopReason,
)
from minicode.core.tool_calls import (
    ToolCall,
    ToolResult,
)
from minicode.models.scripted import ScriptedModel
from minicode.tools.scripted import (
    ScriptedToolRuntime,
)


def test_model_call_record_preserves_success_metrics() -> None:
    usage = ModelUsage(
        input_tokens=12,
        output_tokens=5,
    )

    record = ModelCallRecord(
        elapsed_seconds=0.25,
        usage=usage,
    )

    assert record.elapsed_seconds == 0.25
    assert record.usage is usage


@pytest.mark.parametrize(
    "elapsed_seconds",
    [
        None,
        "0.25",
        True,
    ],
)
def test_model_call_record_rejects_non_numeric_elapsed_seconds(
    elapsed_seconds: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="elapsed_seconds must be a number",
    ):
        ModelCallRecord(
            elapsed_seconds=elapsed_seconds,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "elapsed_seconds",
    [
        -0.1,
        float("inf"),
        float("-inf"),
        float("nan"),
    ],
)
def test_model_call_record_rejects_invalid_elapsed_seconds(
    elapsed_seconds: float,
) -> None:
    with pytest.raises(
        ValueError,
        match=("elapsed_seconds must be finite and non-negative"),
    ):
        ModelCallRecord(
            elapsed_seconds=elapsed_seconds,
        )


@pytest.mark.parametrize(
    "usage",
    [
        {},
        "usage",
        17,
    ],
)
def test_model_call_record_rejects_invalid_usage(
    usage: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="usage must be a ModelUsage or None",
    ):
        ModelCallRecord(
            elapsed_seconds=0.25,
            usage=usage,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "error_kind",
    [
        {},
        "rate_limit",
        17,
    ],
)
def test_model_call_record_rejects_invalid_error_kind(
    error_kind: object,
) -> None:
    with pytest.raises(
        TypeError,
        match=("error_kind must be a ModelErrorKind or None"),
    ):
        ModelCallRecord(
            elapsed_seconds=0.25,
            error_kind=error_kind,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_recording_model_records_successful_call() -> None:
    usage = ModelUsage(
        input_tokens=12,
        output_tokens=5,
    )
    response = ModelResponse(
        content="Done.",
        usage=usage,
    )
    inner_model = ScriptedModel(
        responses=[
            response,
        ],
    )

    clock_values = iter(
        (
            10.0,
            10.25,
        )
    )

    def clock() -> float:
        return next(clock_values)

    model = RecordingModel(
        model=inner_model,
        clock=clock,
    )
    request = ModelRequest(
        conversation=(),
    )

    result = await model.complete(request)

    assert result is response
    assert inner_model.requests == (request,)
    assert model.records == (
        ModelCallRecord(
            elapsed_seconds=0.25,
            usage=usage,
        ),
    )


@pytest.mark.asyncio
async def test_recording_model_records_each_query_loop_turn() -> None:
    first_usage = ModelUsage(
        input_tokens=10,
        output_tokens=2,
    )
    second_usage = ModelUsage(
        input_tokens=20,
        output_tokens=4,
    )

    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={
            "path": "README.md",
        },
    )
    tool_result = ToolResult(
        call_id="call_001",
        output="README contents.",
    )

    inner_model = ScriptedModel(
        responses=[
            ModelResponse(
                content="I will read the file.",
                tool_calls=(tool_call,),
                usage=first_usage,
            ),
            ModelResponse(
                content="The task is complete.",
                usage=second_usage,
            ),
        ],
    )
    tool_runtime = ScriptedToolRuntime(
        results=[
            tool_result,
        ],
    )

    clock_values = iter(
        (
            10.0,
            10.25,
            20.0,
            20.5,
        )
    )

    def clock() -> float:
        return next(clock_values)

    recording_model = RecordingModel(
        model=inner_model,
        clock=clock,
    )
    loop = QueryLoop(
        model=recording_model,
        tool_runtime=tool_runtime,
        max_turns=2,
    )
    initial_history = (
        Message(
            role=MessageRole.USER,
            content="Read README.md.",
        ),
    )

    result = await loop.run(
        initial_history,
    )

    assert result.stop_reason is StopReason.COMPLETED
    assert result.turns_used == 2
    assert recording_model.records == (
        ModelCallRecord(
            elapsed_seconds=0.25,
            usage=first_usage,
        ),
        ModelCallRecord(
            elapsed_seconds=0.5,
            usage=second_usage,
        ),
    )


@pytest.mark.parametrize(
    (
        "error",
        "expected_error_kind",
    ),
    [
        (
            ModelAuthenticationError("model authentication failed"),
            ModelErrorKind.AUTHENTICATION,
        ),
        (
            ModelRateLimitError("model rate limit exceeded"),
            ModelErrorKind.RATE_LIMIT,
        ),
        (
            ModelConnectionError("model service connection failed"),
            ModelErrorKind.CONNECTION,
        ),
        (
            ModelQuotaExceededError("model free quota exhausted"),
            ModelErrorKind.QUOTA_EXCEEDED,
        ),
        (
            ModelAccessDeniedError("model access denied"),
            ModelErrorKind.ACCESS_DENIED,
        ),
        (
            ModelServiceError("model service request failed"),
            ModelErrorKind.SERVICE,
        ),
        (
            ModelProtocolError("model returned invalid data"),
            ModelErrorKind.PROTOCOL,
        ),
    ],
)
@pytest.mark.asyncio
async def test_recording_model_records_and_reraises_model_failure(
    error: ModelError,
    expected_error_kind: ModelErrorKind,
) -> None:
    class FailingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request
            raise error

    clock_values = iter(
        (
            20.0,
            20.5,
        )
    )

    def clock() -> float:
        return next(clock_values)

    model = RecordingModel(
        model=FailingModel(),
        clock=clock,
    )
    request = ModelRequest(
        conversation=(),
    )

    with pytest.raises(ModelError) as exc_info:
        await model.complete(request)

    assert exc_info.value is error
    assert model.records == (
        ModelCallRecord(
            elapsed_seconds=0.5,
            error_kind=expected_error_kind,
        ),
    )


@pytest.mark.asyncio
async def test_recording_model_records_and_reraises_cancellation() -> None:
    model_started = asyncio.Event()

    class WaitingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request
            model_started.set()

            await asyncio.Event().wait()

            raise AssertionError("unreachable")

    clock_values = iter(
        (
            30.0,
            30.25,
        )
    )

    def clock() -> float:
        return next(clock_values)

    model = RecordingModel(
        model=WaitingModel(),
        clock=clock,
    )
    request = ModelRequest(
        conversation=(),
    )

    task = asyncio.create_task(model.complete(request))

    await model_started.wait()

    task.cancel()

    with pytest.raises(
        asyncio.CancelledError,
    ):
        await task

    assert model.records == (
        ModelCallRecord(
            elapsed_seconds=0.25,
            error_kind=ModelErrorKind.CANCELLED,
        ),
    )


@pytest.mark.asyncio
async def test_recording_model_records_query_loop_timeout_as_cancellation() -> None:
    model_started = asyncio.Event()

    class WaitingModel:
        async def complete(
            self,
            request: ModelRequest,
        ) -> ModelResponse:
            del request
            model_started.set()

            await asyncio.Event().wait()

            raise AssertionError("unreachable")

    clock_values = iter(
        (
            40.0,
            40.25,
        )
    )

    def clock() -> float:
        return next(clock_values)

    recording_model = RecordingModel(
        model=WaitingModel(),
        clock=clock,
    )
    loop = QueryLoop(
        model=recording_model,
        total_timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError):
        await loop.run(())

    assert model_started.is_set()
    assert recording_model.records == (
        ModelCallRecord(
            elapsed_seconds=0.25,
            error_kind=ModelErrorKind.CANCELLED,
        ),
    )
