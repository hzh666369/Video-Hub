"""videohub 用户密码管理工具

用法（在 backend 目录下用 venv 的 python 执行）：

    .venv/Scripts/python.exe scripts/user_passwd.py list
    .venv/Scripts/python.exe scripts/user_passwd.py check  <用户名> <明文密码>
    .venv/Scripts/python.exe scripts/user_passwd.py reset  <用户名> <新密码>

说明：
    users.password_hash 存的是 bcrypt 哈希（$2b$...），带随机盐、单向不可逆，
    数据库里永远看不到明文密码。只能"校验"或"重置"，不能"查看"。
"""

import sqlite3
import sys
from pathlib import Path

import bcrypt

DB_PATH = Path(__file__).resolve().parent.parent / "videohub.db"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"[x] 找不到数据库: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def cmd_list() -> None:
    with connect() as con:
        rows = con.execute(
            "SELECT id, username, is_admin, created_at, substr(password_hash, 1, 7) AS algo "
            "FROM users ORDER BY id"
        ).fetchall()
    print(f"{'id':<4}{'用户名':<16}{'管理员':<8}{'算法':<8}创建时间")
    print("-" * 60)
    for r in rows:
        print(f"{r['id']:<4}{r['username']:<16}{('是' if r['is_admin'] else '否'):<8}{r['algo']:<8}{r['created_at']}")
    print(f"\n共 {len(rows)} 个账户（密码均为 bcrypt 哈希，无法反推明文）")


def cmd_check(username: str, plain: str) -> None:
    with connect() as con:
        row = con.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        sys.exit(f"[x] 用户不存在: {username}")
    ok = bcrypt.checkpw(plain.encode(), row["password_hash"].encode())
    print(f"{'✔ 密码正确' if ok else '✘ 密码错误'}  user={row['username']}")


def cmd_reset(username: str, new_password: str) -> None:
    if len(new_password) < 6:
        sys.exit("[x] 新密码至少 6 位")
    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    with connect() as con:
        cur = con.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username)
        )
        if cur.rowcount == 0:
            sys.exit(f"[x] 用户不存在: {username}")
        con.commit()
    print(f"✔ 已重置 {username} 的密码（新明文: {new_password}）")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "list" and not args:
        cmd_list()
    elif cmd == "check" and len(args) == 2:
        cmd_check(*args)
    elif cmd == "reset" and len(args) == 2:
        cmd_reset(*args)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
