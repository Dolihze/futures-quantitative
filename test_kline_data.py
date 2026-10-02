"""
测试获取燃料油FU2611的1分钟级别数据
"""
import akshare as ak
from datetime import datetime, timedelta

def test_get_futures_data():
    """测试获取期货分钟数据"""
    try:
        symbol = "FU2611"
        print(f"正在获取 {symbol} 的1分钟级别数据...")
        
        # 使用akshare获取期货分钟级别数据
        df = ak.futures_zh_minute_sina(symbol=symbol, period="1")
        
        if df is not None and not df.empty:
            print(f"\n数据获取成功！")
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
        print(f"获取数据失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    test_get_futures_data()
