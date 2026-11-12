"""策略 DSL：声明式选股规则（filter + order_by + top_n）的解析与求值。

方案 B 的核心模块。DSL 是封闭词表的规则文本，由本模块用 Python `ast`
白名单解析成闭包树后对当日截面 DataFrame 求值——不经过 `eval`，
LLM 只产出字符串，解释器是项目自身的受信任代码。

语法示例::

    filter:   rank(momentum_20) > 0.8 and pe_percentile < 0.3
    order_by: rank(momentum_20) * 0.6 - rank(pe_percentile) * 0.4

词表：
- 因子名（小写标识符，须在 factor 注册表中，解析期校验）
- 比较/逻辑：> >= < <= == != and or not
- 算术：+ - * /（禁止 **）
- 截面函数：rank(x)（百分位 [0,1]，升序）/ zscore(x) / quantile(x, n)（等频桶 0..n-1）

语义：filter 中任一因子 NaN 的股票剔除（不填 0）；order_by 降序、
NaN 排末尾；并列值按 ts_code 升序保证可复现。
"""
import ast
from typing import Any, Callable, Dict, List, Optional, Set

import pandas as pd

__all__ = ['DslError', 'DslProgram', 'parse_dsl']

# 截面函数名 -> (参数个数, 校验说明)
_CROSS_SECTION_FUNCS: Dict[str, int] = {
    'rank': 1,
    'zscore': 1,
    'quantile': 2,
}

# 允许的二元算术运算符（** 刻意缺席：防大数幂溢出）
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_CMPOPS = (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq)

_MAX_DEPTH = 12


class DslError(ValueError):
    """DSL 语法/词表非法（错误信息直接面向用户与 LLM，可自纠重试）。"""


def _fmt(node: ast.AST) -> str:
    return f"'{ast.dump(node)[:60]}...'" if node else '<空>'


