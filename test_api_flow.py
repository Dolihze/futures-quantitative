"""
测试完整的API调用流程
"""
import requests
import json

def test_api_flow():
    """测试API返回的数据"""
    
    # 测试5分钟线
    print("测试5分钟K线数据:")
    print("=" * 80)
    url = "http://127.0.0.1:5000/api/backtest/kline?symbol=FU2611&period=5&days=30"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get('success'):
            kline_data = data['data']
            print(f"\n获取到 {len(kline_data)} 条数据")
            
            # 只看最新一天的数据
            latest_date = kline_data[-1]['time'].split(' ')[0]
            latest_day_data = [k for k in kline_data if k['time'].startswith(latest_date)]
            
            print(f"\n最新交易日: {latest_date}")
            print(f"该日数据条数: {len(latest_day_data)}")
            
            # 显示时间戳（包含秒）
            print(f"\n最新一天前10条数据时间:")
            for k in latest_day_data[:10]:
                print(f"  {k['time']}")
            
            print(f"\n最新一天后10条数据时间:")
            for k in latest_day_data[-10:]:
                print(f"  {k['time']}")
                
            # 检查是否有非标准时间
            print(f"\n检查是否有非5分钟整数倍的时间:")
            non_standard = []
            for k in latest_day_data:
                time_str = k['time']
                minute = int(time_str.split(' ')[1].split(':')[1])
                if minute % 5 != 0:
                    non_standard.append(time_str)
            
            if non_standard:
                print(f"  ⚠️ 发现 {len(non_standard)} 条非标准时间:")
                for t in non_standard[:10]:
                    print(f"    {t}")
            else:
                print(f"  ✓ 所有时间都是5分钟整数倍")
        else:
            print(f"API调用失败: {data.get('message')}")
            
    except Exception as e:
        print(f"测试失败: {str(e)}")
        print("请确保Flask应用正在运行")

if __name__ == "__main__":
    test_api_flow()
