import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from source import SourceFile, Span

text = "fn main() {\nlet x = 1;\n}\n"
sf = SourceFile("test.zvn", text.encode("utf-8"))

print("line 2 text:", repr(sf.line_text(2)))
print("offset 12 is at:", sf.line_col(12))
print("slice of Span(12, 15):", repr(sf.slice(Span(12, 15))))