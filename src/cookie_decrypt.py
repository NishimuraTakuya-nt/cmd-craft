#!/usr/bin/env python3
"""oauth2-proxy の cookie を復号して中身を表示する"""
import base64
import datetime
import struct
import warnings

import msgpack
import lz4.frame
from cryptography.utils import CryptographyDeprecationWarning
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)  # CFB 非推奨警告を抑制
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ▼▼▼ ここに値をベタ書きしてください ▼▼▼
COOKIE_VALUE = ""
COOKIE_SECRET = ""
# ▲▲▲ ここまで ▲▲▲

def secret_to_key(secret: str) -> bytes:
    # base64url としてデコードして 16/24/32 バイトになればそれを鍵に、ならなければ文字列そのまま
    s = secret.strip().rstrip("=")
    try:
        b = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        if len(b) in (16, 24, 32):
            return b
    except Exception:
        pass
    return secret.strip().encode()

def _decode_ts(data: bytes):
    # msgpack timestamp (ext -1) の 3 形式に対応
    if len(data) == 4:
        return datetime.datetime.fromtimestamp(struct.unpack(">I", data)[0], datetime.timezone.utc)
    if len(data) == 8:
        v = struct.unpack(">Q", data)[0]
        return datetime.datetime.fromtimestamp((v & 0x3FFFFFFFF) + (v >> 34) / 1e9, datetime.timezone.utc)
    if len(data) == 12:
        nsec = struct.unpack(">I", data[:4])[0]
        sec = struct.unpack(">q", data[4:])[0]
        return datetime.datetime.fromtimestamp(sec + nsec / 1e9, datetime.timezone.utc)
    return data  # 想定外の長さは生 bytes で返す（クラッシュ回避）

def ext_hook(code, data):
    # 古い msgpack 版はここに timestamp(-1) が渡ってくる
    if code == -1:
        return _decode_ts(data)
    return data

# msgpack.Timestamp は版によって存在しないため getattr で安全に取得
_MsgpackTimestamp = getattr(msgpack, "Timestamp", None)

def to_readable(v):
    # 新しい msgpack 版が Timestamp オブジェクトで返した場合だけ変換
    if _MsgpackTimestamp is not None and isinstance(v, _MsgpackTimestamp):
        return v.to_datetime()
    return v

def main():
    cookie_value = COOKIE_VALUE.strip()
    secret = COOKIE_SECRET

    # "value|timestamp|sig" の value 部分だけ取り出して base64url デコード
    enc_b64 = cookie_value.split("|")[0]
    raw = base64.urlsafe_b64decode(enc_b64 + "=" * (-len(enc_b64) % 4))

    # AES-CFB 復号（IV = 先頭16バイト）
    key = secret_to_key(secret)
    iv, ciphertext = raw[:16], raw[16:]
    d = Cipher(algorithms.AES(key), modes.CFB(iv)).decryptor()
    compressed = d.update(ciphertext) + d.finalize()

    # LZ4 解凍 → msgpack デコード（ext_hook で timestamp に対応）
    packed = lz4.frame.decompress(compressed)
    session = msgpack.unpackb(packed, raw=False, ext_hook=ext_hook)

    labels = {"ca": "作成時刻", "eo": "有効期限", "at": "アクセストークン", "it": "IDトークン",
              "rt": "リフレッシュトークン", "e": "Email", "u": "User", "g": "Groups"}
    for k, v in session.items():
        print(f"{labels.get(k, k)}: {to_readable(v)}")

if __name__ == "__main__":
    main()