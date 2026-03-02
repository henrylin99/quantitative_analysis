import ast
import operator
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


class FactorExpressionEngine:
    """Safely evaluate custom factor expressions on a stock dataframe."""

    def __init__(self, allowed_columns: Optional[set[str]] = None):
        self.allowed_columns = allowed_columns or {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change_c",
            "pct_chg",
            "vol",
            "amount",
        }
        self.allowed_series_methods = {
            "pct_change",
            "shift",
            "diff",
            "rank",
            "rolling",
        }
        self.allowed_window_methods = {
            "mean",
            "std",
            "max",
            "min",
            "sum",
        }
        self.allowed_functions = {
            "abs": abs,
        }
        self.bin_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
        }
        self.unary_ops = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

    def evaluate(self, expression: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["factor_value"])
        if not expression or not str(expression).strip():
            raise ValueError("empty expression")

        parsed = ast.parse(expression, mode="eval")
        value = self._eval_node(parsed.body, df)

        if np.isscalar(value):
            value = pd.Series([float(value)] * len(df), index=df.index)

        if not isinstance(value, pd.Series):
            raise ValueError("expression must evaluate to a pandas Series")

        result = df.copy()
        result["factor_value"] = pd.to_numeric(value, errors="coerce")
        return result

    def _eval_node(self, node: ast.AST, df: pd.DataFrame):
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, df)
            right = self._eval_node(node.right, df)
            op = self.bin_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"unsupported operator: {type(node.op).__name__}")
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = self.unary_ops.get(type(node.op))
            if op is None:
                raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
            return op(self._eval_node(node.operand, df))

        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise ValueError("unsafe expression")
            if node.id not in self.allowed_columns:
                raise ValueError(f"column not allowed: {node.id}")
            if node.id not in df.columns:
                raise ValueError(f"column not found: {node.id}")
            return pd.to_numeric(df[node.id], errors="coerce")

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("only numeric constants are allowed")

        if isinstance(node, ast.Call):
            return self._eval_call(node, df)

        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    def _eval_call(self, node: ast.Call, df: pd.DataFrame):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in self.allowed_functions:
                raise ValueError(f"function not allowed: {func_name}")
            args = [self._as_scalar(self._eval_node(arg, df), "arg") for arg in node.args]
            kwargs = {
                kw.arg: self._as_scalar(self._eval_node(kw.value, df), kw.arg or "kwarg")
                for kw in node.keywords
            }
            return self.allowed_functions[func_name](*args, **kwargs)

        if not isinstance(node.func, ast.Attribute):
            raise ValueError("unsupported callable")

        method_name = node.func.attr
        if method_name.startswith("__"):
            raise ValueError("unsafe expression")

        target = self._eval_node(node.func.value, df)
        raw_args = [self._eval_node(arg, df) for arg in node.args]
        raw_kwargs: Dict[str, Any] = {
            kw.arg: self._eval_node(kw.value, df)
            for kw in node.keywords
        }

        if method_name == "rolling":
            if not isinstance(target, pd.Series):
                raise ValueError("rolling() must be called on a series")
            window = int(self._as_scalar(raw_args[0], "window")) if raw_args else None
            if window is None or window <= 0:
                raise ValueError("rolling window must be positive")
            min_periods = raw_kwargs.get("min_periods", window)
            min_periods = int(self._as_scalar(min_periods, "min_periods"))
            return target.rolling(window=window, min_periods=min_periods)

        if isinstance(target, pd.Series):
            if method_name not in self.allowed_series_methods:
                raise ValueError(f"series method not allowed: {method_name}")
            args = [self._as_scalar(arg, "arg") for arg in raw_args]
            kwargs = {k: self._as_scalar(v, k) for k, v in raw_kwargs.items()}
            return getattr(target, method_name)(*args, **kwargs)

        if hasattr(target, method_name):
            if method_name not in self.allowed_window_methods:
                raise ValueError(f"window method not allowed: {method_name}")
            args = [self._as_scalar(arg, "arg") for arg in raw_args]
            kwargs = {k: self._as_scalar(v, k) for k, v in raw_kwargs.items()}
            return getattr(target, method_name)(*args, **kwargs)

        raise ValueError(f"unsupported method target: {method_name}")

    def _as_scalar(self, value: Any, name: str):
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            return float(value)
        raise ValueError(f"{name} must be a numeric scalar")
