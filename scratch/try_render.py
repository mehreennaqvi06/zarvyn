import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from source import SourceFile, Span
from diag import DiagBag
from render import render

src_text = 'fn greet(name: string) -> int {\n    let count: int = "hello";\n    return count;\n}\n'
sf = SourceFile("examples/broken.zvn", src_text.encode("utf-8"))

bag = DiagBag()

# The two spans we want to point at, on line 2:
#   let count: int = "hello";
# One at the string literal, one at the int annotation.
string_lit = Span(src_text.index('"hello"'), src_text.index('"hello"') + 7)
annotation = Span(src_text.index("int =") , src_text.index("int =") + 3)

(bag.error("ZV-T0104", "type mismatch in variable initializer")
    .with_label(string_lit, "expected `int`, found `string`")
    .with_label(annotation, "expected due to this type annotation", primary=False)
    .with_help("did you mean to parse the string first?"))

for d in bag.sorted():
    print(render(sf, d))
    print()