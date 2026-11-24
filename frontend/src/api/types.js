/**
 * 前后端接口契约（JSDoc typedef）。
 *
 * 【响应类型】全部来自后端生成：backend/schemas.py（pydantic）-> openapi.json -> types/generated/api.d.ts。
 * 后端改了响应字段：改 schemas.py，运行 `npm run api:types`，前端用到旧字段的地方在 `npm run typecheck` 时报错。
 * tests/test_contract.py 用真实响应校验 schemas.py，所以 schemas.py 和后端实际行为也不会悄悄脱节。
 *
 * 【请求类型】（params / payload）后端不声明，仍在这里手写，改请求参数时同步。
 * 本文件只有类型，没有运行时代码。
 */

/** @typedef {import('../../types/generated/api').components['schemas']} Schemas */

// ---------------------------------------------------------------------------
// 响应（生成）
// ---------------------------------------------------------------------------
/** @typedef {Schemas['ApiResult']} ApiResult */
/** @typedef {Schemas['BrokerGroup']} BrokerGroup */
/** @typedef {Schemas['BrokerItem']} BrokerItem */
/** @typedef {Schemas['SavedCredentials']} SavedCredentials */
/** @typedef {Schemas['LoginResult']} LoginResult */

/** @typedef {Schemas['BacktestContracts']} BacktestContracts */
/** @typedef {Schemas['BacktestContract']} BacktestContract */
/** @typedef {Schemas['BacktestKline']} BacktestKline */
/** @typedef {Schemas['KlineBar']} BacktestKlineBar */
/** @typedef {Schemas['BacktestCoverage']} BacktestCoverage */
/** @typedef {Schemas['BacktestOverviewItem']} BacktestOverviewItem */
/** @typedef {Schemas['BacktestOverview']} BacktestOverview */
/** @typedef {Schemas['BacktestRun']} BacktestRun */

/** 上传 / 打开交易记录文件的响应（两者结构一致） */
/** @typedef {Schemas['ReviewOpenResult']} ReviewOpenResult */
/** @typedef {Schemas['ReviewFile']} ReviewFile */
/** @typedef {Schemas['ReviewFiles']} ReviewFiles */
/** @typedef {Schemas['ReviewFileDetail']} ReviewFileDetail */
/** @typedef {Schemas['ReviewFilesDetail']} ReviewFilesDetail */
/** @typedef {Schemas['ReviewOverview']} ReviewOverview */
/** @typedef {Schemas['ReviewDayTrades']} ReviewDayTrades */
/** @typedef {Schemas['ReviewDayKline']} ReviewDayKline */

/** @typedef {Schemas['DepthOpenResult']} DepthOpenResult */
/** @typedef {Schemas['DepthContract']} DepthContract */
/** @typedef {Schemas['DepthContractFile']} DepthContractFile */
/** @typedef {Schemas['DepthContracts']} DepthContractsResult */
/** @typedef {Schemas['DepthFiles']} DepthFiles */

// ---------------------------------------------------------------------------
// 响应（手写）：后端按 pandas / numpy 动态拼装、没有登记响应模型的结构，仅用于前端组件的 props 类型
// ---------------------------------------------------------------------------

/**
 * /api/depth/kline 返回的 K 线（含 tick 区间，供回放定位）。
 * @typedef {Object} DepthKlineBar
 * @property {string} time
 * @property {number} open
 * @property {number} high
 * @property {number} low
 * @property {number} close
 * @property {number} volume
 * @property {number} [position]  持仓量
 * @property {number} [ticks]
 * @property {number} [ti0]       该 K 线首个 tick 序号
 * @property {number} [ti1]       该 K 线末个 tick 序号
 * @property {number} [bs]
 */

/**
 * @typedef {Object} DepthFootprintLevel
 * @property {number} price
 * @property {number} buy
 * @property {number} sell
 * @property {number} neutral
 */

/**
 * /api/depth/footprint 返回的 K 线（含每个价位的成交分布）。
 * @typedef {Object} DepthFootprintBar
 * @property {string} time
 * @property {number} open
 * @property {number} high
 * @property {number} low
 * @property {number} close
 * @property {number} volume
 * @property {DepthFootprintLevel[]} levels
 */

/**
 * @typedef {Object} DepthBigOrder
 * @property {number} bar     所在 K 线序号
 * @property {number} index   tick 序号
 * @property {number} price
 * @property {number} volume
 * @property {number} side  >0 买方主动，<0 卖方主动
 * @property {number|string} bs
 */

// ---------------------------------------------------------------------------
// 请求（手写）
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} LoginPayload
 * @property {string} broker
 * @property {string} username
 * @property {string} password
 * @property {boolean} [remember]
 */

/**
 * @typedef {Object} OrderPayload
 * @property {string} symbol  形如 ag2612.SHFE
 * @property {'open_long'|'open_short'|'close_long'|'close_short'} action
 * @property {number} price
 * @property {number} volume
 */

/**
 * @typedef {Object} ReversePayload
 * @property {string} symbol
 * @property {'多'|'空'} fromSide
 * @property {number} closePrice
 * @property {number} openPrice
 * @property {number} volume
 */

/**
 * @typedef {Object} BacktestParams
 * @property {string} [symbol]   合约代码（本地行情库里已导入的合约，如 fu2611）
 * @property {number} [days]
 * @property {number} [lots]
 * @property {string} [strategy] 仅 runBacktest
 * @property {string} [period]   仅 getBacktestKline：'1'|'5'|'15'|'30'|'60'
 */

/**
 * @typedef {Object} ReviewCurveParams
 * @property {string} reviewId
 * @property {string} [products]  逗号分隔
 * @property {string} [start]
 * @property {string} [end]
 * @property {0|1} [fee]
 */

/**
 * @typedef {Object} ReviewOverviewParams
 * @property {0|1} [fee]
 * @property {string} [start]
 * @property {string} [end]
 */

/**
 * @typedef {Object} DepthChartParams
 * @property {string} depthId
 * @property {number} [period]    1/5/15/30/60/1440
 * @property {string} [day]
 * @property {number} [bigOrder]  仅足迹图
 */

export {}
