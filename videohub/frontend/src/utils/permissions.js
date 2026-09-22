// 功能点权限码:与后端 app/services/permissions.py 同步维护(单一事实来源在后端)。
// 授权语义为只读可见;写操作入口一律以 is_admin 判定显隐。
export const PERMISSIONS = [
  { code: "dashboard", label: "BI 大屏" },
  { code: "routes", label: "线路配置(只读)" },
  { code: "users", label: "用户管理(只读)" },
  { code: "access", label: "访问记录(只读)" },
]
