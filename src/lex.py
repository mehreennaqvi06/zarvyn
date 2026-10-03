from diag import DiagBag
from source import SourceFile, Span
from tokens import KEYWORDS, T, Token


def is_ident_start(b: int) -> bool:
    return b == 0x5F or (0x41 <= b <= 0x5A) or (0x61 <= b <= 0x7A) or b >= 0x80


def is_ident_cont(b: int) -> bool:
    return is_ident_start(b) or (0x30 <= b <= 0x39)


def is_digit(b: int) -> bool:
    return 0x30 <= b <= 0x39


class Lexer:
    def __init__(self, sf: SourceFile, bag: DiagBag):
        self.sf = sf
        self.data = sf.data
        self.bag = bag
        self.i = 0

    def at_end(self) -> bool:
        return self.i >= len(self.data)

    def peek(self, ahead: int = 0) -> int:
        j = self.i + ahead
        return self.data[j] if j < len(self.data) else -1

    def tokens(self) -> list[Token]:
        out: list[Token] = []
        while True:
            self.skip_trivia()
            if self.at_end():
                end = len(self.data)
                out.append(Token(T.EOF, Span(end, end)))
                return out
            out.append(self.next_token())

    def skip_trivia(self) -> None:
        while not self.at_end():
            b = self.peek()
            if b in (0x20, 0x09, 0x0A, 0x0D):
                self.i += 1
            elif b == 0x2F and self.peek(1) == 0x2F:
                while not self.at_end() and self.peek() != 0x0A:
                    self.i += 1
            elif b == 0x2F and self.peek(1) == 0x2A:
                self.block_comment()
            else:
                return

    def block_comment(self) -> None:
        start = self.i
        self.i += 2
        depth = 1
        while depth > 0:
            if self.at_end():
                self.bag.error("ZV-L0003", "unterminated block comment").with_label(
                    Span(start, start + 2), "this comment is never closed"
                )
                return
            if self.peek() == 0x2F and self.peek(1) == 0x2A:
                depth += 1
                self.i += 2
            elif self.peek() == 0x2A and self.peek(1) == 0x2F:
                depth -= 1
                self.i += 2
            else:
                self.i += 1

    def next_token(self) -> Token:
        start = self.i
        b = self.peek()

        if is_digit(b):
            return self.number(start)
        if is_ident_start(b):
            return self.ident(start)
        if b == 0x22:
            return self.string(start)
        return self.punct(start)

    def ident(self, start: int) -> Token:
        while not self.at_end() and is_ident_cont(self.peek()):
            self.i += 1
        span = Span(start, self.i)
        text = self.sf.slice(span)
        return Token(KEYWORDS.get(text, T.IDENT), span, text)

    def number(self, start: int) -> Token:
        while not self.at_end() and is_digit(self.peek()):
            self.i += 1
        is_float = False
        if self.peek() == 0x2E and is_digit(self.peek(1)):
            is_float = True
            self.i += 1
            while not self.at_end() and is_digit(self.peek()):
                self.i += 1
        span = Span(start, self.i)
        text = self.sf.slice(span)
        if is_float:
            return Token(T.FLOAT, span, text, float(text))
        return Token(T.INT, span, text, int(text))

    def string(self, start: int) -> Token:
        self.i += 1
        chunks: list[str] = []
        while True:
            if self.at_end() or self.peek() == 0x0A:
                span = Span(start, self.i)
                self.bag.error("ZV-L0001", "unterminated string literal").with_label(
                    span, "this string is never closed"
                )
                return Token(T.ERROR, span, self.sf.slice(span))
            b = self.peek()
            if b == 0x22:
                self.i += 1
                span = Span(start, self.i)
                return Token(T.STRING, span, self.sf.slice(span), "".join(chunks))
            if b == 0x5C:
                self.escape(chunks)
            else:
                j = self.i
                self.i += 1
                while not self.at_end() and 0x80 <= self.peek() < 0xC0:
                    self.i += 1
                chunks.append(self.data[j:self.i].decode("utf-8", errors="replace"))

    def escape(self, chunks: list[str]) -> None:
        start = self.i
        self.i += 1
        b = self.peek()
        simple = {0x6E: "\n", 0x74: "\t", 0x72: "\r", 0x5C: "\\", 0x22: '"', 0x30: "\0"}
        if b in simple:
            chunks.append(simple[b])
            self.i += 1
            return
        if b == 0x75 and self.peek(1) == 0x7B:
            self.i += 2
            digits = ""
            while not self.at_end() and self.peek() != 0x7D:
                digits += chr(self.peek())
                self.i += 1
            if self.at_end():
                self.bag.error("ZV-L0004", "unterminated unicode escape").with_label(
                    Span(start, self.i), "expected a closing brace"
                )
                return
            self.i += 1
            try:
                chunks.append(chr(int(digits, 16)))
            except ValueError:
                self.bag.error("ZV-L0005", "invalid unicode escape").with_label(
                    Span(start, self.i), "not a valid code point"
                )
            return
        self.bag.error("ZV-L0002", "unknown escape sequence").with_label(
            Span(start, self.i + 1), "this escape is not recognised"
        )
        self.i += 1

    def punct(self, start: int) -> Token:
        b = self.peek()
        nxt = self.peek(1)

        two = {
            (0x2D, 0x3E): T.ARROW,     # ->
            (0x3D, 0x3E): T.FATARROW,  # =>
            (0x3D, 0x3D): T.EQEQ,      # ==
            (0x21, 0x3D): T.BANGEQ,    # !=
            (0x3C, 0x3D): T.LTEQ,      # <=
            (0x3E, 0x3D): T.GTEQ,      # >=
            (0x26, 0x26): T.ANDAND,    # &&
            (0x7C, 0x7C): T.OROR,      # ||
            (0x7C, 0x3E): T.PIPE,      # |>
        }
        if (b, nxt) in two:
            self.i += 2
            return Token(two[(b, nxt)], Span(start, self.i))

        one = {
            0x28: T.LPAREN, 0x29: T.RPAREN,
            0x7B: T.LBRACE, 0x7D: T.RBRACE,
            0x5B: T.LBRACKET, 0x5D: T.RBRACKET,
            0x2C: T.COMMA, 0x3B: T.SEMI, 0x3A: T.COLON, 0x2E: T.DOT,
            0x2B: T.PLUS, 0x2D: T.MINUS, 0x2A: T.STAR,
            0x2F: T.SLASH, 0x25: T.PERCENT,
            0x3D: T.EQ, 0x21: T.BANG, 0x3C: T.LT, 0x3E: T.GT, 0x7C: T.PIPE_SINGLE,
        }
        if b in one:
            self.i += 1
            return Token(one[b], Span(start, self.i))

        self.i += 1
        span = Span(start, self.i)
        self.bag.error("ZV-L0006", "unexpected character").with_label(
            span, "this character is not valid Zarvyn"
        )
        return Token(T.ERROR, span, self.sf.slice(span))