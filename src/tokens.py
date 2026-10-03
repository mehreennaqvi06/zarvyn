from dataclasses import dataclass
from enum import Enum, auto

from source import Span


class T(Enum):
    # literals and names
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    IDENT = auto()
    # keywords
    FN = auto()
    LET = auto()
    MUT = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    RETURN = auto()
    BREAK = auto()
    CONTINUE = auto()
    STRUCT = auto()
    ENUM = auto()
    MATCH = auto()
    DEFER = auto()
    TRUE = auto()
    FALSE = auto()
    # punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    SEMI = auto()
    COLON = auto()
    DOT = auto()
    ARROW = auto()
    FATARROW = auto()
    # operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    EQEQ = auto()
    BANG = auto()
    BANGEQ = auto()
    LT = auto()
    LTEQ = auto()
    GT = auto()
    GTEQ = auto()
    ANDAND = auto()
    OROR = auto()
    PIPE = auto()
    PIPE_SINGLE = auto()
    # bookkeeping
    ERROR = auto()
    EOF = auto()


KEYWORDS = {
    "fn": T.FN,
    "let": T.LET,
    "mut": T.MUT,
    "if": T.IF,
    "else": T.ELSE,
    "while": T.WHILE,
    "for": T.FOR,
    "in": T.IN,
    "return": T.RETURN,
    "break": T.BREAK,
    "continue": T.CONTINUE,
    "struct": T.STRUCT,
    "enum": T.ENUM,
    "match": T.MATCH,
    "defer": T.DEFER,
    "true": T.TRUE,
    "false": T.FALSE,
}


@dataclass
class Token:
    kind: T
    span: Span
    text: str = ""
    value: object = None