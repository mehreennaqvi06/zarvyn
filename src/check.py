import zast as A
from diag import DiagBag
from resolve import Local, Resolver
from ztypes import (BOOL, ERROR, FLOAT, INT, PRIMITIVES, STRING, UNIT, EnumInfo,
                   StructInfo, Ty, VariantInfo, compatible, fn_params,
                   fn_return, fn_ty)

ARITH = {"+", "-", "*", "/", "%"}
COMPARE = {"<", "<=", ">", ">="}
EQUALITY = {"==", "!="}
LOGICAL = {"&&", "||"}


class Checker:
    def __init__(self, bag: DiagBag, resolver: Resolver):
        self.bag = bag
        self.r = resolver
        self.structs: dict[str, StructInfo] = {}
        self.enums: dict[str, EnumInfo] = {}
        self.fns: dict[str, Ty] = {}
        self.types: dict[int, Ty] = {}      # id(expr node) -> Ty
        self.slot_ty: dict[int, Ty] = {}    # id(Local) -> Ty
        self.current_return = UNIT

    # ---------- entry point ----------

    def run(self, prog: A.Program) -> None:
        for item in prog.items:
            match item:
                case A.StructDecl():
                    self.structs[item.name] = StructInfo(item.name)
                case A.EnumDecl():
                    self.enums[item.name] = EnumInfo(item.name)

        for item in prog.items:
            match item:
                case A.StructDecl():
                    info = self.structs[item.name]
                    for f in item.fields:
                        info.fields[f.name] = self.resolve_type(f.declared_type)
                        info.order.append(f.name)
                case A.EnumDecl():
                    info = self.enums[item.name]
                    for v in item.variants:
                        payload = [self.resolve_type(t) for t in v.payload_types]
                        info.variants[v.name] = VariantInfo(v.name, payload)
                        info.order.append(v.name)

        for item in prog.items:
            if isinstance(item, A.FnDecl):
                params = [self.resolve_type(p.declared_type) for p in item.params]
                ret = self.resolve_type(item.return_type) if item.return_type else UNIT
                self.fns[item.name] = fn_ty(params, ret)

        for item in prog.items:
            if isinstance(item, A.FnDecl):
                self.fn_body(item)

    def resolve_type(self, node) -> Ty:
        if node is None:
            return UNIT
        name = node.name
        if name in PRIMITIVES:
            return PRIMITIVES[name]
        if name in self.structs or name in self.enums:
            return Ty(name)
        self.bag.error("ZV-T0001", f"unknown type `{name}`").with_label(
            node.span, "no type with this name"
        )
        return ERROR

    # ---------- functions ----------

    def fn_body(self, node: A.FnDecl) -> None:
        saved = self.current_return
        self.current_return = fn_return(self.fns[node.name])

        for p, ty in zip(node.params, fn_params(self.fns[node.name])):
            local = self.r.resolved.get(id(p))
            if isinstance(local, Local):
                self.slot_ty[id(local)] = ty

        self.block(node.body)

        if self.current_return is not UNIT and not self.returns(node.body):
            self.bag.error("ZV-T0201", f"not every path through `{node.name}` returns a value").with_label(
                node.span, f"this function must return `{self.current_return}`"
            )

        self.current_return = saved

    def returns(self, node) -> bool:
        """True if this statement or block definitely returns."""
        match node:
            case A.Block():
                return any(self.returns(s) for s in node.stmts)
            case A.Return():
                return True
            case A.If():
                if node.else_block is None:
                    return False
                return self.returns(node.then_block) and self.returns(node.else_block)
            case A.Match():
                if not node.arms:
                    return False
                return all(self.returns(a.body) for a in node.arms)
            case A.While() | A.For():
                return False
        return False

    # ---------- statements ----------

    def block(self, node: A.Block) -> None:
        for s in node.stmts:
            self.stmt(s)

    def stmt(self, node) -> None:
        match node:
            case A.Let():
                value_ty = self.expr(node.value)
                local = self.r.resolved.get(id(node))
                if node.declared_type is not None:
                    declared = self.resolve_type(node.declared_type)
                    if not compatible(declared, value_ty):
                        self.bag.error("ZV-T0104", "type mismatch in variable initializer").with_label(
                            node.value.span, f"expected `{declared}`, found `{value_ty}`"
                        ).with_label(
                            node.declared_type.span, "expected due to this type annotation",
                            primary=False,
                        )
                    final = declared
                else:
                    final = value_ty
                if isinstance(local, Local):
                    self.slot_ty[id(local)] = final

            case A.ExprStmt():
                self.expr(node.expr)

            case A.Block():
                self.block(node)

            case A.If():
                cond = self.expr(node.cond)
                if not compatible(cond, BOOL):
                    self.bag.error("ZV-T0105", "condition must be a `bool`").with_label(
                        node.cond.span, f"found `{cond}`"
                    )
                self.block(node.then_block)
                if node.else_block is not None:
                    if isinstance(node.else_block, A.If):
                        self.stmt(node.else_block)
                    else:
                        self.block(node.else_block)

            case A.While():
                cond = self.expr(node.cond)
                if not compatible(cond, BOOL):
                    self.bag.error("ZV-T0105", "condition must be a `bool`").with_label(
                        node.cond.span, f"found `{cond}`"
                    )
                self.block(node.body)

            case A.For():
                self.expr(node.iterable)
                local = self.r.resolved.get(id(node))
                if isinstance(local, Local):
                    self.slot_ty[id(local)] = INT
                self.block(node.body)

            case A.Return():
                found = self.expr(node.value) if node.value is not None else UNIT
                if not compatible(found, self.current_return):
                    self.bag.error("ZV-T0202", "return type mismatch").with_label(
                        node.span, f"expected `{self.current_return}`, found `{found}`"
                    )

            case A.Defer():
                self.expr(node.expr)

            case A.Break() | A.Continue():
                pass

            case A.Match():
                self.match_expr(node)

    # ---------- match ----------

    def match_expr(self, node: A.Match) -> Ty:
        scrutinee = self.expr(node.scrutinee)
        arm_types = []

        for arm in node.arms:
            self.pattern(arm.pattern, scrutinee)
            if isinstance(arm.body, A.Block):
                self.block(arm.body)
                arm_types.append(UNIT)
            else:
                arm_types.append(self.expr(arm.body))

        self.check_exhaustive(node, scrutinee)
        self.check_reachable(node)

        result = arm_types[0] if arm_types else UNIT
        for t in arm_types[1:]:
            if not compatible(t, result):
                result = ERROR
                break
        self.types[id(node)] = result
        return result

    def check_exhaustive(self, node: A.Match, scrutinee: Ty) -> None:
        if scrutinee is ERROR:
            return
        if any(isinstance(a.pattern, (A.PatWild, A.PatBind)) for a in node.arms):
            return

        if scrutinee.name in self.enums:
            info = self.enums[scrutinee.name]
            covered = set()
            for arm in node.arms:
                if isinstance(arm.pattern, A.PatVariant) and arm.pattern.path:
                    covered.add(arm.pattern.path[-1])
            missing = [v for v in info.order if v not in covered]
            if missing:
                names = ", ".join(f"`{m}`" for m in missing)
                self.bag.error("ZV-T0301", "match is not exhaustive").with_label(
                    node.span, f"these cases are not handled: {names}"
                ).with_help("add a `_ => ...` arm, or handle the missing cases")
            return

        self.bag.error("ZV-T0302", "match is not exhaustive").with_label(
            node.span, f"`{scrutinee}` has values not covered by these arms"
        ).with_help("add a `_ => ...` arm")

    def check_reachable(self, node: A.Match) -> None:
        seen_catchall = None
        for arm in node.arms:
            if seen_catchall is not None:
                self.bag.error("ZV-T0303", "unreachable match arm").with_label(
                    arm.pattern.span, "this arm can never match"
                ).with_label(seen_catchall, "because this arm matches everything", primary=False)
                return
            if isinstance(arm.pattern, (A.PatWild, A.PatBind)):
                seen_catchall = arm.pattern.span

    def pattern(self, node, expected: Ty) -> None:
        match node:
            case A.PatWild():
                pass

            case A.PatBind():
                local = self.r.resolved.get(id(node))
                if isinstance(local, Local):
                    self.slot_ty[id(local)] = expected

            case A.PatLit():
                lit_ty = self.literal_ty(node.value)
                if not compatible(lit_ty, expected):
                    self.bag.error("ZV-T0304", "pattern type does not match").with_label(
                        node.span, f"expected `{expected}`, found `{lit_ty}`"
                    )

            case A.PatVariant():
                if expected.name not in self.enums:
                    if expected is not ERROR:
                        self.bag.error("ZV-T0305", "variant pattern on a non-enum type").with_label(
                            node.span, f"`{expected}` is not an enum"
                        )
                    return
                info = self.enums[expected.name]
                vname = node.path[-1]
                if vname not in info.variants:
                    self.bag.error("ZV-T0306", f"`{expected}` has no variant `{vname}`").with_label(
                        node.span, "unknown variant"
                    )
                    return
                v = info.variants[vname]
                if len(node.sub_patterns) != len(v.payload):
                    self.bag.error("ZV-T0307", "wrong number of fields in variant pattern").with_label(
                        node.span,
                        f"`{vname}` takes {len(v.payload)}, found {len(node.sub_patterns)}",
                    )
                    return
                for sub, ty in zip(node.sub_patterns, v.payload):
                    self.pattern(sub, ty)

            case A.PatStruct():
                if node.type_name not in self.structs:
                    self.bag.error("ZV-T0308", f"unknown struct `{node.type_name}`").with_label(
                        node.span, "no struct with this name"
                    )
                    return
                info = self.structs[node.type_name]
                for f in node.fields:
                    if f.name not in info.fields:
                        self.bag.error("ZV-T0309", f"`{node.type_name}` has no field `{f.name}`").with_label(
                            f.span, "unknown field"
                        ).with_note(f"available fields: {', '.join(info.order)}")
                        continue
                    self.pattern(f.pattern, info.fields[f.name])
                if not node.rest:
                    missing = [n for n in info.order if n not in {f.name for f in node.fields}]
                    if missing:
                        names = ", ".join(f"`{m}`" for m in missing)
                        self.bag.error("ZV-T0310", "struct pattern is missing fields").with_label(
                            node.span, f"not matched: {names}"
                        ).with_help("add the missing fields, or end the pattern with `..`")

    def literal_ty(self, value) -> Ty:
        if isinstance(value, bool):
            return BOOL
        if isinstance(value, int):
            return INT
        if isinstance(value, float):
            return FLOAT
        if isinstance(value, str):
            return STRING
        return ERROR

    # ---------- expressions ----------

    def expr(self, node) -> Ty:
        ty = self._expr(node)
        self.types[id(node)] = ty
        return ty

    def _expr(self, node) -> Ty:
        match node:
            case A.IntLit():
                return INT
            case A.FloatLit():
                return FLOAT
            case A.StrLit():
                return STRING
            case A.BoolLit():
                return BOOL

            case A.Name():
                return self.name_ty(node)

            case A.Assign():
                value = self.expr(node.value)
                target = self.expr(node.target)
                if not compatible(value, target):
                    self.bag.error("ZV-T0106", "type mismatch in assignment").with_label(
                        node.value.span, f"expected `{target}`, found `{value}`"
                    ).with_label(node.target.span, "this has type "
                                 f"`{target}`", primary=False)
                return target

            case A.Unary():
                operand = self.expr(node.operand)
                if node.op == "-":
                    if not (compatible(operand, INT) or compatible(operand, FLOAT)):
                        self.bag.error("ZV-T0107", "`-` needs a numeric operand").with_label(
                            node.operand.span, f"found `{operand}`"
                        )
                        return ERROR
                    return operand
                if not compatible(operand, BOOL):
                    self.bag.error("ZV-T0108", "`!` needs a `bool` operand").with_label(
                        node.operand.span, f"found `{operand}`"
                    )
                    return ERROR
                return BOOL

            case A.Binary():
                return self.binary(node)

            case A.Call():
                return self.call(node)

            case A.FieldAccess():
                target = self.expr(node.target)
                if target is ERROR:
                    return ERROR
                if target.name not in self.structs:
                    self.bag.error("ZV-T0109", "field access on a non-struct value").with_label(
                        node.target.span, f"`{target}` has no fields"
                    )
                    return ERROR
                info = self.structs[target.name]
                if node.field_name not in info.fields:
                    self.bag.error("ZV-T0110", f"`{target}` has no field `{node.field_name}`").with_label(
                        node.span, "unknown field"
                    ).with_note(f"available fields: {', '.join(info.order)}")
                    return ERROR
                return info.fields[node.field_name]

            case A.Index():
                self.expr(node.target)
                idx = self.expr(node.index)
                if not compatible(idx, INT):
                    self.bag.error("ZV-T0111", "index must be an `int`").with_label(
                        node.index.span, f"found `{idx}`"
                    )
                return ERROR

            case A.StructLit():
                return self.struct_lit(node)

            case A.Lambda():
                return self.lambda_expr(node)

            case A.Match():
                return self.match_expr(node)

        return ERROR

    def name_ty(self, node: A.Name) -> Ty:
        target = self.r.resolved.get(id(node))
        if isinstance(target, Local):
            return self.slot_ty.get(id(target), ERROR)
        if isinstance(target, tuple):
            kind, payload = target
            if kind == "global":
                if payload in self.fns:
                    return self.fns[payload]
                return ERROR
            return ERROR
        return ERROR

    def binary(self, node: A.Binary) -> Ty:
        if node.op == "|>":
            return self.pipeline(node)

        left = self.expr(node.left)
        right = self.expr(node.right)

        if node.op in LOGICAL:
            if not compatible(left, BOOL) or not compatible(right, BOOL):
                bad = node.left if not compatible(left, BOOL) else node.right
                found = left if not compatible(left, BOOL) else right
                self.bag.error("ZV-T0112", f"`{node.op}` needs `bool` operands").with_label(
                    bad.span, f"found `{found}`"
                )
                return ERROR
            return BOOL

        if node.op in EQUALITY:
            if not compatible(left, right):
                self.bag.error("ZV-T0113", "cannot compare values of different types").with_label(
                    node.right.span, f"`{right}`"
                ).with_label(node.left.span, f"`{left}`", primary=False)
            return BOOL

        if node.op in COMPARE:
            if not compatible(left, right):
                self.bag.error("ZV-T0113", "cannot compare values of different types").with_label(
                    node.right.span, f"`{right}`"
                ).with_label(node.left.span, f"`{left}`", primary=False)
                return BOOL
            if not (compatible(left, INT) or compatible(left, FLOAT) or compatible(left, STRING)):
                self.bag.error("ZV-T0114", f"`{node.op}` is not defined for `{left}`").with_label(
                    node.span, "not an ordered type"
                )
            return BOOL

        # arithmetic
        if node.op == "+" and compatible(left, STRING) and compatible(right, STRING):
            return STRING
        if not compatible(left, right):
            self.bag.error("ZV-T0115", f"`{node.op}` needs matching operand types").with_label(
                node.right.span, f"found `{right}`"
            ).with_label(node.left.span, f"expected `{left}` to match", primary=False)
            return ERROR
        if not (compatible(left, INT) or compatible(left, FLOAT)):
            self.bag.error("ZV-T0116", f"`{node.op}` is not defined for `{left}`").with_label(
                node.span, "not a numeric type"
            )
            return ERROR
        return left

    def pipeline(self, node: A.Binary) -> Ty:
        """x |> f desugars to f(x). The error must point at the original span."""
        arg = self.expr(node.left)
        callee = self.expr(node.right)

        if callee is ERROR:
            return ERROR
        if callee.name != "fn":
            self.bag.error("ZV-T0117", "right side of `|>` is not callable").with_label(
                node.right.span, f"`{callee}` cannot be called"
            )
            return ERROR

        params = fn_params(callee)
        if len(params) != 1:
            self.bag.error("ZV-T0118", "`|>` needs a function taking exactly one argument").with_label(
                node.right.span, f"this takes {len(params)}"
            )
            return ERROR
        if not compatible(arg, params[0]):
            self.bag.error("ZV-T0119", "piped value has the wrong type").with_label(
                node.left.span, f"expected `{params[0]}`, found `{arg}`"
            ).with_label(node.right.span, "required by this function", primary=False)
            return ERROR
        return fn_return(callee)

    def call(self, node: A.Call) -> Ty:
        callee = self.expr(node.callee)
        args = [self.expr(a) for a in node.args]

        if callee is ERROR:
            return ERROR
        if callee.name != "fn":
            self.bag.error("ZV-T0120", "this value is not callable").with_label(
                node.callee.span, f"`{callee}` cannot be called"
            )
            return ERROR

        params = fn_params(callee)
        if len(args) != len(params):
            self.bag.error("ZV-T0121", "wrong number of arguments").with_label(
                node.span, f"expected {len(params)}, found {len(args)}"
            )
            return fn_return(callee)

        for a_node, a_ty, p_ty in zip(node.args, args, params):
            if not compatible(a_ty, p_ty):
                self.bag.error("ZV-T0122", "argument type mismatch").with_label(
                    a_node.span, f"expected `{p_ty}`, found `{a_ty}`"
                )
        return fn_return(callee)

    def struct_lit(self, node: A.StructLit) -> Ty:
        if node.type_name not in self.structs:
            return ERROR
        info = self.structs[node.type_name]
        given = set()

        for f in node.fields:
            value = self.expr(f.value)
            given.add(f.name)
            if f.name not in info.fields:
                self.bag.error("ZV-T0123", f"`{node.type_name}` has no field `{f.name}`").with_label(
                    f.span, "unknown field"
                ).with_note(f"available fields: {', '.join(info.order)}")
                continue
            if not compatible(value, info.fields[f.name]):
                self.bag.error("ZV-T0124", "field type mismatch").with_label(
                    f.value.span, f"expected `{info.fields[f.name]}`, found `{value}`"
                )

        missing = [n for n in info.order if n not in given]
        if missing:
            names = ", ".join(f"`{m}`" for m in missing)
            self.bag.error("ZV-T0125", "missing fields in struct literal").with_label(
                node.span, f"not initialised: {names}"
            )
        return Ty(node.type_name)

    def lambda_expr(self, node: A.Lambda) -> Ty:
        params = []
        for p in node.params:
            ty = self.resolve_type(p.declared_type) if p.declared_type else ERROR
            params.append(ty)
            local = self.r.resolved.get(id(p))
            if isinstance(local, Local):
                self.slot_ty[id(local)] = ty

        if isinstance(node.body, A.Block):
            self.block(node.body)
            ret = UNIT
        else:
            ret = self.expr(node.body)
        return fn_ty(params, ret)