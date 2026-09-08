# How to add a feature to Zarvyn

Every file you must touch, in order. Keep this current.

## Adding a new operator (e.g. `**`)

1. `src/tokens.py` — add the kind to `class T`.
2. `src/lex.py` — add the byte pair to the `two` dict in `punct()`,
   or the single byte to the `one` dict.
3. `src/parse.py` — add it to the `INFIX` table with a binding power.
4. `tests/lex/basic.zvn` — add a line using it.
5. `tests/parse/basic.zvn` — add a line using it.
6. Run `python run_tests.py --bless`, then check the diff by eye.

## Adding a new keyword (e.g. `unless`)

1. `src/tokens.py` — add the kind to `class T` and the word to `KEYWORDS`.
2. `src/parse.py` — add a branch in `stmt()` or `item()`.
3. `src/zast.py` — add a dataclass for the node, with a `span` field.
4. `src/astprint.py` — add a `case` arm so it prints.
5. `src/parse.py` — add it to `SYNC` if it can start a statement.
6. Tests + bless.

## Adding a new statement form

Same as a keyword, plus:
- `src/parse.py` — decide whether it needs a `;` terminator.

## Notes

- Every AST node carries a span. Parent spans are built with `.to()`.
- `ast` and `token` are reserved standard-library names. Ours are
  `zast.py` and `tokens.py`. Do not rename them back.
- Source lines may end in `\r`. `SourceFile.line_text` strips it.