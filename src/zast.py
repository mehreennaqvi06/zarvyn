from dataclasses import dataclass, field

from source import Span


# ---------- types as written in source ----------

@dataclass
class TypeName:
    """A type as it appears in source: int, string, MyStruct."""
    name: str
    span: Span


# ---------- expressions ----------

@dataclass
class IntLit:
    value: int
    span: Span


@dataclass
class FloatLit:
    value: float
    span: Span


@dataclass
class StrLit:
    value: str
    span: Span


@dataclass
class BoolLit:
    value: bool
    span: Span


@dataclass
class Name:
    """A reference to a variable or function by name."""
    name: str
    span: Span


@dataclass
class Unary:
    op: str
    operand: object
    span: Span


@dataclass
class Binary:
    op: str
    left: object
    right: object
    span: Span


@dataclass
class Call:
    callee: object
    args: list = field(default_factory=list)
    span: Span = None


@dataclass
class FieldAccess:
    target: object
    field_name: str
    span: Span = None


@dataclass
class Index:
    target: object
    index: object
    span: Span = None


@dataclass
class Assign:
    target: object
    value: object
    span: Span = None


# ---------- statements ----------

@dataclass
class Let:
    name: str
    mutable: bool
    declared_type: object
    value: object
    span: Span = None


@dataclass
class ExprStmt:
    expr: object
    span: Span = None


@dataclass
class Block:
    stmts: list = field(default_factory=list)
    span: Span = None


@dataclass
class If:
    cond: object
    then_block: object
    else_block: object = None
    span: Span = None


@dataclass
class While:
    cond: object
    body: object
    span: Span = None


@dataclass
class Return:
    value: object
    span: Span = None


@dataclass
class Break:
    span: Span = None


@dataclass
class Continue:
    span: Span = None


@dataclass
class Defer:
    expr: object
    span: Span = None


# ---------- items (top level) ----------

@dataclass
class Param:
    name: str
    declared_type: object
    span: Span = None


@dataclass
class FnDecl:
    name: str
    params: list = field(default_factory=list)
    return_type: object = None
    body: object = None
    span: Span = None


@dataclass
class StructField:
    name: str
    declared_type: object
    span: Span = None


@dataclass
class StructDecl:
    name: str
    fields: list = field(default_factory=list)
    span: Span = None


@dataclass
class Program:
    items: list = field(default_factory=list)

@dataclass
class For:
    var_name: str
    iterable: object
    body: object
    span: Span = None 

@dataclass
class EnumVariant:
    name: str
    payload_types: list = field(default_factory=list)
    span: Span = None


@dataclass
class EnumDecl:
    name: str
    variants: list = field(default_factory=list)
    span: Span = None

@dataclass
class FieldInit:
    name: str
    value: object
    span: Span = None


@dataclass
class StructLit:
    type_name: str
    fields: list = field(default_factory=list)
    span: Span = None