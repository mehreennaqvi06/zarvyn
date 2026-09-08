from bisect import bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A range of BYTES in one source file. Half-open: [start, end)."""
    start: int
    end: int

    def to(self, other: "Span") -> "Span":
        """The span covering both this one and another. Used to give a parent
        AST node the full extent of its children."""
        return Span(min(self.start, other.start), max(self.end, other.end))


class SourceFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.data = data
        # Byte offset where each line begins. Line 1 starts at offset 0.
        self._line_starts = [0]
        for i, byte in enumerate(data):
            if byte == 0x0A:  # b"\n"
                self._line_starts.append(i + 1)

    @classmethod
    def load(cls, path: str) -> "SourceFile":
        with open(path, "rb") as f:
            return cls(path, f.read())

    def line_col(self, offset: int) -> tuple[int, int]:
        """Convert a byte offset to a 1-based line and column.
        Column counts CHARACTERS, not bytes, so the caret lands in the
        right place when the line contains multi-byte characters."""
        line = bisect_right(self._line_starts, offset) - 1
        line_start = self._line_starts[line]
        col_chars = len(self.data[line_start:offset].decode("utf-8", errors="replace"))
        return line + 1, col_chars + 1

    def line_text(self, line: int) -> str:
        """The text of a 1-based line number, without its newline."""
        start = self._line_starts[line - 1]
        if line < len(self._line_starts):
            end = self._line_starts[line] - 1
        else:
            end = len(self.data)
        return self.data[start:end].decode("utf-8", errors="replace").rstrip("\r")

    def slice(self, span: Span) -> str:
        """The source text a span covers, as a string."""
        return self.data[span.start:span.end].decode("utf-8", errors="replace")