# Tushare 数据源配置指南

## 📋 概述

本项目已从 akshare 切换到 tushare 作为期货数据源，以获得更精确的 1 分钟 K 线数据。

---

## 🔑 配置步骤

### 第一步：注册 Tushare 账号

1. 访问 [Tushare 官网](https://tushare.pro)
2. 点击注册按钮，创建账号
3. 完成邮箱验证

### 第二步：获取 API Token

1. 登录 Tushare
2. 进入个人中心 → API 接口
3. 复制你的 API Token（一串长字符串）

### 第三步：配置 Token

**方法一：在 app.py 中配置**

打开 `app.py`，找到以下代码（约第 99 行）：

```python
ts.set_token('')  # 请填入你的tushare token
```

将你的 token 填入：

```python
ts.set_token('你的token粘贴到这里')
```

**方法二：在测试脚本中配置**

打开 `test_tushare_data.py`，找到以下代码（约第 14 行）：

```python
TUSHARE_TOKEN = 'ab3074f2f6ba6eb316fd19e6f9e5f8b0d0ff50ab90576a84b65ed591'
```

将你的 token 填入：

```python
TUSHARE_TOKEN = '你的token粘贴到这里'
```

---

## 🚀 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或者单独安装 tushare：

```bash
pip install tushare
```

### 2. 测试数据源

运行测试脚本验证数据源是否正常：

```bash
python test_tushare_data.py
```

如果看到类似以下输出，说明配置成功：

```
================================================================================
测试 tushare 获取期货数据
合约代码: FU2611
数据周期: 1分钟
================================================================================

正在初始化 tushare...
转换后的tushare合约代码: FU2611.SHF

正在获取数据...
日期范围: 2026-09-04 10:43:27 ~ 2026-10-04 10:43:27

✓ 成功获取数据，共 1020 条记录
```

### 3. 启动应用

```bash
python app.py
```

或者使用启动脚本：

```bash
start.bat
```

---

## 📊 数据源对比

| 特性        | akshare       | tushare                   |
| ----------- | ------------- | ------------------------- |
| 数据精度    | ⭐⭐ 截片数据 | ⭐⭐⭐⭐⭐ 基于 Tick 数据 |
| 1 分钟 K 线 | 不准确        | 精确                      |
| 价格        | 免费          | 基础功能 500 元/年        |
| 稳定性      | ⭐⭐          | ⭐⭐⭐⭐⭐                |
| 推荐度      | ⭐⭐          | ⭐⭐⭐⭐⭐                |

---

## 🔧 常见问题

### 问题 1：提示 "请先设置 TUSHARE_TOKEN"

**解决方案**：

- 确保你已经复制了正确的 token 到代码中
- 检查 token 是否有拼写错误

### 问题 2：获取数据返回空

**可能原因**：

- 合约代码不正确（例如：FU2611 可能已过期）
- 该时间段没有交易数据
- tushare 权限不足（需要积分）

**解决方案**：

- 检查合约代码是否正确
- 尝试获取其他时间段的数据
- 在 tushare 提升账号积分

### 问题 3：提示权限不足

**解决方案**：

- tushare 部分高级功能需要积分
- 新注册用户有基础权限，足够使用 1 分钟 K 线数据
- 如需更多权限，请在 tushare 完成任务提升积分

---

## 📝 合约代码格式

### Tushare 格式说明

期货合约代码格式为：`合约代码.交易所`

例如：

- `FU2611.SHF` - 上期所燃料油 2611 合约
- `RB2501.SHF` - 上期所螺纹钢 2501 合约
- `M2501.DCE` - 大商所豆粕 2501 合约

### 交易所代码映射

| 交易所             | 代码 | 品种示例               |
| ------------------ | ---- | ---------------------- |
| 上海期货交易所     | SHF  | FU, RB, CU, AL, AU, AG |
| 大连商品交易所     | DCE  | M, Y, I, JM, J         |
| 郑州商品交易所     | CZC  | CF, SR, TA             |
| 中国金融期货交易所 | CFX  | IF, IC, IH, T          |

---

## 💡 优化建议

### 1. Token 安全存储

建议将 token 存储在环境变量中，而不是硬编码在代码中：

```python
import os
ts.set_token(os.environ.get('TUSHARE_TOKEN', ''))
```

### 2. 数据缓存

建议在本地缓存已获取的数据，减少重复请求：

```python
# 保存数据到本地CSV
df.to_csv('data_cache/FU2611_1min.csv', index=False)

# 从本地加载数据
# df = pd.read_csv('data_cache/FU2611_1min.csv')
```

### 3. 错误处理

建议添加重试机制，应对网络问题：

```python
import time
for i in range(3):  # 重试3次
    try:
        df = ts.pro_bar(...)
        break
    except Exception as e:
        print(f"请求失败，{i+1}秒后重试...")
        time.sleep(i + 1)
```

---

## 🔗 相关资源

- [Tushare 官方文档](https://tushare.pro/document/2)
- [Tushare 期货数据接口](https://tushare.pro/document/2?doc_id=135)
- [Tushare 注册入口](https://tushare.pro/register)

---

## 📞 技术支持

如有问题，请查阅：

1. Tushare 官方文档
2. 项目中的测试脚本 `test_tushare_data.py`
3. app.py 中的数据获取逻辑

---

**最后更新时间**：2026-10-04
