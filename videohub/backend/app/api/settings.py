import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_perm
from app.database import get_db
from app.models import AccessLog, Record, User
from app.services.auth import MAX_PASSWORD_BYTES, generate_password, hash_password
from app.services.permissions import PERMISSION_CODES
from app.services.settings import get_setting, get_vip_routes, is_https_prefix, set_setting

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsIn(BaseModel):
    vip_routes: list[dict] | None = None
    vip_default_route: str | None = None


class UserIn(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class PermsIn(BaseModel):
    permissions: list[str]


def _validate_routes(routes: list[dict], default_route: str | None) -> None:
    # 坏结构会导致 VIP 解析处 route["name"]/["prefix"] 直接 KeyError 500，入库前拦截
    names: set[str] = set()
    for r in routes:
        name, prefix = r.get("name"), r.get("prefix")
        if not isinstance(name, str) or not name.strip() or not isinstance(prefix, str) or not prefix.strip():
            raise HTTPException(status_code=400, detail="解析线路的 name 与 prefix 均为必填")
        # prefix 会拼进 embed_url 绑到播放页 iframe：javascript: 等协议会以站点身份
        # 执行脚本（存储型 XSS），http:// 也会被混合内容策略拦截，只放行 https://
        if not is_https_prefix(prefix):
            raise HTTPException(status_code=400, detail="解析线路 prefix 必须以 https:// 开头")
        if name in names:
            raise HTTPException(status_code=400, detail=f"线路名称重复：{name}")
        names.add(name)
    if default_route is not None and routes and default_route not in names:
        raise HTTPException(status_code=400, detail="默认线路不在线路列表中")


@router.get("/settings")
def read_settings(_: User = Depends(require_perm("routes")), db: Session = Depends(get_db)):
    return {
        "vip_routes": get_vip_routes(db),
        "vip_default_route": get_setting(db, "vip_default_route"),
    }


@router.put("/settings")
def update_settings(body: SettingsIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.vip_routes is not None or body.vip_default_route is not None:
        routes = body.vip_routes if body.vip_routes is not None else get_vip_routes(db)
        default_route = body.vip_default_route if body.vip_default_route is not None \
            else get_setting(db, "vip_default_route")
        _validate_routes(routes, default_route)
    if body.vip_routes is not None:
        set_setting(db, "vip_routes", body.vip_routes)
    if body.vip_default_route is not None:
        set_setting(db, "vip_default_route", body.vip_default_route)
    return {"ok": True}


@router.get("/users")
def list_users(_: User = Depends(require_perm("users")), db: Session = Depends(get_db)):
    # record_count 供前端删除确认时提示"将连带删除 N 条解析记录"，一次 group by 避免逐行 count
    counts = dict(db.execute(select(Record.user_id, func.count())
                             .group_by(Record.user_id)).all())
    return [{"id": u.id, "username": u.username, "is_admin": u.is_admin,
             "record_count": counts.get(u.id, 0),
             "permissions": sorted(u.permission_set)}
            for u in db.scalars(select(User)).all()]


@router.post("/users")
def create_user(body: UserIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    # 管理员新增用户只保证用户名唯一：去首尾空格、大小写不敏感（与注册接口判重口径一致），
    # 不做注册页的格式校验（正则/密码规则等），其余交给管理员自行决定
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    # bcrypt 上限 72 字节：本接口刻意不做注册页的强度规则，但硬存储上限必须守，否则 hash 时 500
    if len(body.password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail=f"密码最长 {MAX_PASSWORD_BYTES} 字节")
    if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(username=username, password_hash=hash_password(body.password), is_admin=body.is_admin)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 预检查窗口外的并发/大小写变体由 NOCASE 唯一索引兜底（红线 3.1），
        # 撞约束返回 409 而非 500
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在") from None
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 管理员账户只允许本人改密/数据库直操：避免一个被盗的 admin 无声接管/清除其他 admin
    if user.is_admin:
        raise HTTPException(status_code=403, detail="不允许删除管理员账户")
    # 名下解析记录整体清除（与用户自助注销 DELETE /api/auth/account 同口径，消除"自助能删、
    # 管理员删不掉"的行为分叉）；captions 经 FK ON DELETE CASCADE 联动清理（SQLite foreign_keys=ON 已开）
    db.execute(sa_delete(Record).where(Record.user_id == user.id))
    # 访问日志靠用户名快照保留可读性，删除用户前解除 user_id 外键引用
    db.execute(sa_update(AccessLog).where(AccessLog.user_id == user.id).values(user_id=None))
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 与删除同理：admin 的密码只能本人通过 /api/auth/password 修改，防管理员间横向接管
    if user.is_admin:
        raise HTTPException(status_code=403, detail="不允许重置管理员密码")
    new_password = generate_password()
    user.password_hash = hash_password(new_password)
    db.commit()
    # 重置后该用户所有旧会话随 pw_pv 指纹失配自动下线
    return {"username": user.username, "new_password": new_password}


@router.put("/users/{user_id}/permissions")
def set_user_permissions(user_id: int, body: PermsIn,
                         _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员设置用户功能点权限(授权=只读可见;写操作仍仅限管理员)。"""
    # 白名单校验:未知权限码一律拒绝,防止任意串写入 permissions 列
    bad = sorted({c for c in body.permissions if c not in PERMISSION_CODES})
    if bad:
        raise HTTPException(status_code=400, detail=f"未知权限:{','.join(bad)}")
    if len(body.permissions) != len(set(body.permissions)):
        raise HTTPException(status_code=400, detail="权限码重复")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 管理员账户不经此通道变更(与删除/重置密码同口径);管理员本就 has_perm 恒真
    if user.is_admin:
        raise HTTPException(status_code=403, detail="不允许修改管理员账户权限")
    user.permissions = json.dumps(sorted(set(body.permissions)))
    db.commit()
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin,
            "permissions": sorted(user.permission_set)}
