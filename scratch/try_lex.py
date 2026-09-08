import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from source import SourceFile
from diag import DiagBag
from render import render
from lex import Lexer

code = '''fn main() {
    let s = "never closed
    let x = 5 @ 3;
    /* open comment
'''

sf = SourceFile("t.zvn", code.encode("utf-8"))
bag = DiagBag()

for tok in Lexer(sf, bag).tokens():
    print(f"{tok.kind.name:10} {tok.span.start:3}..{tok.span.end:<3} {tok.text!r}")

print()
print("diagnostics:", len(bag.items))
for d in bag.sorted():
    print(render(sf, d))