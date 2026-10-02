"""
测试获取燃料油FU2611的1分钟级别数据
"""
import akshare as ak
from datetime import datetime, timedelta
import traceback

def test_get_futures_data():
    """测试获取期货分钟数据"""
    try:
        symbol = "FU2611"
        period = "1"
        print(f"正在获取 {symbol} 的{period}分钟级别数据...")
        print(f"调用接口: ak.futures_zh_minute_sina(symbol={symbol}, period={period})")
        
        # 使用akshare获取期货分钟级别数据
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        print(f"\n返回类型: {type(df)}")
        
        if df is not None and not df.empty:
            print(f"数据条数: {len(df)}")
            print(f"列名: {df.columns.tolist()}")
            print(f"\n前5条数据:")
            print(df.head())
            print(f"\n后5条数据:")
            print(df.tail())
            
            # 检查数据格式
            print(f"\n数据类型:")
            print(df.dtypes)
            
            return True
        else:
            print("未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n获取数据失败: {str(e)}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("测试 akshare 获取期货数据")
    print("=" * 60)
    result = test_get_futures_data()
    print("\n" + "=" * 60)
    if result:
        print("测试成功！")
    else:
        print("测试失败！")
    print("=" * 60)
