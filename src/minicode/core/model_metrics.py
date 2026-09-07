"""Provider-neutral model-call observation records."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from time import perf_counter

from minicode.core.model import (
    Model,
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


class ModelErrorKind(StrEnum):
    """Stable categories for failed model calls."""

    CANCELLED = "cancelled"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    QUOTA_EXCEEDED = "quota_exceeded"
    ACCESS_DENIED = "access_denied"
    SERVICE = "service"
    PROTOCOL = "protocol"


def _classify_model_error(
    error: ModelError,
) -> ModelErrorKind | None:
    """Convert a model exception into a stable metrics category."""
    if isinstance(
        error,
        ModelAuthenticationError,
    ):
        return ModelErrorKind.AUTHENTICATION

    if isinstance(
        error,
        ModelRateLimitError,
    ):
        return ModelErrorKind.RATE_LIMIT

    if isinstance(
        error,
        ModelConnectionError,
    ):
        return ModelErrorKind.CONNECTION

    if isinstance(
        error,
        ModelQuotaExceededError,
    ):
        return ModelErrorKind.QUOTA_EXCEEDED

    if isinstance(
        error,
        ModelAccessDeniedError,
    ):
        return ModelErrorKind.ACCESS_DENIED

    if isinstance(
        error,
        ModelServiceError,
    ):
        return ModelErrorKind.SERVICE

    if isinstance(
        error,
        ModelProtocolError,
    ):
        return ModelErrorKind.PROTOCOL

    return None


@dataclass(frozen=True, slots=True)
class ModelCallRecord:
    """Metrics observed for one model call."""

    elapsed_seconds: float
    usage: ModelUsage | None = None
    error_kind: ModelErrorKind | None = None

    def __post_init__(self) -> None:
        """Validate and normalize observed metrics."""
        elapsed_seconds = self.elapsed_seconds

        if isinstance(
            elapsed_seconds,
            bool,
        ) or not isinstance(
            elapsed_seconds,
            (int, float),
        ):
            raise TypeError("elapsed_seconds must be a number")

        normalized_elapsed_seconds = float(elapsed_seconds)

        if not isfinite(normalized_elapsed_seconds) or normalized_elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")

        if self.usage is not None and not isinstance(
            self.usage,
            ModelUsage,
        ):
            raise TypeError("usage must be a ModelUsage or None")

        if self.error_kind is not None and not isinstance(
            self.error_kind,
            ModelErrorKind,
        ):
            raise TypeError("error_kind must be a ModelErrorKind or None")

        object.__setattr__(
            self,
            "elapsed_seconds",
            normalized_elapsed_seconds,
        )


class RecordingModel:
    """Record metrics while delegating calls to another model."""

    def __init__(
        self,
        model: Model,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._model = model
        self._clock = clock
        self._records: list[ModelCallRecord] = []

    @property
    def records(
        self,
    ) -> tuple[ModelCallRecord, ...]:
        """Return an immutable snapshot of recorded calls."""
        return tuple(self._records)

    async def complete(
        self,
        request: ModelRequest,
    ) -> ModelResponse:
        """Delegate one call and record its metrics."""
        started_at = self._clock()

        try:
            response = await self._model.complete(request)
        except asyncio.CancelledError:
            finished_at = self._clock()

            self._records.append(
                ModelCallRecord(
                    elapsed_seconds=(finished_at - started_at),
                    error_kind=(ModelErrorKind.CANCELLED),
                )
            )

            raise
        except ModelError as error:
            finished_at = self._clock()
            error_kind = _classify_model_error(error)

            if error_kind is not None:
                self._records.append(
                    ModelCallRecord(
                        elapsed_seconds=(finished_at - started_at),
                        error_kind=error_kind,
                    )
                )

            raise

        finished_at = self._clock()

        self._records.append(
            ModelCallRecord(
                elapsed_seconds=(finished_at - started_at),
                usage=response.usage,
            )
        )

        return response
