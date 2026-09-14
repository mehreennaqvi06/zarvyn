import zast as A


def sexpr(node, indent: int = 0) -> str:
    """Print an AST node as an indented S-expression."""
    pad = "  " * indent

    if node is None:
        return f"{pad}()"

    def block(head: str, children: list) -> str:
        if not children:
            return f"{pad}({head})"
        inner = "\n".join(sexpr(c, indent + 1) for c in children)
        return f"{pad}({head}\n{inner})"

    match node:
        case A.Program():
            return block("program", node.items)

        case A.FnDecl():
            parts = list(node.params)
            if node.return_type:
                parts.append(node.return_type)
            parts.append(node.body)
            return block(f"fn {node.name}", parts)

        case A.Param():
            return f"{pad}(param {node.name} {node.declared_type.name})"

        case A.StructDecl():
            return block(f"struct {node.name}", node.fields)

        case A.StructField():
            return f"{pad}(field {node.name} {node.declared_type.name})"

        case A.EnumDecl():
            return block(f"enum {node.name}", node.variants)

        case A.EnumVariant():
            if not node.payload_types:
                return f"{pad}(variant {node.name})"
            types = " ".join(t.name for t in node.payload_types)
            return f"{pad}(variant {node.name} {types})"

        case A.TypeName():
            return f"{pad}(type {node.name})"

        case A.Block():
            return block("block", node.stmts)

        case A.Let():
            head = f"let{' mut' if node.mutable else ''} {node.name}"
            parts = []
            if node.declared_type:
                parts.append(node.declared_type)
            parts.append(node.value)
            return block(head, parts)

        case A.If():
            parts = [node.cond, node.then_block]
            if node.else_block:
                parts.append(node.else_block)
            return block("if", parts)

        case A.While():
            return block("while", [node.cond, node.body])

        case A.For():
            return block(f"for {node.var_name}", [node.iterable, node.body])

        case A.Return():
            return block("return", [node.value] if node.value else [])

        case A.Defer():
            return block("defer", [node.expr])

        case A.Break():
            return f"{pad}(break)"

        case A.Continue():
            return f"{pad}(continue)"

        case A.ExprStmt():
            return block("expr-stmt", [node.expr])

        case A.Assign():
            return block("assign", [node.target, node.value])

        case A.Binary():
            return block(f"binary {node.op}", [node.left, node.right])

        case A.Unary():
            return block(f"unary {node.op}", [node.operand])

        case A.Call():
            return block("call", [node.callee, *node.args])

        case A.FieldAccess():
            return block(f"field .{node.field_name}", [node.target])

        case A.Index():
            return block("index", [node.target, node.index])

        case A.IntLit():
            return f"{pad}(int {node.value})"

        case A.FloatLit():
            return f"{pad}(float {node.value})"

        case A.StrLit():
            return f"{pad}(str {node.value!r})"

        case A.BoolLit():
            return f"{pad}(bool {'true' if node.value else 'false'})"

        case A.Name():
            return f"{pad}(name {node.name})"

    return f"{pad}(??? {type(node).__name__})"