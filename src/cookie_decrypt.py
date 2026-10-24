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
COOKIE_VALUE = "thmR76ItCjkxrJSTxY_d_Qfatr3JFB18ia2WPBYc2F7Wsw2fYGOhjb9z3fp3QG0GNYbtFKEWREeKhOoPUO8fiqvX73aiOXXJYBk-fhs2ln63BXDzw3mZYfHD2md2WFy8myKYQ6kRTIWSbDduhoDuVNTfdaVW7gTujGv4m6uczsQReDsiUsnvX4sZQqpWizBUyBc13zdapwTg3p2E7OprwxOifmKgGx841qZ9bqG_3kTwqhQNjfCffCsiSrJNcHJzsHn4tJidtPLV3a2krtcvAQVQV0Q4Kpl2UYBAqWTioJs1nk_deJyimejN9VT1PYFR1VJlsvJkBmnp6V7lqOzLEsNcuvcooqU0qYkYloi908_OY2xIrY7_AwlnDoziUvxM9gON2dW-D-oaJxhZHGZ2lempX7clisAEnnAGYaqcc0EVqXWJ5vSQFx14qn6_i-aH-5ndL7UfeH_VNma5rRx5OzucN8ymo-vNrlv5etuyvaeO2UcB63CP_BclU2ij1SknUx69Gk0vUVruINWjJXZhVd41Yi7LXCPx8Ru1jf6PTKuMZq_nd2K4hwXUX7_-3yA_Yu2slgDYzqHdDpDCcoHv9ompscOfzq5-Yrox4kpW8ugPZue_EOWJbTF2brkU_xIlHen6H74IvwDHFKvey6d4TDWNOqPhvi41pztE9b_xuOcZ-TcjCju5V7JOvqtPJUXiSofsZyXAFwRNRmtqfEs7yUuQJxg5qX4EJNeRP6nWsABcYJgUabttgRIlKGoKzAXzWbeiqQB_IBu6bztWtjLtZhpW3zueapNGNSwqAT0-cToM5t4QiCqBQKyq-9hNamf5kiS5jlUgxjpWEbh6Qrv43zkmX3y1JsOMGp8M1S40XT5k5hvlr2wvYErktGfsy2sMF0O_CbWf7jPrNtYTUwwxr2XaJS2GMcdeT_i1T1rJD6AiuBuvjmPwLDbE1OJvpr5wvNr0XUsfyzUO5OtRcUOzp9x_1imUnaqzvw1U3Shihb5_mrc66VPjzZEAPDqiskaT0rW0Myph-ttj0gTQg3uSGlff2RWYyjsU50HwXF6uMepA85LnFZpBvDyBVmoQWonqCikkKcOBhaTOWqOQL8JVkB5Soq3nsm_NohkrSbSoejYP3BkC0FhfPvZw7b-3ceuInMeCZUvvekzpeqRjD8Hl8p20Ezv4GLO2bfEBVb9-Es3MhIMhXeD13fIaFqf2WT6z8OmmltB8jxhJbh407cBTFktaXMrW-rwxsBdNdpGmXBLvLqsZ0x6L3J6QPOq0l73Yj4Q5-AmqJUgT3uvfW9srNOafuRra-GWwnQiQsnzwmJxNuv27_u23I944iWh56aSKJO6Ru6k2PSLDa3oX5bCGz0TFHhhW5C_rk9MlFMnbfyLmEdL3mzNERvrgcwGGcQG6A0q4_PiihuIcRTpduajWC3V5PcNJ_zLm47U3ZwUnMbmsjionIChyGHGGFRhoZDBSizEgeO4YD1tG6oOfFDlXP4htjFtYXOoWQ2hQqkBybi0iyUd-NPNOBIB1oI2Tnw0sIvuhP08tQ6SrsPrOYpSLvOK1YOdVQG3aLqktC4oyF-csa5aXZ8yMGxQO4ck9C41geqrqp-mFxxI2OeQPoIw1OKqRkTXSEXd0IbmxSvWLL8XuH22B05c2qJHhmrAPnhExdZ_UXTJVLRobxu_iSpE1cWpd8lyfw2K4ZU2Blk6s8CVymDV9yX41JTuBaMA3kWz_LV6nFFmTs5Lncnr7cABGsNgvs7B1Tynm-xNHZIQio2WOl3yBHWPtMSLu1zI7zoHmzE17o6Xz9JGsYcKGl1yDpmsY_wOdhnX0HuiDjNP8DvBANfrJqzVe05DxA3tiIFG6WFxq7oD4lEnO3db4wXy6cFdXjtpbhsWA4mGECncHb2sejtHQpP5Dy8SeZYxzKuXlom3agpEcXom1GzAPVe19Hxwz4vf_Ro3MZBkkdDjzPtwgGazHOI5m7Lw0h41LeYfDL0crjvZRTk5HVKsQ3Pzd8yXXsZG0djoPltYAF175RSTpMDSdgGbIUOBJN7R_E8U762ybBRxGXDwjajbZkJYAGK6KBnuLPH6YVKa8vAT76M9cD2me72WR-bCQlI4cn2jDUx0bbeFytQ9O9uFiMwOhVioxb9ql10WKaSSu6VDAhQESOZizCushTtot1nsXauHRzTQdILsX51uCO2GhdsHjRw95UfgCrR0fuLurE3Spa8s1yz5rwltRXqXYP0OeHw2l5FJG3yEMw3F62etYKEQgbdSY59RzCum5V8Twp2iFm1obaYM4dnEGHGFXbEMn7PvM8FW_9N6EP32VegYuc0fBInoXmoudc0DgY_GBtjCJQSsq_knpOnZbEDbHs01mbVukk6lYfEl9_x-y9fr3IdherzFalDlfrL_wAGXfHWstcRJirbo=|1783143874|G1A43x7SQ1QUGDWeC2Tk2WzKARtkpVGCMQ4_ITZcbj0="
COOKIE_SECRET = "E-4Hzoxvmn8T5eKrYF10NVSlKz_07z8gqAt9O0z_xqquawHjtlhz1JbegVL-rP-P"
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