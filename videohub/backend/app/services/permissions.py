"""功能点权限码:细粒度只读授权的单一事实来源。

与前端 src/utils/permissions.js 同步维护;新增可控功能点 = 在此加码并接线端点,
users 表无需迁移。授权语义为「只读可见」(设计:
docs/superpowers/specs/2026-09-15-permission-system-design.md)——写操作仍一律 require_admin。
"""
PERMISSION_CODES: frozenset[str] = frozenset({"dashboard", "routes", "users", "access"})
