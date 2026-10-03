from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ty:
    name: str
    params: tuple = ()

    def __str__(self) -> str:
        if not self.params:
            return self.name
        inner = ", ".join(str(p) for p in self.params)
        return f"{self.name}<{inner}>"


INT = Ty("int")
FLOAT = Ty("float")
STRING = Ty("string")
BOOL = Ty("bool")
UNIT = Ty("unit")
ERROR = Ty("<error>")

PRIMITIVES = {"int": INT, "float": FLOAT, "string": STRING, "bool": BOOL, "unit": UNIT}


def fn_ty(params: list, ret) -> Ty:
    return Ty("fn", tuple(params) + (ret,))


def fn_params(t: Ty) -> tuple:
    return t.params[:-1]


def fn_return(t: Ty) -> Ty:
    return t.params[-1]


def compatible(a: Ty, b: Ty) -> bool:
    """ERROR unifies with everything, so one bad expression doesn't cascade."""
    if a is ERROR or b is ERROR:
        return True
    return a == b


@dataclass
class StructInfo:
    name: str
    fields: dict = field(default_factory=dict)   # name -> Ty
    order: list = field(default_factory=list)


@dataclass
class VariantInfo:
    name: str
    payload: list = field(default_factory=list)  # list[Ty]


@dataclass
class EnumInfo:
    name: str
    variants: dict = field(default_factory=dict)  # name -> VariantInfo
    order: list = field(default_factory=list)