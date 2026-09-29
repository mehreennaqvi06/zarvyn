import zast as A
from diag import DiagBag
from source import Span
from tokens import T, Token

# Binding power for each infix operator. Higher binds tighter.
INFIX = {
    T.OROR: (1, "||"),
    T.ANDAND: (2, "&&"),
    T.EQEQ: (3, "=="),
    T.BANGEQ: (3, "!="),
    T.LT: (3, "<"),
    T.LTEQ: (3, "<="),
    T.GT: (3, ">"),
    T.GTEQ: (3, ">="),
    T.PIPE: (4, "|>"),
    T.PLUS: (5, "+"),
    T.MINUS: (5, "-"),
    T.STAR: (6, "*"),
    T.SLASH: (6, "/"),
    T.PERCENT: (6, "%"),
}

MAX_DEPTH = 200

# Tokens we resynchronise on after a parse error.
SYNC = {T.SEMI, T.RBRACE, T.MATCH, T.FN, T.STRUCT, T.LET, T.IF, T.WHILE, T.FOR, T.RETURN, T.EOF}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, toks: list[Token], bag: DiagBag):
        self.toks = toks
        self.bag = bag
        self.i = 0
        self.depth = 0
        self.no_struct = 0

    # ---------- token helpers ----------

    def peek(self, ahead: int = 0) -> Token:
        j = min(self.i + ahead, len(self.toks) - 1)
        return self.toks[j]

    def at(self, kind: T) -> bool:
        return self.peek().kind is kind

    def advance(self) -> Token:
        tok = self.peek()
        if tok.kind is not T.EOF:
            self.i += 1
        return tok

    def eat(self, kind: T) -> Token | None:
        if self.at(kind):
            return self.advance()
        return None

    def expect(self, kind: T, what: str) -> Token:
        if self.at(kind):
            return self.advance()
        got = self.peek()
        self.bag.error("ZV-P0001", f"expected {what}").with_label(
            got.span, f"found {got.kind.name.lower()} here"
        )
        raise ParseError()

    # ---------- entry point ----------

    def program(self) -> A.Program:
        prog = A.Program()
        while not self.at(T.EOF):
            try:
                prog.items.append(self.item())
            except ParseError:
                self.recover()
        return prog

    def recover(self) -> None:
        """Skip tokens until we reach something that can start a new item."""
        while not self.at(T.EOF):
            if self.peek().kind in (T.FN, T.STRUCT, T.ENUM):
                return
            if self.eat(T.SEMI) or self.eat(T.RBRACE):
                return
            self.advance()

    def item(self):
        if self.at(T.FN):
            return self.fn_decl()
        if self.at(T.STRUCT):
            return self.struct_decl()
        if self.at(T.ENUM):
            return self.enum_decl() 
        got = self.peek()
        self.bag.error("ZV-P0002", "expected a top-level declaration").with_label(
            got.span, "only `fn` and `struct` can appear here"
        )
        raise ParseError()

    # ---------- declarations ----------

    def fn_decl(self) -> A.FnDecl:
        start = self.expect(T.FN, "`fn`").span
        name_tok = self.expect(T.IDENT, "a function name")
        self.expect(T.LPAREN, "`(`")

        params = []
        while not self.at(T.RPAREN):
            p_name = self.expect(T.IDENT, "a parameter name")
            self.expect(T.COLON, "`:` after the parameter name")
            p_type = self.type_ref()
            params.append(A.Param(p_name.text, p_type, p_name.span.to(p_type.span)))
            if not self.eat(T.COMMA):
                break
        self.expect(T.RPAREN, "`)`")

        ret = None
        if self.eat(T.ARROW):
            ret = self.type_ref()

        body = self.block()
        return A.FnDecl(name_tok.text, params, ret, body, start.to(body.span))

    def struct_decl(self) -> A.StructDecl:
        start = self.expect(T.STRUCT, "`struct`").span
        name_tok = self.expect(T.IDENT, "a struct name")
        self.expect(T.LBRACE, "`{`")

        fields = []
        while not self.at(T.RBRACE):
            f_name = self.expect(T.IDENT, "a field name")
            self.expect(T.COLON, "`:` after the field name")
            f_type = self.type_ref()
            fields.append(A.StructField(f_name.text, f_type, f_name.span.to(f_type.span)))
            if not self.eat(T.COMMA):
                break
        end = self.expect(T.RBRACE, "`}`").span
        return A.StructDecl(name_tok.text, fields, start.to(end))

    def enum_decl(self) -> A.EnumDecl:
        start = self.expect(T.ENUM, "`enum`").span
        name_tok = self.expect(T.IDENT, "an enum name")
        self.expect(T.LBRACE, "`{`")

        variants = []
        while not self.at(T.RBRACE):
            v_name = self.expect(T.IDENT, "a variant name")
            payload = []
            v_end = v_name.span
            if self.eat(T.LPAREN):
                while not self.at(T.RPAREN):
                    payload.append(self.type_ref())
                    if not self.eat(T.COMMA):
                        break
                v_end = self.expect(T.RPAREN, "`)`").span
            variants.append(A.EnumVariant(v_name.text, payload, v_name.span.to(v_end)))
            if not self.eat(T.COMMA):
                break
        end = self.expect(T.RBRACE, "`}`").span
        return A.EnumDecl(name_tok.text, variants, start.to(end)) 

    def type_ref(self) -> A.TypeName:
        tok = self.expect(T.IDENT, "a type name")
        return A.TypeName(tok.text, tok.span)

    # ---------- statements ----------

    def block(self) -> A.Block:
        start = self.expect(T.LBRACE, "`{`").span
        stmts = []
        while not self.at(T.RBRACE) and not self.at(T.EOF):
            try:
                stmts.append(self.stmt())
            except ParseError:
                self.sync_in_block()
        end = self.expect(T.RBRACE, "`}`").span
        return A.Block(stmts, start.to(end))

    def sync_in_block(self) -> None:
        while not self.at(T.EOF):
            if self.peek().kind in SYNC:
                self.eat(T.SEMI)
                return
            self.advance()

    def stmt(self):
        if self.at(T.LET):
            return self.let_stmt()
        if self.at(T.IF):
            return self.if_stmt()
        if self.at(T.WHILE):
            return self.while_stmt()
        if self.at(T.FOR):
            return self.for_stmt() 
        if self.at(T.RETURN):
            return self.return_stmt()
        if self.at(T.DEFER):
            return self.defer_stmt()
        if self.at(T.MATCH):
            return self.match_stmt()
        if self.at(T.BREAK):
            tok = self.advance()
            end = self.expect(T.SEMI, "`;`").span
            return A.Break(tok.span.to(end))
        if self.at(T.CONTINUE):
            tok = self.advance()
            end = self.expect(T.SEMI, "`;`").span
            return A.Continue(tok.span.to(end))
        if self.at(T.LBRACE):
            return self.block()

        expr = self.expr()
        end = self.expect(T.SEMI, "`;` after the expression").span
        return A.ExprStmt(expr, expr.span.to(end))

    def let_stmt(self) -> A.Let:
        start = self.advance().span
        mutable = self.eat(T.MUT) is not None
        name_tok = self.expect(T.IDENT, "a variable name")

        declared = None
        if self.eat(T.COLON):
            declared = self.type_ref()

        self.expect(T.EQ, "`=`")
        value = self.expr()
        end = self.expect(T.SEMI, "`;`").span
        return A.Let(name_tok.text, mutable, declared, value, start.to(end))

    def if_stmt(self) -> A.If:
        start = self.advance().span
        self.no_struct += 1
        cond = self.expr()
        self.no_struct -= 1
        then_block = self.block()
        else_block = None
        if self.eat(T.ELSE):
            else_block = self.if_stmt() if self.at(T.IF) else self.block()
        end = else_block.span if else_block else then_block.span
        return A.If(cond, then_block, else_block, start.to(end))

    def while_stmt(self) -> A.While:
        start = self.advance().span
        cond = self.expr()
        body = self.block()
        return A.While(cond, body, start.to(body.span))

    def for_stmt(self) -> A.For:
        start = self.advance().span
        var_tok = self.expect(T.IDENT, "a loop variable name")
        self.expect(T.IN, "`in`")
        self.no_struct += 1
        iterable = self.expr()
        self.no_struct -= 1
        body = self.block()
        return A.For(var_tok.text, iterable, body, start.to(body.span))

    def return_stmt(self) -> A.Return:
        start = self.advance().span
        value = None
        if not self.at(T.SEMI):
            value = self.expr()
        end = self.expect(T.SEMI, "`;`").span
        return A.Return(value, start.to(end))

    def defer_stmt(self) -> A.Defer:
        start = self.advance().span
        expr = self.expr()
        end = self.expect(T.SEMI, "`;`").span
        return A.Defer(expr, start.to(end))

    def match_stmt(self) -> A.Match:
        start = self.advance().span
        self.no_struct += 1
        scrutinee = self.expr()
        self.no_struct -= 1
        self.expect(T.LBRACE, "`{`")

        arms = []
        while not self.at(T.RBRACE) and not self.at(T.EOF):
            pat = self.pattern()
            self.expect(T.FATARROW, "`=>` after the pattern")
            if self.at(T.LBRACE):
                body = self.block()
            else:
                body = self.expr(0)
            arms.append(A.MatchArm(pat, body, pat.span.to(body.span)))
            self.eat(T.COMMA)
        end = self.expect(T.RBRACE, "`}`").span
        return A.Match(scrutinee, arms, start.to(end))

    def pattern(self):
        tok = self.peek()

        if tok.kind is T.INT:
            self.advance()
            return A.PatLit(tok.value, tok.span)
        if tok.kind is T.STRING:
            self.advance()
            return A.PatLit(tok.value, tok.span)
        if tok.kind is T.TRUE:
            self.advance()
            return A.PatLit(True, tok.span)
        if tok.kind is T.FALSE:
            self.advance()
            return A.PatLit(False, tok.span)

        if tok.kind is T.IDENT:
            if tok.text == "_":
                self.advance()
                return A.PatWild(tok.span)

            path = [self.advance()]
            while self.at(T.COLON) and self.peek(1).kind is T.COLON:
                self.advance()
                self.advance()
                path.append(self.expect(T.IDENT, "a path segment"))

            if self.at(T.LPAREN):
                self.advance()
                subs = []
                while not self.at(T.RPAREN):
                    subs.append(self.pattern())
                    if not self.eat(T.COMMA):
                        break
                end = self.expect(T.RPAREN, "`)`").span
                names = [t.text for t in path]
                return A.PatVariant(names, subs, path[0].span.to(end))

            if self.at(T.LBRACE):
                return self.pattern_struct(path[0])

            if len(path) > 1:
                names = [t.text for t in path]
                return A.PatVariant(names, [], path[0].span.to(path[-1].span))
            return A.PatBind(path[0].text, path[0].span)

        self.bag.error("ZV-P0005", "expected a pattern").with_label(
            tok.span, f"found {tok.kind.name.lower()} here"
        )
        raise ParseError()

    def pattern_struct(self, name_tok) -> A.PatStruct:
        self.expect(T.LBRACE, "`{`")
        fields = []
        rest = False
        while not self.at(T.RBRACE):
            if self.at(T.DOT) and self.peek(1).kind is T.DOT:
                self.advance()
                self.advance()
                rest = True
                break
            f_name = self.expect(T.IDENT, "a field name")
            if self.eat(T.COLON):
                sub = self.pattern()
            else:
                sub = A.PatBind(f_name.text, f_name.span)
            fields.append(A.PatField(f_name.text, sub, f_name.span.to(sub.span)))
            if not self.eat(T.COMMA):
                break
        end = self.expect(T.RBRACE, "`}`").span
        return A.PatStruct(name_tok.text, fields, rest, name_tok.span.to(end))

    # ---------- expressions (Pratt) ----------

    def expr(self, min_bp: int = 0):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            self.depth -= 1
            self.bag.error("ZV-P0003", "expression nested too deeply").with_label(
                self.peek().span, f"the limit is {MAX_DEPTH} levels"
            )
            raise ParseError()
        try:
            return self._expr(min_bp)
        finally:
            self.depth -= 1

    def _expr(self, min_bp: int):
        left = self.prefix()

        while True:
            kind = self.peek().kind

            if kind is T.EQ and min_bp == 0:
                self.advance()
                value = self.expr(0)
                left = A.Assign(left, value, left.span.to(value.span))
                continue

            entry = INFIX.get(kind)
            if entry is None:
                return left
            bp, op = entry
            if bp < min_bp:
                return left

            self.advance()
            right = self.expr(bp + 1)
            left = A.Binary(op, left, right, left.span.to(right.span))

    def prefix(self):
        tok = self.peek()

        if tok.kind is T.MINUS or tok.kind is T.BANG:
            self.advance()
            op = "-" if tok.kind is T.MINUS else "!"
            operand = self.expr(7)
            return A.Unary(op, operand, tok.span.to(operand.span))

        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            if self.at(T.LPAREN):
                self.advance()
                args = []
                while not self.at(T.RPAREN):
                    args.append(self.expr(0))
                    if not self.eat(T.COMMA):
                        break
                end = self.expect(T.RPAREN, "`)`").span
                node = A.Call(node, args, node.span.to(end))
            elif self.at(T.DOT):
                self.advance()
                name_tok = self.expect(T.IDENT, "a field name")
                node = A.FieldAccess(node, name_tok.text, node.span.to(name_tok.span))
            elif self.at(T.LBRACKET):
                self.advance()
                index = self.expr(0)
                end = self.expect(T.RBRACKET, "`]`").span
                node = A.Index(node, index, node.span.to(end))
            else:
                return node
            
    def struct_lit(self, name_tok) -> A.StructLit:
        self.expect(T.LBRACE, "`{`")
        saved = self.no_struct
        self.no_struct = 0
        fields = []
        while not self.at(T.RBRACE):
            f_name = self.expect(T.IDENT, "a field name")
            self.expect(T.COLON, "`:` after the field name")
            value = self.expr(0)
            fields.append(A.FieldInit(f_name.text, value, f_name.span.to(value.span)))
            if not self.eat(T.COMMA):
                break
        end = self.expect(T.RBRACE, "`}`").span
        self.no_struct = saved
        return A.StructLit(name_tok.text, fields, name_tok.span.to(end))

    def primary(self):
        tok = self.peek()

        if tok.kind is T.INT:
            self.advance()
            return A.IntLit(tok.value, tok.span)
        if tok.kind is T.FLOAT:
            self.advance()
            return A.FloatLit(tok.value, tok.span)
        if tok.kind is T.STRING:
            self.advance()
            return A.StrLit(tok.value, tok.span)
        if tok.kind is T.TRUE:
            self.advance()
            return A.BoolLit(True, tok.span)
        if tok.kind is T.FALSE:
            self.advance()
            return A.BoolLit(False, tok.span)
        if tok.kind is T.IDENT:
            self.advance()
            if self.at(T.LBRACE) and self.no_struct == 0:
                return self.struct_lit(tok)
            return A.Name(tok.text, tok.span)

        if tok.kind is T.LPAREN:
            self.advance()
            inner = self.expr(0)
            self.expect(T.RPAREN, "`)`")
            return inner

        self.bag.error("ZV-P0004", "expected an expression").with_label(
            tok.span, f"found {tok.kind.name.lower()} here"
        )
        raise ParseError()