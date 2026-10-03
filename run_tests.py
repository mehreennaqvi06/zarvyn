import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from diag import DiagBag
from lex import Lexer
from render import render
from source import SourceFile
from astprint import sexpr
from parse import Parser
from resolve import Resolver
from resolveprint import dump

BLESS = "--bless" in sys.argv


def lex_output(path: pathlib.Path) -> str:
    sf = SourceFile(path.name, path.read_bytes())
    bag = DiagBag()
    lines = []
    for tok in Lexer(sf, bag).tokens():
        lines.append(f"{tok.kind.name} {tok.span.start}..{tok.span.end} {tok.text!r}")
    for d in bag.sorted():
        lines.append("")
        lines.append(render(sf, d))
    return "\n".join(lines) + "\n"

def parse_output(path: pathlib.Path) -> str:
    sf = SourceFile(path.name, path.read_bytes())
    bag = DiagBag()
    toks = Lexer(sf, bag).tokens()
    prog = Parser(toks, bag).program()
    parts = [sexpr(prog)]
    for d in bag.sorted():
        parts.append("")
        parts.append(render(sf, d))
    return "\n".join(parts) + "\n"

def resolve_output(path: pathlib.Path) -> str:
    sf = SourceFile(path.name, path.read_bytes())
    bag = DiagBag()
    toks = Lexer(sf, bag).tokens()
    prog = Parser(toks, bag).program()
    r = Resolver(bag)
    r.run(prog)
    parts = [dump(prog, r)]
    for d in bag.sorted():
        parts.append(render(sf, d))
        parts.append("")
    return "\n".join(parts) + "\n"

def main() -> int:
    passed = failed = blessed = 0

    for zvn in sorted((ROOT / "tests" / "lex").glob("*.zvn")):
        expected_path = zvn.with_suffix(".expected")
        actual = lex_output(zvn)

        if BLESS or not expected_path.exists():
            expected_path.write_text(actual, encoding="utf-8", newline="\n")
            print(f"blessed  {zvn.name}")
            blessed += 1
            continue

        expected = expected_path.read_text(encoding="utf-8", newline="\n")
        if actual == expected:
            print(f"ok       {zvn.name}")
            passed += 1
        else:
            print(f"FAILED   {zvn.name}")
            failed += 1
            for line in _diff(expected, actual):
                print("   " + line)

    for zvn in sorted((ROOT / "tests" / "parse").glob("*.zvn")):
        expected_path = zvn.with_suffix(".expected")
        actual = parse_output(zvn)

        if BLESS or not expected_path.exists():
            expected_path.write_text(actual, encoding="utf-8", newline="\n")
            print(f"blessed  parse/{zvn.name}")
            blessed += 1
            continue

        expected = expected_path.read_text(encoding="utf-8", newline="\n")
        if actual == expected:
            print(f"ok       parse/{zvn.name}")
            passed += 1
        else:
            print(f"FAILED   parse/{zvn.name}")
            failed += 1
            for line in _diff(expected, actual):
                print("   " + line)

    for zvn in sorted((ROOT / "tests" / "resolve").glob("*.zvn")):
        expected_path = zvn.with_suffix(".expected")
        actual = resolve_output(zvn)

        if BLESS or not expected_path.exists():
            expected_path.write_text(actual, encoding="utf-8", newline="\n")
            print(f"blessed  resolve/{zvn.name}")
            blessed += 1
            continue

        expected = expected_path.read_text(encoding="utf-8", newline="\n")
        if actual == expected:
            print(f"ok       resolve/{zvn.name}")
            passed += 1
        else:
            print(f"FAILED   resolve/{zvn.name}")
            failed += 1
            for line in _diff(expected, actual):
                print("   " + line)

    print()
    print(f"{passed} passed, {failed} failed, {blessed} blessed")
    return 1 if failed else 0


def _diff(expected: str, actual: str) -> list[str]:
    import difflib
    return list(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile="expected", tofile="actual", lineterm="",
    ))


if __name__ == "__main__":
    sys.exit(main())