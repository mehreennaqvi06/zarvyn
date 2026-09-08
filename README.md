# Zarvyn

A compiler for Zarvyn, a small statically typed language, written in Python.
Built as an internship assignment.

## Status

**M1 complete** — lexer, parser, AST, and diagnostics.

| Stage | State |
|---|---|
| 1. Lexer | done |
| 2. Parser + AST | partial (no `match`, `enum`, or struct literals yet) |
| 3. Resolver | not started |
| 4. Type checker | not started |
| 5. Tree-walking interpreter | not started |
| 6. IR + lowering | not started |
| 7. Bytecode + VM | not started |
| 8. Optimizer + GC | not started |

## Layout

- `src/source.py` — spans and line/column lookup
- `src/diag.py` — diagnostic data model
- `src/render.py` — terminal diagnostic renderer
- `src/tokens.py` — token kinds and keyword table
- `src/lex.py` — lexer
- `src/zast.py` — AST node definitions
- `src/parse.py` — recursive-descent parser with Pratt expressions
- `src/astprint.py` — AST to S-expression printer
- `tests/` — golden tests, one folder per stage
- `docs/` — design notes

## Running the tests

    python run_tests.py
    python run_tests.py --bless

The second form rewrites the expected output files. Use it after a
deliberate change, and read the diff before blessing.

## Design notes

Spans are byte offsets into the source, not line/column pairs. Line and
column are derived on demand from a line-start index, so the lexer never
has to track them. Columns are counted in characters rather than bytes so
carets line up under multi-byte characters.

Source files may use CRLF line endings; a trailing carriage return is
stripped when a source line is rendered.

Two modules are named `zast.py` and `tokens.py` rather than `ast.py` and
`token.py` because both of those shadow Python standard-library modules
that `dataclasses` transitively imports.