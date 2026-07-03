r"""
Cookie 保存脚本。
直接运行，修改下方 COOKIE_STR 后点运行。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.processor import _cookie_string_to_netscape
from app.core.paths import project_root

# ============================================================
#  改这里：粘贴你的 B站 Cookie
#  格式: "SESSDATA=xxx; bili_jct=yyy; buvid3=zzz"
# ============================================================
COOKIE_STR = "SESSDATA=5a9629f7%2C1798601266%2C58f90%2A71CjD8hJ0WDIoIVeC9uaUxFhAxaLIJAvcKis4VjcJ4aoHNe4RhGOtmeTJTpUXpRKpzRL8SVk0teHNKTWlIWlA4c25QTDJPZWROaTMzQnRMRTF3NU9EUmh3dHdFLXBDVktrMkdRaU1aMFFXUHhvbGhCcmlURVBRVzlrQ1RZVTlTMU0yY2pTOEF6a0VnIIEC"
# ============================================================


def main() -> None:
    if not COOKIE_STR:
        print("❌ COOKIE_STR 为空，请先在脚本顶部填入 Cookie 字符串")
        sys.exit(1)

    netscape = _cookie_string_to_netscape(COOKIE_STR)
    print(f"Netscape 格式 ({len(netscape.strip().split(chr(10)))} 行):")
    for line in netscape.strip().split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            print(f"  {parts[5]}={parts[6][:20]}...")

    txt_path = os.path.join(str(project_root()), "data", "cookies.txt")
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(netscape)

    print(f"\n✅ 已保存到 {txt_path}")


if __name__ == "__main__":
    main()
