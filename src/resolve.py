from dataclasses import dataclass, field

import zast as A
from diag import DiagBag
from source import Span


@dataclass
class Local:
    name: str
    slot: int
    mutable: bool
    span: Span
    boxed: bool = False       # captured and mutated: lives in a heap cell
    captured: bool = False


@dataclass
class Upvalue:
    """A variable a lambda refers to from an enclosing function."""
    name: str
    from_parent_slot: bool    # True: take from parent's locals; False: from parent's upvalues
    index: int


@dataclass
class ScopeFrame:
    """One lexical block. Holds its locals and anything it defers."""
    locals: dict = field(default_factory=dict)
    defers: list = field(default_factory=list)
    is_loop: bool = False
    is_fn_root: bool = False


class FnContext:
    """Resolution state for one function or lambda."""

    def __init__(self, parent=None, node=None):
        self.parent = parent
        self.node = node
        self.scopes: list[ScopeFrame] = []
        self.next_slot = 0
        self.max_slots = 0
        self.upvalues: list[Upvalue] = []

    def alloc_slot(self) -> int:
        slot = self.next_slot
        self.next_slot += 1
        self.max_slots = max(self.max_slots, self.next_slot)
        return slot


class Resolver:
    def __init__(self, bag: DiagBag):
        self.bag = bag
        self.fn: FnContext | None = None
        self.globals: dict[str, object] = {}
        # Results, keyed by the id() of the AST node.
        self.resolved: dict[int, object] = {}
        self.fn_info: dict[int, dict] = {}
        self.exit_defers: dict[int, list] = {}

    # ---------- entry point ----------

    def run(self, prog: A.Program) -> None:
        # Pass one: collect every top-level name, so forward references work.
        for item in prog.items:
            match item:
                case A.FnDecl() | A.StructDecl() | A.EnumDecl():
                    if item.name in self.globals:
                        self.bag.error("ZV-R0001", f"`{item.name}` is declared more than once").with_label(
                            item.span, "this name is already taken at file scope"
                        )
                    self.globals[item.name] = item

        # Pass two: walk the bodies.
        for item in prog.items:
            if isinstance(item, A.FnDecl):
                self.fn_decl(item)

    # ---------- scope helpers ----------

    def push_scope(self, is_loop: bool = False, is_fn_root: bool = False) -> None:
        self.fn.scopes.append(ScopeFrame(is_loop=is_loop, is_fn_root=is_fn_root))

    def pop_scope(self) -> ScopeFrame:
        frame = self.fn.scopes.pop()
        self.fn.next_slot -= len(frame.locals)
        return frame

    def declare(self, name: str, mutable: bool, span: Span) -> Local:
        frame = self.fn.scopes[-1]
        if name in frame.locals:
            prev = frame.locals[name]
            self.bag.error("ZV-R0002", f"`{name}` is declared twice in the same scope").with_label(
                span, "this redeclaration"
            ).with_label(prev.span, "first declared here", primary=False)
        local = Local(name, self.fn.alloc_slot(), mutable, span)
        frame.locals[name] = local
        return local

    def lookup_local(self, fn: FnContext, name: str) -> Local | None:
        for frame in reversed(fn.scopes):
            if name in frame.locals:
                return frame.locals[name]
        return None

    def resolve_upvalue(self, fn: FnContext, name: str) -> int | None:
        """Find `name` in an enclosing function, threading it through as an
        upvalue on every function in between. Returns the index into
        fn.upvalues, or None if the name isn't an enclosing local."""
        if fn.parent is None:
            return None

        for i, uv in enumerate(fn.upvalues):
            if uv.name == name:
                return i

        parent_local = self.lookup_local(fn.parent, name)
        if parent_local is not None:
            parent_local.captured = True
            if parent_local.mutable:
                parent_local.boxed = True
            fn.upvalues.append(Upvalue(name, True, parent_local.slot))
            return len(fn.upvalues) - 1

        parent_index = self.resolve_upvalue(fn.parent, name)
        if parent_index is not None:
            fn.upvalues.append(Upvalue(name, False, parent_index))
            return len(fn.upvalues) - 1

        return None

    # ---------- declarations ----------

    def fn_decl(self, node: A.FnDecl) -> None:
        self.fn = FnContext(parent=None, node=node)
        self.push_scope(is_fn_root=True)
        for p in node.params:
            self.resolved[id(p)] = self.declare(p.name, False, p.span)
        self.block(node.body, new_scope=False)
        frame = self.pop_scope()
        self.fn_info[id(node)] = {
            "max_slots": self.fn.max_slots,
            "upvalues": self.fn.upvalues,
            "root_defers": frame.defers,
        }
        self.fn = None

    def lambda_expr(self, node: A.Lambda) -> None:
        outer = self.fn
        self.fn = FnContext(parent=outer, node=node)
        self.push_scope(is_fn_root=True)
        for p in node.params:
            self.resolved[id(p)] = self.declare(p.name, False, p.span)

        if isinstance(node.body, A.Block):
            self.block(node.body, new_scope=False)
        else:
            self.expr(node.body)

        frame = self.pop_scope()
        self.fn_info[id(node)] = {
            "max_slots": self.fn.max_slots,
            "upvalues": self.fn.upvalues,
            "root_defers": frame.defers,
        }
        self.fn = outer

    # ---------- statements ----------

    def block(self, node: A.Block, new_scope: bool = True) -> None:
        if new_scope:
            self.push_scope()
        for s in node.stmts:
            self.stmt(s)
        if new_scope:
            frame = self.pop_scope()
            self.exit_defers[id(node)] = frame.defers
        else:
            self.exit_defers[id(node)] = self.fn.scopes[-1].defers

    def stmt(self, node) -> None:
        match node:
            case A.Let():
                self.expr(node.value)
                local = self.declare(node.name, node.mutable, node.span)
                self.resolved[id(node)] = local

            case A.ExprStmt():
                self.expr(node.expr)

            case A.Block():
                self.block(node)

            case A.If():
                self.expr(node.cond)
                self.block(node.then_block)
                if node.else_block is not None:
                    if isinstance(node.else_block, A.If):
                        self.stmt(node.else_block)
                    else:
                        self.block(node.else_block)

            case A.While():
                self.expr(node.cond)
                self.push_scope(is_loop=True)
                for s in node.body.stmts:
                    self.stmt(s)
                frame = self.pop_scope()
                self.exit_defers[id(node.body)] = frame.defers

            case A.For():
                self.expr(node.iterable)
                self.push_scope(is_loop=True)
                self.resolved[id(node)] = self.declare(node.var_name, False, node.span)
                for s in node.body.stmts:
                    self.stmt(s)
                frame = self.pop_scope()
                self.exit_defers[id(node.body)] = frame.defers

            case A.Return():
                if node.value is not None:
                    self.expr(node.value)
                self.exit_defers[id(node)] = self.collect_exit_defers(to_fn_root=True)

            case A.Break():
                if not self.in_loop():
                    self.bag.error("ZV-R0003", "`break` outside a loop").with_label(
                        node.span, "there is no enclosing loop here"
                    )
                self.exit_defers[id(node)] = self.collect_exit_defers(to_loop=True)

            case A.Continue():
                if not self.in_loop():
                    self.bag.error("ZV-R0004", "`continue` outside a loop").with_label(
                        node.span, "there is no enclosing loop here"
                    )
                self.exit_defers[id(node)] = self.collect_exit_defers(to_loop=True)

            case A.Defer():
                self.expr(node.expr)
                self.fn.scopes[-1].defers.append(node)

            case A.Match():
                self.expr(node.scrutinee)
                for arm in node.arms:
                    self.push_scope()
                    self.pattern(arm.pattern)
                    if isinstance(arm.body, A.Block):
                        for s in arm.body.stmts:
                            self.stmt(s)
                    else:
                        self.expr(arm.body)
                    self.pop_scope()

    def in_loop(self) -> bool:
        for frame in reversed(self.fn.scopes):
            if frame.is_loop:
                return True
            if frame.is_fn_root:
                return False
        return False

    def collect_exit_defers(self, to_loop: bool = False, to_fn_root: bool = False) -> list:
        """Every deferred expression that must run on this exit edge, innermost
        scope first, and in reverse declaration order within each scope."""
        out = []
        for frame in reversed(self.fn.scopes):
            out.extend(reversed(frame.defers))
            if to_loop and frame.is_loop:
                break
            if to_fn_root and frame.is_fn_root:
                break
        return out

    # ---------- patterns ----------

    def pattern(self, node) -> None:
        match node:
            case A.PatBind():
                self.resolved[id(node)] = self.declare(node.name, False, node.span)
            case A.PatVariant():
                for sub in node.sub_patterns:
                    self.pattern(sub)
            case A.PatStruct():
                for f in node.fields:
                    self.pattern(f.pattern)
            case A.PatWild() | A.PatLit():
                pass

    # ---------- expressions ----------

    def expr(self, node) -> None:
        match node:
            case A.Name():
                self.resolve_name(node)

            case A.Assign():
                self.expr(node.value)
                self.expr(node.target)
                if isinstance(node.target, A.Name):
                    target = self.resolved.get(id(node.target))
                    if isinstance(target, Local) and not target.mutable:
                        self.bag.error("ZV-R0005", f"cannot assign to immutable `{target.name}`").with_label(
                            node.span, "this assignment"
                        ).with_label(target.span, "declared without `mut` here", primary=False)

            case A.Binary():
                self.expr(node.left)
                self.expr(node.right)

            case A.Unary():
                self.expr(node.operand)

            case A.Call():
                self.expr(node.callee)
                for a in node.args:
                    self.expr(a)

            case A.FieldAccess():
                self.expr(node.target)

            case A.Index():
                self.expr(node.target)
                self.expr(node.index)

            case A.StructLit():
                if node.type_name not in self.globals:
                    self.bag.error("ZV-R0006", f"unknown type `{node.type_name}`").with_label(
                        node.span, "no struct or enum with this name"
                    )
                for f in node.fields:
                    self.expr(f.value)

            case A.Lambda():
                self.lambda_expr(node)

            case A.Match():
                self.stmt(node)

            case A.IntLit() | A.FloatLit() | A.StrLit() | A.BoolLit():
                pass

    def resolve_name(self, node: A.Name) -> None:
        local = self.lookup_local(self.fn, node.name)
        if local is not None:
            self.resolved[id(node)] = local
            return

        uv_index = self.resolve_upvalue(self.fn, node.name)
        if uv_index is not None:
            self.resolved[id(node)] = ("upvalue", uv_index)
            return

        if node.name in self.globals:
            self.resolved[id(node)] = ("global", node.name)
            return

        self.bag.error("ZV-R0007", f"cannot find `{node.name}` in this scope").with_label(
            node.span, "not found"
        )