class _Compiler:
    """把白名单校验通过的 ast 节点编译成 (df) -> pd.Series 的闭包树。"""

    def __init__(self, known_factors: Set[str]):
        self.known_factors = known_factors
        self.referenced: Set[str] = set()

    # -- 表达式 → 数值列 ------------------------------------------------

    def compile_numeric(self, node: ast.AST, depth: int = 0) -> Callable:
        """编译数值表达式；布尔表达式（filter 顶层之外的 BoolOp）拒绝。"""
        fn = self._compile(node, depth, boolean=False)
        return fn

    def compile_boolean(self, node: ast.AST, depth: int = 0) -> Callable:
        return self._compile(node, depth, boolean=True)

    def _compile(self, node: ast.AST, depth: int, boolean: bool) -> Callable:
        if depth > _MAX_DEPTH:
            raise DslError(f'表达式嵌套超过 {_MAX_DEPTH} 层，请精简')
        if isinstance(node, ast.Expression):
            return self._compile(node.body, depth, boolean)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                value = float(node.value)
                return lambda df: pd.Series(value, index=df.index)
            raise DslError(f'不支持的常量 {_fmt(node)}（只允许数字）')
        if isinstance(node, ast.Name):
            return self._compile_factor(node)
        if isinstance(node, ast.BinOp):
            return self._compile_binop(node, depth, boolean)
        if isinstance(node, ast.UnaryOp):
            return self._compile_unaryop(node, depth, boolean)
        if isinstance(node, ast.Call):
            return self._compile_call(node, depth)
        if isinstance(node, ast.Compare):
            if not boolean:
                raise DslError(
                    '比较表达式只能出现在 filter 中（order_by 须是数值表达式）'
                )
            return self._compile_compare(node, depth)
        if isinstance(node, ast.BoolOp):
            if not boolean:
                raise DslError(
                    'and/or 只能用于 filter（order_by 须是数值表达式）'
                )
            return self._compile_boolop(node, depth)
        raise DslError(
            f'不支持的语法 {_fmt(node)}；词表：因子名 / + - * / / '
            f'> >= < <= == != / and or not / rank / zscore / quantile'
        )

    def _compile_factor(self, node: ast.Name) -> Callable:
        name = node.id
        if name not in self.known_factors:
            raise DslError(
                f'未知因子: {name}（须先在因子注册表中存在；可用 list_factors 查询）'
            )
        self.referenced.add(name)

        def col(df: pd.DataFrame) -> pd.Series:
            if name not in df.columns:
                raise DslError(f'截面数据缺少因子列: {name}')
            return pd.to_numeric(df[name], errors='coerce')

        return col

    def _compile_binop(self, node: ast.BinOp, depth: int, boolean: bool) -> Callable:
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise DslError(
                f'不支持的运算符 {type(node.op).__name__}（只允许 + - * /）'
            )
        if boolean:
            raise DslError('算术表达式不能出现在 filter 的布尔位置')
        left = self._compile(node.left, depth + 1, boolean=False)
        right = self._compile(node.right, depth + 1, boolean=False)
        if isinstance(node.op, ast.Add):
            return lambda df: left(df) + right(df)
        if isinstance(node.op, ast.Sub):
            return lambda df: left(df) - right(df)
        if isinstance(node.op, ast.Mult):
            return lambda df: left(df) * right(df)
        return lambda df: left(df) / right(df)

    def _compile_unaryop(self, node: ast.UnaryOp, depth: int, boolean: bool) -> Callable:
        if isinstance(node.op, ast.USub):
            operand = self._compile(node.operand, depth + 1, boolean=False)
            return lambda df: -operand(df)
        if isinstance(node.op, ast.Not):
            if not boolean:
                raise DslError('not 只能用于 filter')
            operand = self._compile(node.operand, depth + 1, boolean=True)
            return lambda df: ~operand(df)
        raise DslError(f'不支持的运算符 {type(node.op).__name__}')

    def _compile_call(self, node: ast.Call, depth: int) -> Callable:
        if not isinstance(node.func, ast.Name) or node.func.id not in _CROSS_SECTION_FUNCS:
            fname = getattr(node.func, 'id', _fmt(node))
            raise DslError(
                f'未知函数: {fname}（截面函数仅支持 '
                f'{" / ".join(_CROSS_SECTION_FUNCS)}）'
            )
        fname = node.func.id
        nargs = _CROSS_SECTION_FUNCS[fname]
        if len(node.args) != nargs or node.keywords:
            raise DslError(
                f'{fname} 需要 {nargs} 个位置参数'
                f'（quantile(x, n) 的 n 为 2~100 的整数）'
            )
        arg_fns = [self._compile(a, depth + 1, boolean=False) for a in node.args]
        if fname == 'quantile':
            n_val = node.args[1]
            if not (isinstance(n_val, ast.Constant)
                    and isinstance(n_val.value, int)
                    and not isinstance(n_val.value, bool)
                    and 2 <= n_val.value <= 100):
                raise DslError('quantile 第二个参数须是 2~100 的整数常量')

        def call(df: pd.DataFrame) -> pd.Series:
            series = arg_fns[0](df)
            if fname == 'rank':
                # 升序百分位 [0,1]：值越大 rank 越大
                return series.rank(pct=True)
            if fname == 'zscore':
                std = series.std()
                if std == 0 or pd.isna(std):
                    return series * 0.0
                return (series - series.mean()) / std
            # quantile：等频分桶编号 0..n-1
            n = node.args[1].value
            return pd.Series(
                pd.qcut(series, q=n, labels=False, duplicates='drop'),
                index=df.index,
            ).astype(float)

        return call

    def _compile_compare(self, node: ast.Compare, depth: int) -> Callable:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise DslError('不支持链式比较（如 a < b < c），请拆成 and 连接')
        if not isinstance(node.ops[0], _ALLOWED_CMPOPS):
            raise DslError(f'不支持的比较运算符 {type(node.ops[0]).__name__}')
        left = self._compile(node.left, depth + 1, boolean=False)
        right = self._compile(node.comparators[0], depth + 1, boolean=False)
        op = node.ops[0]
        if isinstance(op, ast.Gt):
            combine = lambda l, r: l > r  # noqa: E731
        elif isinstance(op, ast.GtE):
            combine = lambda l, r: l >= r  # noqa: E731
        elif isinstance(op, ast.Lt):
            combine = lambda l, r: l < r  # noqa: E731
        elif isinstance(op, ast.LtE):
            combine = lambda l, r: l <= r  # noqa: E731
        elif isinstance(op, ast.Eq):
            combine = lambda l, r: l == r  # noqa: E731
        else:
            combine = lambda l, r: l != r  # noqa: E731
        return lambda df: combine(left(df), right(df))

    def _compile_boolop(self, node: ast.BoolOp, depth: int) -> Callable:
        value_fns = [self._compile(v, depth + 1, boolean=True) for v in node.values]
        is_and = isinstance(node.op, ast.And)

        def boolop(df: pd.DataFrame) -> pd.Series:
            result = value_fns[0](df)
            for fn in value_fns[1:]:
                other = fn(df)
                result = (result & other) if is_and else (result | other)
            return result

        return boolop


