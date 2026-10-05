"""
测试akshare获取K线数据的实际能力
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def test_data_range():
    """测试akshare能获取多少天的数据"""
    symbol = "FU2611"
    period = "5"  # 5分钟线
    
    print(f"测试合约: {symbol}")
    print(f"测试周期: {period}分钟")
    print("=" * 60)
    
    try:
        # 获取数据
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        if df is not None and not df.empty:
            print(f"\n获取到数据条数: {len(df)}")
            print(f"列名: {df.columns.tolist()}")
            
            # 转换datetime列
            df['datetime'] = pd.to_datetime(df['datetime'])
            
            # 获取最早和最新时间
            earliest = df['datetime'].min()
            latest = df['datetime'].max()
            
            print(f"\n最早数据时间: {earliest}")
            print(f"最新数据时间: {latest}")
            
            # 计算时间跨度
            time_span = latest - earliest
            print(f"时间跨度: {time_span}")
            print(f"时间跨度（天数）: {time_span.days} 天")
            print(f"时间跨度（小时）: {time_span.total_seconds() / 3600:.2f} 小时")
            
            # 按天统计数据量
            df['date'] = df['datetime'].dt.date
            daily_counts = df.groupby('date').size()
            print(f"\n每日数据条数:")
            print(daily_counts)
            
            print(f"\n数据示例（前5行）:")
            print(df.head())
            
            print(f"\n数据示例（后5行）:")
            print(df.tail())
            
        else:
            print("未获取到数据")
            
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_data_range()
