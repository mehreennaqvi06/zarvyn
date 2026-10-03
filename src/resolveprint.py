import zast as A
from resolve import Local, Resolver


def dump(prog: A.Program, r: Resolver) -> str:
    out: list[str] = []

    for item in prog.items:
        if not isinstance(item, A.FnDecl):
            continue
        info = r.fn_info.get(id(item), {})
        out.append(f"fn {item.name}  slots={info.get('max_slots', 0)}")
        for p in item.params:
            loc = r.resolved.get(id(p))
            if isinstance(loc, Local):
                out.append(f"  param {p.name} -> slot {loc.slot}")
        walk(item.body, r, out, 1)
        out.append("")

    return "\n".join(out) + "\n"


def walk(node, r: Resolver, out: list, depth: int) -> None:
    pad = "  " * depth

    match node:
        case A.Block():
            for s in node.stmts:
                walk(s, r, out, depth)

        case A.Let():
            loc = r.resolved.get(id(node))
            if isinstance(loc, Local):
                flags = []
                if loc.mutable:
                    flags.append("mut")
                if loc.captured:
                    flags.append("captured")
                if loc.boxed:
                    flags.append("boxed")
                suffix = f" [{' '.join(flags)}]" if flags else ""
                out.append(f"{pad}let {node.name} -> slot {loc.slot}{suffix}")
            walk(node.value, r, out, depth)

        case A.Lambda():
            info = r.fn_info.get(id(node), {})
            uvs = info.get("upvalues", [])
            desc = ", ".join(
                f"{u.name}<-{'local' if u.from_parent_slot else 'upval'}:{u.index}" for u in uvs
            )
            out.append(f"{pad}lambda  slots={info.get('max_slots', 0)}  upvalues=[{desc}]")
            for p in node.params:
                loc = r.resolved.get(id(p))
                if isinstance(loc, Local):
                    out.append(f"{pad}  param {p.name} -> slot {loc.slot}")
            walk(node.body, r, out, depth + 1)

        case A.Name():
            target = r.resolved.get(id(node))
            if isinstance(target, Local):
                out.append(f"{pad}name {node.name} -> slot {target.slot}")
            elif isinstance(target, tuple):
                out.append(f"{pad}name {node.name} -> {target[0]} {target[1]}")

        case A.Defer():
            out.append(f"{pad}defer")
            walk(node.expr, r, out, depth + 1)

        case A.Return() | A.Break() | A.Continue():
            kind = type(node).__name__.lower()
            defers = r.exit_defers.get(id(node), [])
            out.append(f"{pad}{kind}  runs {len(defers)} defer(s)")
            if isinstance(node, A.Return) and node.value is not None:
                walk(node.value, r, out, depth + 1)

        case A.If():
            walk(node.cond, r, out, depth)
            walk(node.then_block, r, out, depth + 1)
            if node.else_block is not None:
                walk(node.else_block, r, out, depth + 1)

        case A.While():
            walk(node.cond, r, out, depth)
            walk(node.body, r, out, depth + 1)

        case A.For():
            loc = r.resolved.get(id(node))
            if isinstance(loc, Local):
                out.append(f"{pad}for {node.var_name} -> slot {loc.slot}")
            walk(node.iterable, r, out, depth)
            walk(node.body, r, out, depth + 1)

        case A.Match():
            walk(node.scrutinee, r, out, depth)
            for arm in node.arms:
                out.append(f"{pad}arm")
                walk_pattern(arm.pattern, r, out, depth + 1)
                walk(arm.body, r, out, depth + 1)

        case A.ExprStmt():
            walk(node.expr, r, out, depth)

        case A.Assign():
            walk(node.target, r, out, depth)
            walk(node.value, r, out, depth)

        case A.Binary():
            walk(node.left, r, out, depth)
            walk(node.right, r, out, depth)

        case A.Unary():
            walk(node.operand, r, out, depth)

        case A.Call():
            walk(node.callee, r, out, depth)
            for a in node.args:
                walk(a, r, out, depth)

        case A.FieldAccess():
            walk(node.target, r, out, depth)

        case A.Index():
            walk(node.target, r, out, depth)
            walk(node.index, r, out, depth)

        case A.StructLit():
            for f in node.fields:
                walk(f.value, r, out, depth)


def walk_pattern(node, r: Resolver, out: list, depth: int) -> None:
    pad = "  " * depth
    match node:
        case A.PatBind():
            loc = r.resolved.get(id(node))
            if isinstance(loc, Local):
                out.append(f"{pad}bind {node.name} -> slot {loc.slot}")
        case A.PatVariant():
            for sub in node.sub_patterns:
                walk_pattern(sub, r, out, depth)
        case A.PatStruct():
            for f in node.fields:
                walk_pattern(f.pattern, r, out, depth)