"""
测试脚本：获取akshare中2026-09-30 14:40的期货数据
"""
import akshare as ak
import pandas as pd

def get_specific_time_data():
    """获取特定时间点的期货数据"""
    symbol = "FU2611"  # 燃料油2611合约
    period = "1"  # 1分钟
    
    print("=" * 80)
    print(f"获取akshare期货数据 - 指定时间: 2026-09-30 14:40")
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
        
        # 查询特定时间点：2026-09-30 14:40:00
        target_time = pd.Timestamp('2026-09-30 14:40:00')
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
            
            # 查找最接近的时间
            print("\n尝试查找最接近的时间点...")
            time_diff = (df['datetime'] - target_time).abs()
            closest_idx = time_diff.idxmin()
            closest_row = df.loc[closest_idx]
            print(f"\n最接近的数据点:")
            print(f"  时间: {closest_row['datetime']}")
            print(f"  时间差: {time_diff[closest_idx]}")
            print(f"  开盘: {closest_row['open']:.2f}")
            print(f"  最高: {closest_row['high']:.2f}")
            print(f"  最低: {closest_row['low']:.2f}")
            print(f"  收盘: {closest_row['close']:.2f}")
        
        # 显示数据时间范围
        print("\n" + "=" * 80)
        print("数据时间范围:")
        print("=" * 80)
        print(f"最早时间: {df['datetime'].min()}")
        print(f"最晚时间: {df['datetime'].max()}")
        
        # 显示目标时间附近的数据
        print("\n" + "=" * 80)
        print("目标时间附近的数据（前后各5条）:")
        print("=" * 80)
        
        # 找到目标时间在DataFrame中的位置
        target_indices = df[df['datetime'] == target_time].index
        if len(target_indices) > 0:
            target_idx = target_indices[0]
            start_idx = max(0, target_idx - 5)
            end_idx = min(len(df), target_idx + 6)
            
            print(f"\n显示索引 {start_idx} 到 {end_idx-1} 的数据:")
            for idx in range(start_idx, end_idx):
                row = df.iloc[idx]
                marker = " <-- 目标时间" if row['datetime'] == target_time else ""
                print(f"\n[{idx}] 时间: {row['datetime']}{marker}")
                print(f"     开盘: {row['open']:.2f}, 最高: {row['high']:.2f}, 最低: {row['low']:.2f}, 收盘: {row['close']:.2f}")
        else:
            print("\n未找到精确匹配的目标时间，显示最后10条数据:")
            last_10_data = df.tail(10)
            for idx, row in last_10_data.iterrows():
                print(f"\n[{idx}] 时间: {row['datetime']}")
                print(f"     开盘: {row['open']:.2f}, 最高: {row['high']:.2f}, 最低: {row['low']:.2f}, 收盘: {row['close']:.2f}")
        
        print("\n" + "=" * 80)
        print("脚本执行完成!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ 获取数据失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    get_specific_time_data()
