#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接向远端账号服务 POST /api/setUser，自动附带 date（到期时间 = 当前 + days）。
不修改远端 Node 进程；用于新开账号或「已知密码」时续期（远端对已存在用户会校验密码一致后才更新 date）。

用法:
  set ACCOUNT_PROVISION_KEY（与 wrapper 的 /api/account/provision 使用同一密钥概念时，此处仅为脚本自用校验可选）
  实际远端 setUser 不要求 provision_key，本脚本默认只发 username/password/date。

  py -3 scripts/account_set_user.py --username 741741 --password secret --days 365

环境变量:
  ACCOUNT_API_BASE  默认 
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser(description="调用远端 /api/setUser 写入到期时间 date")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--days", type=int, default=365, help="从当前起有效天数（写入为到期时间）")
    args = p.parse_args()

    base = (os.environ.get("ACCOUNT_API_BASE") or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base

    exp = datetime.now() + timedelta(days=max(1, int(args.days)))
    date_str = exp.strftime("%Y-%m-%d %H:%M:%S")

    payload = json.dumps(
        {"username": args.username.strip(), "password": args.password, "date": date_str},
        ensure_ascii=False,
    ).encode("utf-8")

    url = f"{base}/api/setUser"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=2))
    if isinstance(data, dict) and data.get("code") == 0:
        print(f"\n到期时间已写入: {date_str}", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
