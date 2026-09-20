import pytest

from minicode.core.checkpoints import InMemoryCheckpointStore
from minicode.core.context_editing import plan_context_editing
from minicode.core.context_profile import profile_context_projection
from minicode.core.context_projection import (
    BudgetedToolResultProjector,
    IdentityModelContextProjector,
    ToolResultReferenceProjector,
    describe_context_projector,
)
from minicode.core.context_retrieval import (
    DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
)
from minicode.core.events import InMemoryEventLedger
from minicode.core.messages import Message, MessageRole
from minicode.core.model import ModelRequest, ModelResponse
from minicode.core.query_loop import QueryLoop
from minicode.core.tool_calls import ToolCall, ToolResult
from minicode.models.scripted import ScriptedModel
from minicode.tools.read_tool_result import ReadToolResultArguments
from minicode.tools.scripted import ScriptedToolRuntime
from minicode.tools.spec import ToolSpec

_READ_TOOL_RESULT_SPEC = ToolSpec(
    name="read_tool_result",
    description=(
        "Read the exact original output of an earlier tool call in the current run. "
        "This does not execute the earlier tool again."
    ),
    arguments_type=ReadToolResultArguments,
)


def _reference_projector(
    *,
    max_inline_output_bytes: int,
    protected_recent_tool_result_batches: int = 1,
    max_retrievable_output_bytes: int = DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
) -> ToolResultReferenceProjector:
    return ToolResultReferenceProjector(
        max_inline_output_bytes=max_inline_output_bytes,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        protected_recent_tool_result_batches=(protected_recent_tool_result_batches),
        max_retrievable_output_bytes=max_retrievable_output_bytes,
    )


@pytest.mark.asyncio
async def test_identity_projector_preserves_request() -> None:
    request = ModelRequest(
        conversation=(
            Message(
                role=MessageRole.USER,
                content="Inspect the project.",
            ),
        )
    )

    projected = await IdentityModelContextProjector().project(request)

    assert projected is request


def test_projector_configuration_describes_identity_behavior() -> None:
    configuration = describe_context_projector(IdentityModelContextProjector())

    assert configuration.to_payload() == {
        "configuration_schema_version": 2,
        "strategy": "identity",
        "max_inline_tool_result_bytes": None,
        "minimum_net_savings_bytes": None,
        "retrieval_tool_loading": None,
    }


def test_projector_configuration_describes_adaptive_reference_behavior() -> None:
    configuration = describe_context_projector(
        _reference_projector(max_inline_output_bytes=100)
    )

    assert configuration.to_payload() == {
        "configuration_schema_version": 2,
        "strategy": "tool_result_reference",
        "max_inline_tool_result_bytes": 100,
        "minimum_net_savings_bytes": 1,
        "retrieval_tool_loading": "on_reference",
    }


