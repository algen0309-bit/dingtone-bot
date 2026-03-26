"""
math_solver.py - Parse and evaluate math equations from the Dingtone game.

Statements are displayed as strings like "1+8=11", "5+2>8", "15÷3=5", "3+3>=6".
Supports equality (=) and inequality (>, <, >=, <=) operators.
Returns True if the statement is mathematically correct, False otherwise.
"""

import ast
import operator as op
import re

# Unicode symbol → Python operator replacement table
_REPLACEMENTS = [
    ('\u00d7', '*'),    # × (multiplication sign)
    ('\u00f7', '/'),    # ÷ (division sign)
    ('\u2212', '-'),    # − (minus sign, U+2212)
    ('\u2013', '-'),    # – (en dash, sometimes used as minus)
]

# Allowed binary operators
_BINOPS = {
    ast.Add:      op.add,
    ast.Sub:      op.sub,
    ast.Mult:     op.mul,
    ast.Div:      op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod:      op.mod,
    ast.Pow:      op.pow,
}

# Allowed unary operators
_UNOPS = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

# Matches equations (=) and inequalities (>=, <=, >, <)
# Group 1 = left-hand side, group 2 = operator, group 3 = right-hand side
_EQ_RE = re.compile(r'^(.+?)(>=|<=|>|<|=)(.+)$')

_CMP_OPS = {
    '=':  lambda a, b: abs(a - b) < 1e-9,
    '>':  lambda a, b: a > b,
    '<':  lambda a, b: a < b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
}


def normalize(text: str) -> str:
    """Replace Unicode math symbols with Python-parseable equivalents."""
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    return text


def _eval_node(node):
    """Recursively evaluate an AST node. Only arithmetic is allowed."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Non-numeric constant: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        fn = _BINOPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
        return fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        fn = _UNOPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return fn(_eval_node(node.operand))
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def safe_eval(expr: str) -> float:
    """Safely evaluate an arithmetic expression string. No eval()."""
    tree = ast.parse(expr.strip(), mode='eval')
    return _eval_node(tree)


def solve(equation_text: str) -> bool:
    """
    Determine whether a math statement is correct.

    Args:
        equation_text: e.g. "1+8=11", "5+2>8", "15÷3=5", "3+3>=6"

    Returns:
        True  if the statement is mathematically correct
        False if it is incorrect

    Raises:
        ValueError if the text cannot be parsed
    """
    text = normalize(equation_text.strip())
    m = _EQ_RE.match(text)
    if not m:
        raise ValueError(f"No operator found in: {text!r}")
    lhs = safe_eval(m.group(1))
    cmp_op = _CMP_OPS[m.group(2)]
    rhs = safe_eval(m.group(3))
    return cmp_op(lhs, rhs)


if __name__ == '__main__':
    # Quick self-test
    tests = [
        # equalities
        ("1+8=9",    True),
        ("1+8=11",   False),
        ("15÷3=5",   True),
        ("7×8=56",   True),
        ("7×8=55",   False),
        ("20-4=16",  True),
        ("20-4=15",  False),
        ("2+2×2=6",  True),    # operator precedence: 2+(2*2)=6
        ("100÷4=25", True),
        # inequalities
        ("5+2>8",    False),   # 7 > 8 is False
        ("5+2>6",    True),    # 7 > 6 is True
        ("3+3>=6",   True),    # 6 >= 6 is True
        ("3+3>=7",   False),   # 6 >= 7 is False
        ("3+3<=5",   False),   # 6 <= 5 is False
        ("3+3<=6",   True),    # 6 <= 6 is True
        ("10<5×3",   True),    # 10 < 15 is True
        ("10<5×2",   False),   # 10 < 10 is False
    ]
    all_pass = True
    for eq, expected in tests:
        result = solve(eq)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"[{status}] solve({eq!r}) = {result}  (expected {expected})")
    print("\nAll tests passed!" if all_pass else "\nSome tests FAILED!")
