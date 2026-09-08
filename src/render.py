from diag import Diagnostic
from source import SourceFile


def render(sf: SourceFile, d: Diagnostic) -> str:
    """Turn one diagnostic into the block of text shown in the terminal."""
    out: list[str] = []
    out.append(f"{d.severity.value}[{d.code}]: {d.message}")

    if not d.labels:
        return "\n".join(out)

    # Work out each label's line, column, and end column once.
    placed = []
    for lb in d.labels:
        line, col = sf.line_col(lb.span.start)
        _, end_col = sf.line_col(lb.span.end)
        placed.append((line, col, end_col, lb))

    width = len(str(max(p[0] for p in placed)))
    pad = " " * width

    first_line, first_col = placed[0][0], placed[0][1]
    out.append(f"{pad}--> {sf.name}:{first_line}:{first_col}")
    out.append(f"{pad} |")

    # Group labels by the line they sit on, keeping lines in source order.
    by_line: dict[int, list] = {}
    for p in placed:
        by_line.setdefault(p[0], []).append(p)

    for line_no in sorted(by_line):
        # Print the source line once.
        out.append(f"{str(line_no).rjust(width)} | {sf.line_text(line_no)}")

        # Then one caret row per label on that line, leftmost first.
        for _, col, end_col, lb in sorted(by_line[line_no], key=lambda p: p[1]):
            marker = "^" if lb.primary else "-"
            carets = marker * max(1, end_col - col)
            out.append(f"{pad} | {' ' * (col - 1)}{carets} {lb.message}")

    out.append(f"{pad} |")

    for note in d.notes:
        out.append(f"{pad} = note: {note}")
    if d.help:
        out.append(f"{pad} = help: {d.help}")

    return "\n".join(out)