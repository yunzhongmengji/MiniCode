"""Lazy Skill metadata/body split, keyword router, and on-demand load_skill tool."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from minicode.tools.base import ToolExecutionError
from minicode.tools.schema import ToolArguments
from minicode.tools.spec import ToolSpec

LOAD_SKILL_TOOL_NAME = "load_skill"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class SkillMetadata(BaseModel):
    """Lightweight Skill header injected into the default system prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    trigger_keywords: tuple[str, ...] = ()
    source_path: Path


class SkillDocument(BaseModel):
    """Full Skill document loaded on demand."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metadata: SkillMetadata
    instructions: str = Field(min_length=1)


def parse_skill_markdown(path: Path) -> SkillDocument:
    """Parse a Skill Markdown file with YAML-style frontmatter into metadata + body."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise ValueError(f"skill file '{path}' must start with '---' frontmatter")

    closing_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_idx = idx
            break
    if closing_idx is None:
        raise ValueError(f"skill file '{path}' is missing closing '---' frontmatter")

    header_fields: dict[str, str] = {}
    for line in lines[1:closing_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"invalid frontmatter line in '{path}': {line}")
        key, value = stripped.split(":", 1)
        header_fields[key.strip()] = value.strip()

    name = header_fields.get("name", "")
    description = header_fields.get("description", "")
    keywords_raw = header_fields.get("trigger_keywords", "")
    keywords = tuple(
        kw.strip().lower() for kw in keywords_raw.split(",") if kw.strip()
    )
    body = "\n".join(lines[closing_idx + 1 :]).strip()

    metadata = SkillMetadata(
        name=name,
        description=description,
        trigger_keywords=keywords,
        source_path=path.resolve(),
    )
    return SkillDocument(metadata=metadata, instructions=body)


class LazySkillRegistry:
    """Index lightweight Skill metadata and load full instructions only on demand."""

    def __init__(self, metadata_items: tuple[SkillMetadata, ...]) -> None:
        self._by_name: dict[str, SkillMetadata] = {}
        for item in metadata_items:
            if item.name in self._by_name:
                raise ValueError(f"duplicate skill name: '{item.name}'")
            self._by_name[item.name] = item
        self._loaded_names: list[str] = []

    @classmethod
    def discover(cls, skills_dir: Path) -> LazySkillRegistry:
        """Scan *.md files and retain only lightweight metadata in memory."""
        if not skills_dir.is_dir():
            raise FileNotFoundError(f"skills directory not found: {skills_dir}")
        items: list[SkillMetadata] = []
        for path in sorted(skills_dir.glob("*.md")):
            doc = parse_skill_markdown(path)
            items.append(doc.metadata)
        return cls(tuple(items))

    @property
    def metadata_list(self) -> tuple[SkillMetadata, ...]:
        """Return all registered Skill metadata entries."""
        return tuple(self._by_name.values())

    @property
    def loaded_skill_names(self) -> tuple[str, ...]:
        """Return Skill names whose full bodies have been loaded on demand."""
        return tuple(self._loaded_names)

    def render_metadata_prompt(self) -> str:
        """Render a compact catalog prompt containing only Skill metadata."""
        if not self._by_name:
            return ""
        lines = [
            "Available Skills (metadata only; call load_skill(name) when needed):"
        ]
        for meta in self._by_name.values():
            kw = ", ".join(meta.trigger_keywords)
            lines.append(
                f"- {meta.name}: {meta.description} [keywords: {kw}]"
            )
        return "\n".join(lines)

    def render_all_full_instructions(self) -> str:
        """Render every Skill's full body upfront (used as non-routed ablation baseline)."""
        blocks: list[str] = []
        for meta in self._by_name.values():
            doc = parse_skill_markdown(meta.source_path)
            blocks.append(f"## Skill: {meta.name}\n{doc.instructions}")
        return "\n\n".join(blocks)

    def route(self, query: str, *, max_skills: int = 2) -> tuple[SkillMetadata, ...]:
        """Rank skills by keyword/token overlap against a task query."""
        query_lower = query.lower()
        query_tokens = set(_TOKEN_RE.findall(query_lower))
        scored: list[tuple[int, str, SkillMetadata]] = []
        for meta in self._by_name.values():
            score = 0
            for kw in meta.trigger_keywords:
                if kw in query_lower:
                    score += 3
                elif kw in query_tokens:
                    score += 2
            desc_tokens = set(_TOKEN_RE.findall(meta.description.lower()))
            score += len(query_tokens & desc_tokens)
            if score > 0:
                scored.append((score, meta.name, meta))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(item[2] for item in scored[:max_skills])

    def load_instructions(self, name: str) -> SkillDocument:
        """Load the full instruction body for one Skill on demand."""
        meta = self._by_name.get(name)
        if meta is None:
            raise KeyError(f"unknown skill: '{name}'")
        doc = parse_skill_markdown(meta.source_path)
        if name not in self._loaded_names:
            self._loaded_names.append(name)
        return doc


class LoadSkillArguments(ToolArguments):
    """Input schema for the on-demand load_skill tool."""

    name: str = Field(min_length=1)


class LoadSkillTool:
    """Tool allowing the Agent to load a Skill's full instructions on demand."""

    def __init__(self, registry: LazySkillRegistry) -> None:
        self._registry = registry
        self._spec = ToolSpec(
            name=LOAD_SKILL_TOOL_NAME,
            description=(
                "Load the full instructions for a named Skill when its metadata "
                "matches the current coding task."
            ),
            arguments_type=LoadSkillArguments,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: ToolArguments) -> str:
        if not isinstance(arguments, LoadSkillArguments):
            raise TypeError("arguments must be LoadSkillArguments")
        try:
            doc = self._registry.load_instructions(arguments.name)
        except KeyError as error:
            available = ", ".join(m.name for m in self._registry.metadata_list)
            raise ToolExecutionError(
                f"unknown skill '{arguments.name}'. Available: {available}"
            ) from error
        return doc.instructions
