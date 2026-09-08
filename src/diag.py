from dataclasses import dataclass, field
from enum import Enum

from source import Span


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Label:
    """One span of source with a note attached. Each label becomes one
    line of caret art in the rendered output."""
    span: Span
    message: str
    primary: bool = True


@dataclass
class Diagnostic:
    """One complete error or warning."""
    code: str
    severity: Severity
    message: str
    labels: list[Label] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    help: str | None = None

    def with_label(self, span: Span, message: str, primary: bool = True) -> "Diagnostic":
        self.labels.append(Label(span, message, primary))
        return self

    def with_note(self, note: str) -> "Diagnostic":
        self.notes.append(note)
        return self

    def with_help(self, text: str) -> "Diagnostic":
        self.help = text
        return self


class DiagBag:
    """Collects every diagnostic produced during a run. The compiler keeps
    going after an error and reports them all at the end, so this is what
    each pass writes into."""

    def __init__(self):
        self.items: list[Diagnostic] = []

    def error(self, code: str, message: str) -> Diagnostic:
        d = Diagnostic(code, Severity.ERROR, message)
        self.items.append(d)
        return d

    def warning(self, code: str, message: str) -> Diagnostic:
        d = Diagnostic(code, Severity.WARNING, message)
        self.items.append(d)
        return d

    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self.items)

    def sorted(self) -> list[Diagnostic]:
        """Errors in source order, so output is stable for golden tests."""
        return sorted(
            self.items,
            key=lambda d: d.labels[0].span.start if d.labels else 0,
        )