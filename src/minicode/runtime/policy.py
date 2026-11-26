"""Risk classification and approval policy for runtime tool execution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from minicode.schemas.checkpoints import RiskLevel


class RiskAssessment(BaseModel):
    """Policy decision describing a tool's risk level and approval requirement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(min_length=1)
    risk_level: RiskLevel
    requires_approval: bool
    reason: str = Field(min_length=1)


_DEFAULT_TOOL_RISKS: dict[str, RiskLevel] = {
    "list_files": RiskLevel.READ_ONLY,
    "read_file": RiskLevel.READ_ONLY,
    "search_text": RiskLevel.READ_ONLY,
    "git_diff": RiskLevel.READ_ONLY,
    "read_tool_result": RiskLevel.READ_ONLY,
    "read_artifact": RiskLevel.READ_ONLY,
    "load_skill": RiskLevel.READ_ONLY,
    "create_file": RiskLevel.WRITE_FILE,
    "edit_file": RiskLevel.WRITE_FILE,
    "run_tests": RiskLevel.EXECUTE_SHELL,
    "run_shell": RiskLevel.EXECUTE_SHELL,
    "delete_file": RiskLevel.EXECUTE_SHELL,
}


class ToolRiskPolicy:
    """Classify tools by risk level and determine whether approval is required."""

    def __init__(
        self,
        *,
        tool_risks: Mapping[str, RiskLevel] | None = None,
        approval_required_levels: Iterable[RiskLevel] = (
            RiskLevel.WRITE_FILE,
            RiskLevel.EXECUTE_SHELL,
        ),
        default_risk_level: RiskLevel = RiskLevel.EXECUTE_SHELL,
    ) -> None:
        self._tool_risks = dict(_DEFAULT_TOOL_RISKS)
        if tool_risks is not None:
            self._tool_risks.update(tool_risks)
        self._approval_required_levels = frozenset(approval_required_levels)
        self._default_risk_level = default_risk_level

    def assess(self, tool_name: str) -> RiskAssessment:
        """Assess risk level and whether execution must pause for approval."""
        risk_level = self._tool_risks.get(tool_name, self._default_risk_level)
        requires_approval = risk_level in self._approval_required_levels
        if tool_name not in self._tool_risks:
            reason = (
                f"unclassified tool '{tool_name}' treated as {risk_level.value}"
            )
        elif requires_approval:
            reason = (
                f"tool '{tool_name}' has risk level '{risk_level.value}' "
                "and requires external approval"
            )
        else:
            reason = f"tool '{tool_name}' is classified as '{risk_level.value}'"
        return RiskAssessment(
            tool_name=tool_name,
            risk_level=risk_level,
            requires_approval=requires_approval,
            reason=reason,
        )


def build_default_risk_policy() -> ToolRiskPolicy:
    """Build the default coding-agent tool risk policy."""
    return ToolRiskPolicy()
