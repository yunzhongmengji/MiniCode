"""Storage contracts for memory records."""

from typing import Protocol

from minicode.memory.records import (
    MemoryRecord,
    MemoryScope,
)


class MemoryStoreError(RuntimeError):
    """Base exception for memory storage failures."""


class MemoryAlreadyExistsError(MemoryStoreError):
    """Raised when a memory ID already exists."""


class MemoryNotFoundError(MemoryStoreError):
    """Raised when a memory ID does not exist."""


class MemoryStore(Protocol):
    """Store and retrieve memory records."""

    def save(
        self,
        record: MemoryRecord,
    ) -> None:
        """Save one new memory record."""
        ...

    def get(
        self,
        memory_id: str,
    ) -> MemoryRecord | None:
        """Return one record by ID."""
        ...

    def find(
        self,
        scope: MemoryScope,
    ) -> tuple[MemoryRecord, ...]:
        """Return records in one scope."""
        ...

    def delete(
        self,
        memory_id: str,
    ) -> MemoryRecord:
        """Delete and return one record."""
        ...


class InMemoryMemoryStore:
    """Store memory records in process memory."""

    def __init__(self) -> None:
        self._records_by_id: dict[
            str,
            MemoryRecord,
        ] = {}

    def save(
        self,
        record: MemoryRecord,
    ) -> None:
        """Save a record without overwriting."""
        if not isinstance(
            record,
            MemoryRecord,
        ):
            raise TypeError("record must be a MemoryRecord")

        if record.memory_id in self._records_by_id:
            raise MemoryAlreadyExistsError(f"memory already exists: {record.memory_id}")

        self._records_by_id[record.memory_id] = record

    def get(
        self,
        memory_id: str,
    ) -> MemoryRecord | None:
        """Return one record by ID."""
        return self._records_by_id.get(memory_id)

    def find(
        self,
        scope: MemoryScope,
    ) -> tuple[MemoryRecord, ...]:
        """Return records in insertion order."""
        if not isinstance(
            scope,
            MemoryScope,
        ):
            raise TypeError("scope must be a MemoryScope")

        return tuple(
            record for record in self._records_by_id.values() if record.scope == scope
        )

    def delete(
        self,
        memory_id: str,
    ) -> MemoryRecord:
        """Delete and return one record."""
        try:
            return self._records_by_id.pop(memory_id)
        except KeyError:
            raise MemoryNotFoundError(f"memory not found: {memory_id}") from None
