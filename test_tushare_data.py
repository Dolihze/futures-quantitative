"""
测试 tushare 获取期货分钟K线数据
"""
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 配置tushare token
TUSHARE_TOKEN = ''  # TODO: 请在 https://tushare.pro 注册后获取token并填入这里

# 测试参数
SYMBOL = 'FU2611'  # 合约代码
PERIOD = '1'  # 1分钟
DAYS = 30  # 获取最近30天的数据


def convert_to_tushare_symbol(symbol):
    """
    转换合约代码为tushare格式
    例如: FU2611 -> FU2611.SHF (上期所)
    """
    # 交易所映射规则
    exchange_map = {
        # 上海期货交易所 (SHF)
        'FU': 'SHF',  # 燃料油
        'RB': 'SHF',  # 螺纹钢
        'CU': 'SHF',  # 铜
        'AL': 'SHF',  # 铝
        'AU': 'SHF',  # 黄金
        'AG': 'SHF',  # 白银
        
        # 大连商品交易所 (DCE)
        'M': 'DCE',   # 豆粕
        'Y': 'DCE',   # 豆油
        'I': 'DCE',   # 铁矿石
        
        # 郑州商品交易所 (CZC)
        'CF': 'CZC',  # 棉花
        'SR': 'CZC',  # 白糖
        'TA': 'CZC',  # PTA
        
        # 中国金融期货交易所 (CFX)
        'IF': 'CFX',  # 沪深300股指期货
        'IC': 'CFX',  # 中证500股指期货
        'IH': 'CFX',  # 上证50股指期货
    }
    
    # 提取品种代码（去掉数字部分）
    variety_code = ''.join([c for c in symbol if c.isalpha()])
    
    # 获取对应的交易所代码
    exchange = exchange_map.get(variety_code.upper(), 'SHF')  # 默认使用SHF
    
    return f"{symbol}.{exchange}"


def test_tushare_data():
    """测试tushare数据获取"""
    
    print("=" * 80)
    print("测试 tushare 获取期货数据")
    print(f"合约代码: {SYMBOL}")
    print(f"数据周期: {PERIOD}分钟")
    print("=" * 80)
    print()
    
    # 检查token
    if not TUSHARE_TOKEN:
        print("❌ 错误: 请先配置 TUSHARE_TOKEN")
        print("请在 https://tushare.pro 注册后获取token")
        print("然后将token填入代码中的 TUSHARE_TOKEN 变量")
        return
    
    try:
        # 初始化tushare
        print("正在初始化 tushare...")
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        
        # 转换合约代码
        ts_symbol = convert_to_tushare_symbol(SYMBOL)
        print(f"转换后的tushare合约代码: {ts_symbol}")
        print()
        
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=DAYS)
        
        # 格式化日期为tushare格式
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"正在获取数据...")
        print(f"日期范围: {start_date_str} ~ {end_date_str}")
        print()
        
        # 使用tushare获取期货分钟级别数据
        df = pro.ft_mins(
            ts_code=ts_symbol,
            freq=f'{PERIOD}min',
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        if df is not None and not df.empty:
            print(f"✓ 成功获取数据，共 {len(df)} 条记录")
            print()
            print("数据列名:", df.columns.tolist())
            print()
            print("前5行数据:")
            print(df.head())
            print()
            print("后5行数据:")
            print(df.tail())
            print()
            
            # 数据统计
            print("价格统计:")
            print(f"  最高价: {df['high'].max()}")
            print(f"  最低价: {df['low'].min()}")
            print(f"  平均收盘价: {df['close'].mean():.2f}")
            print()
            
            # 时间范围
            df_sorted = df.sort_values('trade_time')
            print(f"时间范围:")
            print(f"  开始时间: {df_sorted.iloc[0]['trade_time']}")
            print(f"  结束时间: {df_sorted.iloc[-1]['trade_time']}")
            
        else:
            print("❌ 未获取到数据")
            print("可能原因:")
            print("  1. 合约代码不正确（可能已过期）")
            print("  2. tushare token权限不足")
            print("  3. 该时间段没有交易数据")
            print()
            print("建议:")
            print("  1. 检查合约代码是否正确")
            print("  2. 尝试获取其他合约的数据")
            print("  3. 在tushare提升账号积分")
            
    except Exception as e:
        print(f"❌ 获取数据失败: {str(e)}")
        print()
        print("详细错误信息:")
        import traceback
        traceback.print_exc()
        print()
        print("常见错误及解决方案:")
        print("  1. '请先设置token' -> 请确保已正确配置TUSHARE_TOKEN")
        print("  2. '权限不足' -> 请在tushare提升账号积分")
        print("  3. '合约代码不存在' -> 请检查合约代码格式是否正确")


if __name__ == '__main__':
    test_tushare_data()
