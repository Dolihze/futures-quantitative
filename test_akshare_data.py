"""
测试脚本：验证 akshare 获取的期货1分钟K线数据
用于检查数据源是否正确，并查询特定时间点的数据
"""
import akshare as ak
import pandas as pd

def test_akshare_data():
    """测试 akshare 获取期货数据"""
    symbol = "FU2611"  # 燃料油2611合约
    period = "1"  # 1分钟
    
    print("=" * 80)
    print(f"测试 akshare 获取期货数据")
    print(f"合约代码: {symbol}")
    print(f"数据周期: {period}分钟")
    print("=" * 80)
    
    try:
        # 调用 akshare 接口
        print("\n正在调用 akshare.futures_zh_minute_sina...")
        df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        
        print(f"\n✓ 成功获取数据，共 {len(df)} 条记录")
        print(f"\n数据列名: {df.columns.tolist()}")
        
        # 转换 datetime 列
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # 查询特定时间点：2026-09-30 14:57:00
        target_time = pd.Timestamp('2026-09-30 14:57:00')
        print("\n" + "=" * 80)
        print(f"查询目标时间点: {target_time}")
        print("=" * 80)
        
        # 查找目标时间的数据
        target_data = df[df['datetime'] == target_time]
        
        if not target_data.empty:
            print(f"\n✓ 找到目标时间的数据！")
            row = target_data.iloc[0]
            print(f"\n详细数据:")
            print(f"  时间: {row['datetime']}")
            print(f"  开盘价: {row['open']}")
            print(f"  最高价: {row['high']}")
            print(f"  最低价: {row['low']}")
            print(f"  收盘价: {row['close']}")
            print(f"  成交量: {row.get('volume', 'N/A')}")
            
            # 验证数据合理性
            print(f"\n数据验证:")
            if row['open'] > 0:
                print(f"  ✓ 开盘价 > 0: {row['open']}")
            else:
                print(f"  ✗ 开盘价异常: {row['open']}")
            
            if row['high'] >= row['low']:
                print(f"  ✓ 最高价 >= 最低价: {row['high']} >= {row['low']}")
            else:
                print(f"  ✗ 最高价 < 最低价: 异常数据!")
            
            if row['high'] >= row['open'] and row['high'] >= row['close']:
                print(f"  ✓ 最高价是区间的最大值")
            else:
                print(f"  ✗ 最高价不是区间的最大值: 异常数据!")
            
            if row['low'] <= row['open'] and row['low'] <= row['close']:
                print(f"  ✓ 最低价是区间的最小值")
            else:
                print(f"  ✗ 最低价不是区间的最小值: 异常数据!")
        else:
            print(f"\n✗ 未找到目标时间的数据")
            print(f"\n数据时间范围: {df['datetime'].min()} ~ {df['datetime'].max()}")
            
            # 显示最接近目标时间的数据
            print("\n显示最后20条数据（最新数据）:")
            last_20_data = df.tail(20)
            for idx, row in last_20_data.iterrows():
                print(f"\n时间: {row['datetime']}")
                print(f"  开盘: {row['open']:.2f}, 最高: {row['high']:.2f}, 最低: {row['low']:.2f}, 收盘: {row['close']:.2f}")
        
        # 显示数据时间范围
        print("\n" + "=" * 80)
        print("数据时间范围:")
        print("=" * 80)
        print(f"最早时间: {df['datetime'].min()}")
        print(f"最晚时间: {df['datetime'].max()}")
        
        print("\n" + "=" * 80)
        print("测试完成!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ 获取数据失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_akshare_data()