class DslProgram:
    """已编译的 DSL 策略：持有 filter/order_by 闭包与引用因子集合。"""

    def __init__(self, filter_fn: Optional[Callable], order_fn: Callable,
                 referenced: Set[str], filter_text: str, order_text: str):
        self._filter_fn = filter_fn
        self._order_fn = order_fn
        self.filter_text = filter_text
        self.order_text = order_text
        self._referenced = referenced

    @property
    def referenced_factors(self) -> Set[str]:
        """DSL 引用的全部因子名（覆盖校验复用）。"""
        return set(self._referenced)

    def describe(self) -> Dict[str, Any]:
        return {
            'filter': self.filter_text,
            'order_by': self.order_text,
            'referenced_factors': sorted(self._referenced),
        }

    def select(self, cross_section: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
        """对当日截面执行 过滤 → order_by 降序 → top N。

        入参 cross_section：index=ts_code、列=因子名的宽表（与
        calculate_factor_scores 输出同构）。返回带 ts_code / composite_score /
        rank / percentile_rank 列的 DataFrame，可直通 rank_stocks。
        """
        if cross_section is None or cross_section.empty:
            return pd.DataFrame()
        df = cross_section
        if self._filter_fn is not None:
            try:
                mask = self._filter_fn(df).fillna(False).astype(bool)
            except DslError:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一转 DslError 语义
                raise DslError(f'filter 求值失败: {exc}') from exc
            df = df[mask]
            if df.empty:
                return pd.DataFrame()

        try:
            scores = self._order_fn(df)
        except DslError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DslError(f'order_by 求值失败: {exc}') from exc

        result = pd.DataFrame({
            'ts_code': df.index,
            'composite_score': pd.to_numeric(scores, errors='coerce').values,
        })
        # NaN 排末尾 + 并列按 ts_code 升序：保证同一截面结果可复现
        result = result.sort_values(
            ['composite_score', 'ts_code'],
            ascending=[False, True],
            na_position='last',
        ).head(int(top_n))
        result['rank'] = range(1, len(result) + 1)
        result['percentile_rank'] = (
            result['composite_score'].rank(pct=True) * 100
        )
        return result.reset_index(drop=True)


def parse_dsl(filter_text: str, order_by_text: str,
              known_factors: Set[str]) -> DslProgram:
    """解析并编译一条 DSL 策略；任何非法输入抛 DslError（fail-fast）。

    known_factors 是允许引用的因子 id 集合（由调用方从因子注册表取）。
    """
    filter_text = (filter_text or '').strip()
    order_by_text = (order_by_text or '').strip()
    if not order_by_text:
        raise DslError('order_by 不能为空（至少需要一个因子或截面函数表达式）')
    if len(order_by_text) > 500 or len(filter_text) > 500:
        raise DslError('filter / order_by 长度须 ≤500 字符')

    compiler = _Compiler(set(known_factors))
    try:
        filter_fn = None
        if filter_text:
            filter_tree = ast.parse(filter_text, mode='eval')
            filter_fn = compiler.compile_boolean(filter_tree)
        order_tree = ast.parse(order_by_text, mode='eval')
        order_fn = compiler.compile_numeric(order_tree)
    except SyntaxError as exc:
        raise DslError(
            f'DSL 语法错误: {exc.msg}（行 {exc.lineno} 列 {exc.offset}）'
        ) from exc

    return DslProgram(filter_fn, order_fn, compiler.referenced,
                      filter_text, order_by_text)
