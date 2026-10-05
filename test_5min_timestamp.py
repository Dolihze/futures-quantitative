"""
测试akshare获取5分钟K线数据的时间戳
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def test_5min_kline():
    """测试5分钟K线的时间戳是否正确"""
    symbol = "FU2611"
    period = "5"  # 5分钟线
    
    print(f"测试合约: {symbol}")
    print(f"测试周期: {period}分钟")
    print("=" * 80)
    
    try:
        # 获取数据
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        if df is not None and not df.empty:
            print(f"\n获取到数据条数: {len(df)}")
            
            # 转换datetime列
            df['datetime'] = pd.to_datetime(df['datetime'])
            
            # 只看最近一天的数据
            latest_date = df['datetime'].dt.date.max()
            latest_day_data = df[df['datetime'].dt.date == latest_date]
            
            print(f"\n最新交易日: {latest_date}")
            print(f"该日数据条数: {len(latest_day_data)}")
            
            # 显示时间戳（只看前20条和后20条）
            print(f"\n前20条数据时间戳:")
            for i, row in latest_day_data.head(20).iterrows():
                print(f"  {row['datetime']}")
            
            print(f"\n后20条数据时间戳:")
            for i, row in latest_day_data.tail(20).iterrows():
                print(f"  {row['datetime']}")
            
            # 检查时间间隔
            print(f"\n检查时间间隔（前10条相邻数据的时间差）:")
            times = latest_day_data['datetime'].head(10).tolist()
            for i in range(1, len(times)):
                time_diff = (times[i] - times[i-1]).total_seconds() / 60
                print(f"  {times[i-1]} → {times[i]}: {time_diff} 分钟")
            
            # 检查是否有13:36, 13:47这种非标准5分钟K线时间
            print(f"\n检查是否有非标准5分钟K线时间（分钟不是5的倍数）:")
            non_standard_times = []
            for dt in latest_day_data['datetime']:
                if dt.minute % 5 != 0:
                    non_standard_times.append(dt)
            
            if non_standard_times:
                print(f"  ⚠️ 发现 {len(non_standard_times)} 条非标准时间的数据:")
                for dt in non_standard_times[:10]:  # 只显示前10条
                    print(f"    {dt}")
            else:
                print(f"  ✓ 所有数据的时间戳都是标准5分钟K线时间")
                
        else:
            print("未获取到数据")
            
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_5min_kline()
