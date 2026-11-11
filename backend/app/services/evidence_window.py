"""Shared verbal evidence windows. Whole text is never falsely time-clipped."""
from dataclasses import dataclass, field
from typing import Any

from app.services.evidence_quality import finite_time

VERBAL_HOOK_SECONDS = 8.0


@dataclass
class EvidenceWindow:
    segments: list[dict[str, Any]] = field(default_factory=list)
    boundary_ranges: list[tuple[float, float]] = field(default_factory=list)
    untimed_count: int = 0
    start: float = 0.0
    end: float = VERBAL_HOOK_SECONDS

    @property
    def text(self) -> str | None:
        return " ".join(str(s["text"]) for s in self.segments).strip() or None

    def describe(self) -> dict[str, Any]:
        return {"requested_start": self.start, "requested_end": self.end,
                "actual_ranges": [(s["start_time"], s["end_time"]) for s in self.segments],
                "excluded_boundary_ranges": self.boundary_ranges, "untimed_count": self.untimed_count,
                "status": "partial" if self.segments and (self.boundary_ranges or self.untimed_count)
                          else "valid" if self.segments else "not_assessable",
                "limitation": "Boundary-crossing or untimed speech excluded; word timing unavailable."
                              if self.boundary_ranges or self.untimed_count else None}


def select_evidence_window(segments: list[dict[str, Any]], *, start: float = 0.0,
                           end: float = VERBAL_HOOK_SECONDS) -> EvidenceWindow:
    if not 0 <= start < end or finite_time(end) is None:
        raise ValueError("Evidence window must have finite ordered nonnegative bounds.")
    window = EvidenceWindow(start=start, end=end)
    previous_end = start
    for segment in sorted(segments, key=lambda s: finite_time(s.get("start_time")) or 0.0):
        if not str(segment.get("text") or "").strip():
            continue
        left, right = finite_time(segment.get("start_time")), finite_time(segment.get("end_time"))
        if left is None or right is None:
            window.untimed_count += 1
            continue
        if left < 0 or right <= left or right <= start or left >= end:
            continue
        if left < start or right > end or left < previous_end:
            window.boundary_ranges.append((left, right))
            continue
        window.segments.append(segment)
        previous_end = right
    return window
