#!/usr/bin/env python3
"""
「记住账号」凭据存储

  * 记住的内容：期货公司、交易账号、交易密码
  * 密码用 Windows DPAPI（CryptProtectData）加密后存到本机文件，只有「当前 Windows 用户」能解开；
    复制到别的电脑 / 别的 Windows 账户都无法还原。
  * 存放位置：%LOCALAPPDATA%\\futures-quantitative\\credentials.dat（不在项目目录里，不会被提交）
  * 只保存一份（最近一次勾选「记住账号」登录的账号）。
  * 非 Windows 环境（没有 DPAPI）不保存密码，只保存账号 / 期货公司，不会退化成明文存储。

注意：密码「预填」到登录页意味着前端会拿到明文密码（本机 127.0.0.1 回环接口），
这是「记住密码」功能本身的性质；因此只在用户主动勾选「记住账号」时才保存，
取消勾选或退出时可随时清除。
"""
import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes

APP_DIRNAME = "futures-quantitative"
FILENAME = "credentials.dat"
# DPAPI 附加熵：不同用途的数据互不通用，也避免被其它程序直接用 CryptUnprotectData 解开
_ENTROPY = b"futures-quantitative/login-credentials/v1"

_IS_WINDOWS = sys.platform == "win32"


def store_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_DIRNAME, FILENAME)


# ----------------------------------------------------------------------------
# DPAPI
# ----------------------------------------------------------------------------

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _protect(plain):
    """bytes -> 加密 bytes；失败返回 None。"""
    if not _IS_WINDOWS:
        return None
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src, _keep1 = _blob(plain)
    ent, _keep2 = _blob(_ENTROPY)
    out = _DataBlob()
    # CRYPTPROTECT_UI_FORBIDDEN = 0x1：任何情况下都不弹系统对话框
    ok = crypt32.CryptProtectData(ctypes.byref(src), "futures-quantitative", ctypes.byref(ent),
                                  None, None, 0x1, ctypes.byref(out))
    if not ok:
        return None
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _unprotect(cipher):
    """加密 bytes -> 明文 bytes；不是本机本用户加密的 / 数据损坏返回 None。"""
    if not _IS_WINDOWS:
        return None
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src, _keep1 = _blob(cipher)
    ent, _keep2 = _blob(_ENTROPY)
    out = _DataBlob()
    ok = crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent),
                                    None, None, 0x1, ctypes.byref(out))
    if not ok:
        return None
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


# ----------------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------------

def save(broker, username, password):
    """保存凭据。返回 True=已保存（含密码）；False=没能保存密码（仅保存了账号 / 公司，或完全失败）。"""
    record = {"broker": broker, "username": username, "password": ""}
    password_saved = False

    if password:
        cipher = _protect(password.encode("utf-8"))
        if cipher is not None:
            record["password"] = base64.b64encode(cipher).decode("ascii")
            password_saved = True

    path = store_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp, path)  # 原子替换，避免写到一半崩溃留下坏文件
    except OSError as e:
        print(f"[Credentials] 保存失败: {e}")
        return False
    return password_saved


def load():
    """读取凭据。返回 {"broker", "username", "password"}；没有记录或文件损坏返回 None。
    密码无法解密（换了电脑 / 换了 Windows 用户 / 文件损坏）时 password 为空串，账号仍可预填。"""
    path = store_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
        broker = str(record.get("broker", ""))
        username = str(record.get("username", ""))
        enc = record.get("password", "")
    except (OSError, ValueError) as e:
        print(f"[Credentials] 读取失败，忽略: {e}")
        return None

    password = ""
    if enc:
        try:
            plain = _unprotect(base64.b64decode(enc))
            password = plain.decode("utf-8") if plain is not None else ""
        except (ValueError, UnicodeDecodeError):
            password = ""

    if not username:
        return None
    return {"broker": broker, "username": username, "password": password}


def clear():
    """清除已保存的凭据（不存在也安全）。"""
    try:
        os.remove(store_path())
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[Credentials] 清除失败: {e}")
