/**
 * 国内期货常见品种（品种代码 -> 中文名），用于量化监控「品种白名单」的多选下拉。
 *
 * 为什么前端内置：白名单是按合约代码前缀（rb2610 -> rb）匹配的，选项不依赖登录状态和柜台查询，
 * 监控页没有交易账号会话时也能选。表里没有的品种，下拉框允许直接输入代码创建（见 Monitor 页）。
 * 代码一律小写，和后端 copy_trading._product_of 的比较口径一致。
 */
export const FUTURES_PRODUCTS = [
  // 上期所 SHFE
  { value: 'cu', label: '沪铜' }, { value: 'al', label: '沪铝' }, { value: 'zn', label: '沪锌' },
  { value: 'pb', label: '沪铅' }, { value: 'ni', label: '沪镍' }, { value: 'sn', label: '沪锡' },
  { value: 'ao', label: '氧化铝' }, { value: 'ss', label: '不锈钢' },
  { value: 'au', label: '黄金' }, { value: 'ag', label: '白银' },
  { value: 'rb', label: '螺纹钢' }, { value: 'hc', label: '热轧卷板' }, { value: 'wr', label: '线材' },
  { value: 'fu', label: '燃料油' }, { value: 'bu', label: '沥青' }, { value: 'ru', label: '橡胶' },
  { value: 'br', label: '丁二烯橡胶' }, { value: 'sp', label: '纸浆' }, { value: 'ad', label: '铸造铝合金' },
  // 能源中心 INE
  { value: 'sc', label: '原油' }, { value: 'lu', label: '低硫燃料油' }, { value: 'nr', label: '20号胶' },
  { value: 'bc', label: '国际铜' }, { value: 'ec', label: '集运指数（欧线）' },
  // 大商所 DCE
  { value: 'a', label: '豆一' }, { value: 'b', label: '豆二' }, { value: 'm', label: '豆粕' },
  { value: 'y', label: '豆油' }, { value: 'p', label: '棕榈油' }, { value: 'c', label: '玉米' },
  { value: 'cs', label: '玉米淀粉' }, { value: 'jd', label: '鸡蛋' }, { value: 'lh', label: '生猪' },
  { value: 'rr', label: '粳米' }, { value: 'i', label: '铁矿石' }, { value: 'j', label: '焦炭' },
  { value: 'jm', label: '焦煤' }, { value: 'l', label: '塑料' }, { value: 'v', label: 'PVC' },
  { value: 'pp', label: '聚丙烯' }, { value: 'eg', label: '乙二醇' }, { value: 'eb', label: '苯乙烯' },
  { value: 'pg', label: '液化石油气' }, { value: 'lg', label: '原木' }, { value: 'bz', label: '纯苯' },
  // 郑商所 CZCE
  { value: 'cf', label: '棉花' }, { value: 'cy', label: '棉纱' }, { value: 'sr', label: '白糖' },
  { value: 'ta', label: 'PTA' }, { value: 'ma', label: '甲醇' }, { value: 'fg', label: '玻璃' },
  { value: 'sa', label: '纯碱' }, { value: 'ur', label: '尿素' }, { value: 'sf', label: '硅铁' },
  { value: 'sm', label: '锰硅' }, { value: 'pf', label: '短纤' }, { value: 'pk', label: '花生' },
  { value: 'ap', label: '苹果' }, { value: 'cj', label: '红枣' }, { value: 'oi', label: '菜籽油' },
  { value: 'rm', label: '菜粕' }, { value: 'rs', label: '菜籽' }, { value: 'wh', label: '强麦' },
  { value: 'pm', label: '普麦' }, { value: 'ri', label: '早籼稻' }, { value: 'lr', label: '晚籼稻' },
  { value: 'jr', label: '粳稻' }, { value: 'pr', label: '瓶片' }, { value: 'px', label: '对二甲苯' },
  { value: 'sh', label: '烧碱' },
  // 中金所 CFFEX
  { value: 'if', label: '沪深300股指' }, { value: 'ih', label: '上证50股指' },
  { value: 'ic', label: '中证500股指' }, { value: 'im', label: '中证1000股指' },
  { value: 'ts', label: '2年期国债' }, { value: 'tf', label: '5年期国债' },
  { value: 't', label: '10年期国债' }, { value: 'tl', label: '30年期国债' },
  // 广期所 GFEX
  { value: 'si', label: '工业硅' }, { value: 'lc', label: '碳酸锂' }, { value: 'ps', label: '多晶硅' },
  { value: 'pt', label: '铂' }, { value: 'pd', label: '钯' }
]
