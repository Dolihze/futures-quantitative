"""
测试akshare返回数据中的秒数
"""
import akshare as ak
import pandas as pd

def test_seconds():
    """测试数据中的秒数"""
    symbol = "FU2611"
    period = "5"
    
    df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 只看最新一天的数据
    latest_date = df['datetime'].dt.date.max()
    latest_day_data = df[df['datetime'].dt.date == latest_date]
    
    print(f"检查 {latest_date} 的数据秒数:")
    print("=" * 80)
    
    # 检查秒数
    seconds_counts = latest_day_data['datetime'].dt.second.value_counts().sort_index()
    print(f"\n秒数分布:")
    print(seconds_counts)
    
    # 显示秒数不为0的数据
    non_zero_seconds = latest_day_data[latest_day_data['datetime'].dt.second != 0]
    if len(non_zero_seconds) > 0:
        print(f"\n⚠️ 发现 {len(non_zero_seconds)} 条秒数不为0的数据:")
        for i, row in non_zero_seconds.head(10).iterrows():
            print(f"  {row['datetime']}")
    else:
        print(f"\n✓ 所有数据的秒数都是0")
    
    # 显示完整时间戳（包含秒）
    print(f"\n完整时间戳示例（前10条）:")
    for i, row in latest_day_data.head(10).iterrows():
        dt = row['datetime']
        print(f"  {dt.strftime('%Y-%m-%d %H:%M:%S')} (秒数: {dt.second})")

if __name__ == "__main__":
    test_seconds()