@pytest.mark.asyncio
async def test_budgeted_projector_materializes_the_exact_planned_request() -> None:
    first_result = ToolResult(call_id="call_first", output="a" * 2_500)
    second_result = ToolResult(call_id="call_second", output="b" * 2_500)
    latest_result = ToolResult(call_id="call_latest", output="latest evidence")
    request = ModelRequest(
        conversation=(
            ToolCall(call_id="call_first", name="read_file", arguments={}),
            first_result,
            Message(role=MessageRole.ASSISTANT, content="Read another file."),
            ToolCall(call_id="call_second", name="read_file", arguments={}),
            second_result,
            Message(role=MessageRole.ASSISTANT, content="Check the latest file."),
            ToolCall(call_id="call_latest", name="read_file", arguments={}),
            latest_result,
        ),
    )
    original_bytes = profile_context_projection(request, request).total_bytes_before
    budget = original_bytes - 1_000
    plan = plan_context_editing(
        request,
        max_request_bytes=budget,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )
    projector = BudgetedToolResultProjector(
        max_request_bytes=budget,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    projected = await projector.project(request)
    profile = profile_context_projection(request, projected)

    assert plan.selected_call_ids == ("call_first",)
    assert profile.total_bytes_after == plan.planned_request_bytes
    assert profile.changed_tool_result_count == len(plan.selected_call_ids)
    assert projected.conversation[1] != first_result
    assert projected.conversation[4] is second_result
    assert projected.conversation[-1] is latest_result
    assert projected.tool_specs == (_READ_TOOL_RESULT_SPEC,)
    assert request.conversation[1] is first_result
    assert request.tool_specs == ()


@pytest.mark.asyncio
async def test_budgeted_projector_returns_same_request_when_budget_is_satisfied() -> (
    None
):
    request = ModelRequest(
        conversation=(Message(role=MessageRole.USER, content="Inspect it."),),
    )
    budget = profile_context_projection(request, request).total_bytes_before
    projector = BudgetedToolResultProjector(
        max_request_bytes=budget,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    projected = await projector.project(request)

    assert projected is request


def test_projector_configuration_describes_budgeted_behavior() -> None:
    projector = BudgetedToolResultProjector(
        max_request_bytes=1_000,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
    )

    configuration = describe_context_projector(projector)

    assert configuration is projector.configuration
    assert configuration.to_payload()["configuration_schema_version"] == 3


def test_budgeted_projector_exposes_complete_experimental_configuration() -> None:
    projector = BudgetedToolResultProjector(
        max_request_bytes=120_000,
        retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        protected_recent_batch_count=2,
        excluded_tool_names=("run_tests", "git_diff"),
        max_retrievable_output_bytes=40_000,
        minimum_net_savings_bytes=512,
    )

    assert projector.configuration.to_payload() == {
        "configuration_schema_version": 3,
        "strategy": "budgeted_tool_result_reference",
        "max_request_bytes": 120_000,
        "protected_recent_batch_count": 2,
        "minimum_net_savings_bytes": 512,
        "excluded_tool_names": ["git_diff", "run_tests"],
        "max_retrievable_output_bytes": 40_000,
        "retrieval_tool_loading": "on_reference",
    }


@pytest.mark.parametrize(
    ("max_request_bytes", "error_type", "message"),
    (
        (True, TypeError, "max_request_bytes must be an integer"),
        (0, ValueError, "max_request_bytes must be greater than zero"),
    ),
)
def test_budgeted_projector_rejects_invalid_request_budget(
    max_request_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        BudgetedToolResultProjector(
            max_request_bytes=max_request_bytes,  # type: ignore[arg-type]
            retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        )


@pytest.mark.asyncio
async def test_reference_projector_compacts_only_eligible_large_result() -> None:
    older_output = "旧内容" * 100
    latest_output = "最新内容" * 100
    older_result = ToolResult(call_id="call_old", output=older_output)
    latest_result = ToolResult(call_id="call_latest", output=latest_output)
    request = ModelRequest(
        conversation=(
            ToolCall(
                call_id="call_old",
                name="read_file",
                arguments={"path": "old.py"},
            ),
            older_result,
            Message(role=MessageRole.ASSISTANT, content="Now inspect latest.py."),
            ToolCall(
                call_id="call_latest",
                name="read_file",
                arguments={"path": "latest.py"},
            ),
            latest_result,
        ),
        instructions=("Keep changes focused.",),
    )

    projected = await _reference_projector(max_inline_output_bytes=100).project(request)

    assert projected is not request
    assert projected.conversation[1] == ToolResult(
        call_id="call_old",
        output=(
            '{"call_id":"call_old",'
            '"kind":"historical_tool_result_reference",'
            '"original_output_bytes":900,'
            '"retrieval_tool":"read_tool_result"}'
        ),
    )
    assert projected.conversation[-1] is latest_result
    assert projected.instructions == request.instructions
    assert projected.tool_specs == (_READ_TOOL_RESULT_SPEC,)
    assert request.conversation[1] is older_result


@pytest.mark.asyncio
async def test_two_batch_candidate_keeps_evidence_across_a_diff_check() -> None:
    search_result = ToolResult(call_id="call_search", output="search\n" * 500)
    registry_result = ToolResult(
        call_id="call_registry",
        output="accounting-ledger\n" + ("client\n" * 300) + "transaction-journal\n",
    )
    diff_result = ToolResult(call_id="call_diff", output="focused diff")
    request = ModelRequest(
        conversation=(
            ToolCall(
                call_id="call_search",
                name="search_text",
                arguments={"query": "DEFAULT_TIMEOUT"},
            ),
            search_result,
            Message(role=MessageRole.ASSISTANT, content="Read the registry."),
            ToolCall(
                call_id="call_registry",
                name="read_file",
                arguments={"path": "client_registry.py"},
            ),
            registry_result,
            Message(role=MessageRole.ASSISTANT, content="Check the final diff."),
            ToolCall(call_id="call_diff", name="git_diff", arguments={}),
            diff_result,
        ),
    )
    one_batch = await _reference_projector(
        max_inline_output_bytes=100,
    ).project(request)
    two_batches = await _reference_projector(
        max_inline_output_bytes=100,
        protected_recent_tool_result_batches=2,
    ).project(request)

    assert one_batch.conversation[4] != registry_result
    assert two_batches.conversation[4] is registry_result
    assert one_batch.conversation[-1] is diff_result
    assert two_batches.conversation[-1] is diff_result
    assert two_batches.conversation[1] != search_result
    assert request.conversation[1] is search_result
    assert request.conversation[4] is registry_result

    one_batch_profile = profile_context_projection(request, one_batch)
    two_batch_profile = profile_context_projection(request, two_batches)

    assert one_batch_profile.changed_tool_result_count == 2
    assert two_batch_profile.changed_tool_result_count == 1
    assert one_batch_profile.total_bytes_saved == 5_645
    assert two_batch_profile.total_bytes_saved == 3_353


def test_non_default_retention_cannot_enter_traced_query_loop_yet() -> None:
    projector = _reference_projector(
        max_inline_output_bytes=100,
        protected_recent_tool_result_batches=2,
    )

    with pytest.raises(
        ValueError,
        match="non-default tool-result retention is experimental",
    ):
        describe_context_projector(projector)


@pytest.mark.asyncio
async def test_reference_projector_keeps_eligible_small_result_inline() -> None:
    small_result = ToolResult(call_id="call_small", output="small")
    request = ModelRequest(
        conversation=(
            small_result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=5).project(request)

    assert projected is request
    assert projected.conversation[0] is small_result


@pytest.mark.asyncio
async def test_reference_projector_keeps_unretrievable_large_result_inline() -> None:
    oversized_result = ToolResult(
        call_id="call_oversized",
        output="x" * (DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES + 1),
    )
    latest_result = ToolResult(call_id="call_latest", output="latest")
    request = ModelRequest(
        conversation=(
            oversized_result,
            Message(role=MessageRole.ASSISTANT, content="Inspect the latest result."),
            latest_result,
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=100).project(request)

    assert projected is request
    assert projected.conversation[0] is oversized_result


@pytest.mark.asyncio
async def test_reference_projector_can_reference_result_at_retrieval_limit() -> None:
    boundary_result = ToolResult(
        call_id="call_boundary",
        output="x" * DEFAULT_TOOL_RESULT_READ_LIMIT_BYTES,
    )
    request = ModelRequest(
        conversation=(
            boundary_result,
            Message(role=MessageRole.ASSISTANT, content="Inspect the latest result."),
            ToolResult(call_id="call_latest", output="latest"),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=100).project(request)

    assert projected is not request
    assert projected.conversation[0] != boundary_result


@pytest.mark.asyncio
async def test_reference_projector_never_expands_a_short_result() -> None:
    short_result = ToolResult(call_id="call_short", output="x" * 20)
    request = ModelRequest(
        conversation=(
            short_result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request


@pytest.mark.asyncio
async def test_reference_projector_preserves_earlier_error_result() -> None:
    error_result = ToolResult(
        call_id="call_error",
        output="permission denied" * 100,
        is_error=True,
    )
    request = ModelRequest(
        conversation=(
            error_result,
            Message(role=MessageRole.ASSISTANT, content="Try another path."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request
    assert projected.conversation[0] is error_result


@pytest.mark.parametrize(
    ("max_inline_output_bytes", "error_type", "message"),
    (
        (True, TypeError, "max_inline_output_bytes must be an integer"),
        (-1, ValueError, "max_inline_output_bytes must not be negative"),
    ),
)
def test_reference_projector_validates_byte_limit(
    max_inline_output_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        ToolResultReferenceProjector(
            max_inline_output_bytes=max_inline_output_bytes,  # type: ignore[arg-type]
            retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
        )


@pytest.mark.parametrize(
    ("max_retrievable_output_bytes", "error_type", "message"),
    (
        (True, TypeError, "max_retrievable_output_bytes must be an integer"),
        (0, ValueError, "max_retrievable_output_bytes must be greater than zero"),
    ),
)
def test_reference_projector_validates_retrieval_capacity(
    max_retrievable_output_bytes: object,
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        ToolResultReferenceProjector(
            max_inline_output_bytes=100,
            retrieval_tool_spec=_READ_TOOL_RESULT_SPEC,
            max_retrievable_output_bytes=(  # type: ignore[arg-type]
                max_retrievable_output_bytes
            ),
        )


def test_non_default_retrieval_capacity_cannot_enter_traced_query_loop() -> None:
    projector = _reference_projector(
        max_inline_output_bytes=100,
        max_retrievable_output_bytes=100,
    )

    with pytest.raises(
        ValueError,
        match="non-default tool-result retrieval capacity is experimental",
    ):
        describe_context_projector(projector)


@pytest.mark.asyncio
async def test_reference_projector_skips_projection_without_positive_net_savings() -> (
    None
):
    result = ToolResult(call_id="call_old", output="x" * 300)
    request = ModelRequest(
        conversation=(
            result,
            Message(role=MessageRole.ASSISTANT, content="Continue."),
        )
    )

    projected = await _reference_projector(max_inline_output_bytes=0).project(request)

    assert projected is request
    assert projected.conversation[0] is result
    assert projected.tool_specs == ()


@pytest.mark.asyncio
async def test_query_loop_projects_only_the_model_view() -> None:
    class ReplacingToolOutputProjector:
        async def project(self, request: ModelRequest) -> ModelRequest:
            projected_conversation = tuple(
                ToolResult(
                    call_id=item.call_id,
                    output="[earlier output omitted]",
                    is_error=item.is_error,
                )
                if isinstance(item, ToolResult)
                else item
                for item in request.conversation
            )
            return ModelRequest(
                conversation=projected_conversation,
                tool_specs=request.tool_specs,
                instructions=request.instructions,
            )

    full_tool_result = ToolResult(
        call_id="call_001",
        output="complete file contents",
    )
    tool_call = ToolCall(
        call_id="call_001",
        name="read_file",
        arguments={"path": "README.md"},
    )
    model = ScriptedModel(
        responses=(
            ModelResponse(
                content="I will inspect it.",
                tool_calls=(tool_call,),
            ),
            ModelResponse(content="Inspection complete."),
        )
    )
    checkpoint_store = InMemoryCheckpointStore()
    loop = QueryLoop(
        model=model,
        tool_runtime=ScriptedToolRuntime(results=(full_tool_result,)),
        max_turns=2,
        context_projector=ReplacingToolOutputProjector(),
        event_ledger=InMemoryEventLedger(run_id="run_001"),
        checkpoint_store=checkpoint_store,
    )

    result = await loop.run(
        (
            Message(
                role=MessageRole.USER,
                content="Inspect README.md",
            ),
        )
    )

    assert model.requests[1].conversation[-1] == ToolResult(
        call_id="call_001",
        output="[earlier output omitted]",
    )
    assert result.message_history[-1] is full_tool_result

    checkpoint = checkpoint_store.latest("run_001")
    assert checkpoint is not None
    assert checkpoint.message_history[-1] is full_tool_result
