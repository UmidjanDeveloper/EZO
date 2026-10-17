"""Pick the orchestration provider. Native is the default and the fallback."""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.orchestration.base import OrchestrationProvider, StepExecutor
from ezo_api.orchestration.native import NativeOrchestrationProvider
from ezo_api.settings import Settings

FALLBACK_NOTICE = (
    "Advanced orchestration provider unavailable; continuing with EZO's native workflow."
)


@dataclass(frozen=True, slots=True)
class OrchestrationSelection:
    provider: OrchestrationProvider
    requested: str
    notice: str = ""
    """Shown when the requested provider could not be used (never an error for the user)."""


def select_orchestration(settings: Settings, executor: StepExecutor) -> OrchestrationSelection:
    requested = settings.orchestration_provider
    native = NativeOrchestrationProvider(executor, step_timeout=settings.ruflo_timeout_seconds)
    if requested != "ruflo":
        return OrchestrationSelection(native, requested)
    if not settings.ruflo_enabled or not settings.ruflo_command:
        return OrchestrationSelection(native, requested, FALLBACK_NOTICE)
    # The Ruflo MCP provider is specified (docs/RUFLO_INTEGRATION_PLAN.md) but intentionally
    # not active yet: missions run natively until the roadmap enables external execution.
    return OrchestrationSelection(native, requested, FALLBACK_NOTICE)
