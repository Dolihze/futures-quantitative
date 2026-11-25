"""接口响应契约（pydantic）。

作用：
  1. 生成 OpenAPI（scripts/gen-openapi.py -> openapi.json），再生成前端类型，前后端字段不再靠人工对齐。
  2. tests/test_contract.py 用真实响应校验这些模型：后端改了字段而没同步这里，测试会失败。

这里的模型只描述响应，运行时不参与校验、不影响路由行为。
extra="allow"：没有逐字段列出的部分（如回测的 stats 明细）不会让校验失败，列出来的字段才是契约。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# 通用外壳
# ---------------------------------------------------------------------------
class ApiResult(_Model):
    """业务接口统一外壳。失败时 success=false + message；部分接口还带下面的标志。"""
    success: bool
    message: Optional[str] = None
    expired: Optional[bool] = None       # reviewId / depthId 已失效（后端重启）
    exists: Optional[bool] = None        # 409：同名文件已存在，需 overwrite 确认
    fileMissing: Optional[bool] = None   # 文件已被移动或删除


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------
class BrokerItem(_Model):
    value: str
    name: str
    tag: Optional[str] = None


class BrokerGroup(_Model):
    label: str
    items: list[BrokerItem]


class SavedCredentials(_Model):
    saved: bool
    broker: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class LoginResult(ApiResult):
    data: Optional[Any] = None
    password_saved: Optional[bool] = None


# ---------------------------------------------------------------------------
# 量化回测
# ---------------------------------------------------------------------------
class BacktestContract(_Model):
    """本地历史行情库里已导入的合约（回测页下拉用）。"""
    symbol: str
    name: str
    label: str
    dayCount: int
    start: str
    end: str
    tickCount: int


class BacktestContracts(ApiResult):
    default: str
    data: list[BacktestContract]


class KlineBar(_Model):
    time: str  # 'YYYY-MM-DD HH:mm:ss'
    open: float
    high: float
    low: float
    close: float
    volume: float


class BacktestKline(ApiResult):
    data: list[KlineBar]
    symbol: str
    symbolName: str
    count: int


class BacktestCoverage(_Model):
    availableDays: int
    requestedDays: int
    usedDays: int
    truncated: bool
    dataFrom: Optional[str] = None
    dataTo: Optional[str] = None


class EquityPoint(_Model):
    time: str
    equity: float
    tradeNo: int


class BacktestOverviewItem(_Model):
    id: str
    name: str
    description: str
    category: str
    period: str
    stats: Optional[dict[str, Any]] = None
    equity: list[EquityPoint]
    error: Optional[str] = None
    coverage: Optional[BacktestCoverage] = None


class BacktestOverview(ApiResult):
    symbol: str
    symbolName: str
    days: int
    lots: int
    availableDays: int
    data: list[BacktestOverviewItem]


class StrategyInfo(_Model):
    id: str
    name: str
    description: str
    category: str
    period: str
    params: dict[str, Any]


class BacktestRun(ApiResult):
    strategy: StrategyInfo
    symbol: str
    symbolName: str
    lots: int
    days: int
    period: str
    initialCapital: float
    stats: dict[str, Any]
    trades: list[dict[str, Any]]
    equity: list[EquityPoint]
    kline: list[KlineBar]
    coverage: BacktestCoverage


# ---------------------------------------------------------------------------
# 交易复盘
# ---------------------------------------------------------------------------
class ReviewOpenResult(ApiResult):
    """上传 / 打开交易记录文件的响应（两者结构一致）。"""
    reviewId: str
    filename: str
    products: list[str]
    start: str
    end: str
    tradeCount: int
    hasFee: bool
    days: list[str]
    warnings: list[str]
    saved: Optional[bool] = None
    overwritten: Optional[bool] = None


class ReviewFile(_Model):
    name: str
    size: int
    mtime: int  # 秒级时间戳


class ReviewFiles(ApiResult):
    dir: str
    files: list[ReviewFile]


class ReviewFileDetail(ReviewFile):
    products: Optional[list[str]] = None
    days: Optional[list[str]] = None
    tradeCount: Optional[int] = None
    start: Optional[str] = None
    end: Optional[str] = None
    hasFee: Optional[bool] = None
    error: Optional[str] = None


class ReviewFilesDetail(ApiResult):
    dir: str
    files: list[ReviewFileDetail]


class SkippedFile(_Model):
    name: str
    error: str


class ReviewOverviewStats(_Model):
    totalPnl: float
    grossPnl: float
    totalFee: float
    closeCount: int
    winCount: int
    lossCount: int
    winRate: float
    maxDrawdown: float
    maxProfit: float
    maxLoss: float
    profitLossRatio: float
    tradingDays: int
    winDays: int
    lossDays: int
    dayWinRate: float
    volume: float
    turnover: float


class ReviewOverviewDay(_Model):
    day: str
    pnl: float
    grossPnl: float
    fee: float
    closeCount: int
    winCount: int
    lossCount: int
    volume: float
    cumPnl: float


class ReviewOverviewProduct(_Model):
    product: str
    pnl: float
    volume: float
    turnover: float
    turnoverRatio: float
    closeCount: int
    winCount: int
    lossCount: int
    winRate: float


class ReviewOverview(ApiResult):
    reviewId: str
    fileCount: int
    skipped: list[SkippedFile]
    warnings: list[str]
    allStart: str
    allEnd: str
    hasFee: bool
    days: list[ReviewOverviewDay]
    products: list[ReviewOverviewProduct]
    stats: ReviewOverviewStats
    start: str
    end: str


class ReviewDayTrades(ApiResult):
    day: str
    days: list[str]
    symbols: list[dict[str, Any]]


class ReviewDayKline(ApiResult):
    available: bool
    data: list[KlineBar]
    symbol: Optional[str] = None
    day: Optional[str] = None
    period: Optional[int] = None
    count: Optional[int] = None
    partial: Optional[bool] = None


# ---------------------------------------------------------------------------
# 深度行情
# ---------------------------------------------------------------------------
class DepthOpenResult(ApiResult):
    depthId: str
    filename: str
    symbol: str
    name: str
    tickCount: int
    levels: int
    days: list[str]
    start: str
    end: str
    hasBs: bool
    warnings: list[str]
    fileCount: Optional[int] = None
    saved: Optional[bool] = None
    overwritten: Optional[bool] = None
    savedName: Optional[str] = None
    originalName: Optional[str] = None


class DepthArchiveItem(_Model):
    label: str      # 压缩包内路径，如 202611/20261102/fu2611.zip
    status: str     # imported / overwritten / skipped / failed
    name: str       # 保存后的文件名（合约名_YYYYMMDD.csv），失败时可能为空
    message: str
    symbol: str


class DepthArchiveResult(ApiResult):
    products: list[str]
    perProduct: dict[str, int]   # 每个品种命中的合约文件数（0 表示压缩包里没有该品种）
    matched: int
    imported: int
    overwritten: int
    skipped: int
    failed: int
    contracts: list[str]
    items: list[DepthArchiveItem]
    originalName: Optional[str] = None


class DepthArchiveStart(ApiResult):
    taskId: str
    products: list[str]
    originalName: str


class DepthArchiveTask(ApiResult):
    taskId: str
    status: str     # running / done / error
    products: list[str]
    originalName: str
    done: int       # 已处理的合约文件数
    total: int      # 命中的合约文件总数（扫描完成前为 0）
    current: str    # 正在处理的压缩包内路径
    message: str    # status=error 时的原因
    result: Optional[DepthArchiveResult] = None


class DepthContractFile(_Model):
    name: str
    size: int
    mtime: int
    tickCount: int
    days: list[str]
    start: str
    end: str
    hasBs: bool


class DepthContract(_Model):
    symbol: str
    name: str
    fileCount: int
    files: list[DepthContractFile]
    tickCount: int
    days: list[str]
    dayCount: int
    start: str
    end: str
    hasBs: bool
    mtime: int
    size: int


class DepthUnrecognized(_Model):
    name: str
    size: int
    mtime: int
    error: str


class DepthContracts(ApiResult):
    dir: str
    contracts: list[DepthContract]
    unrecognized: list[DepthUnrecognized]


class DepthFiles(ApiResult):
    dir: str
    files: list[ReviewFile]


# ---------------------------------------------------------------------------
# 契约注册表：(HTTP 方法, 路由规则) -> 响应模型。
# 未登记的接口（实盘交易、跟单等，字段由 CTP 决定、变化频繁）在 OpenAPI 里仍会出现，只是响应为通用 ApiResult。
# ---------------------------------------------------------------------------
RESPONSES: dict[tuple[str, str], type[BaseModel]] = {
    ("GET", "/api/brokers"): BrokerGroup,   # 实际返回 list[BrokerGroup]，见 gen-openapi 的特殊处理
    ("GET", "/api/credentials"): SavedCredentials,
    ("POST", "/api/login"): LoginResult,
    ("GET", "/api/backtest/contracts"): BacktestContracts,
    ("GET", "/api/backtest/kline"): BacktestKline,
    ("GET", "/api/backtest/overview"): BacktestOverview,
    ("GET", "/api/backtest/run"): BacktestRun,
    ("POST", "/api/review/upload"): ReviewOpenResult,
    ("POST", "/api/review/open"): ReviewOpenResult,
    ("GET", "/api/review/files"): ReviewFiles,
    ("GET", "/api/review/files/detail"): ReviewFilesDetail,
    ("GET", "/api/review/overview"): ReviewOverview,
    ("GET", "/api/review/day-trades"): ReviewDayTrades,
    ("GET", "/api/review/day-kline"): ReviewDayKline,
    ("POST", "/api/depth/upload"): DepthOpenResult,
    ("POST", "/api/depth/upload-archive"): DepthArchiveStart,
    ("GET", "/api/depth/archive-task"): DepthArchiveTask,
    ("POST", "/api/depth/open"): DepthOpenResult,
    ("POST", "/api/depth/open-contract"): DepthOpenResult,
    ("GET", "/api/depth/contracts"): DepthContracts,
    ("GET", "/api/depth/files"): DepthFiles,
}
