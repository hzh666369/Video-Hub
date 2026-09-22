"""密码强度段位（青铜 ~ 王者）判定 —— v2.0 积分制。

与前端 frontend/src/utils/passwordTier.js 是同一套规则的两份实现，
修改任何一侧必须同步另一侧，完整规则见 docs/密码段位说明书.md。

得分 = 长度分 + 类别分 − 连续片段扣分 − 重复字符扣分；黑名单命中封顶青铜。
单调性保证：每追加 1 个字符长度分最少 +4，而 1 个新字符最多新增 1 个
连续片段或 1 组重复（两者互斥）最多 -4，因此追加字符段位只升不降。

段位：1 青铜 / 2 白银 / 3 黄金 / 4 铂金 / 5 钻石 / 6 星耀 / 7 王者
0 表示无段位（长度不足 8 位，不满足最低有效段位）
"""

import re

TIER_NAMES = ("无段位", "青铜", "白银", "黄金", "铂金", "钻石", "星耀", "王者")

# 最低有效段位：青铜（等价于历史规则"密码至少 8 位"）
MIN_VALID_LEVEL = 1
PASSWORD_MIN_LEN = 8

# 积分参数（与前端 passwordTier.js 保持一致）
_LENGTH_FIRST = 6   # 前 8 位每字符得分
_LENGTH_MID = 4     # 9-11 位每字符得分
_LENGTH_LONG = 8    # 12 位起每字符得分
_LOWER_SCORE = 10
_UPPER_SCORE = 12
_DIGIT_SCORE = 8
_SPECIAL_SCORE = 14
_RUN_PENALTY = 4    # 每个 3 位连续片段
_RUN_CAP = 12
_REPEAT_PENALTY = 4 # 每组 ≥3 连续相同字符
_REPEAT_CAP = 8
# 白银 / 黄金 / 铂金 / 钻石 / 星耀 / 王者 的得分下限（低于首档为青铜）
_TIER_THRESHOLDS = (70, 80, 90, 100, 110, 120)

_STRIP_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# 常见弱密码黑名单（小写；命中后段位封顶青铜）
WEAK_PASSWORD_BLACKLIST = frozenset({
    "password", "password1", "password123", "password1234",
    "12345678", "123456789", "1234567890",
    "qwerty123", "qwerty12345", "qwerty123456",
    "abc12345", "abc123456", "abc12345678",
    "iloveyou", "iloveyou1", "admin123", "admin1234",
    "letmein123", "welcome1", "welcome123", "monkey123", "dragon123",
    "11111111", "00000000", "12121212", "12341234",
    "1234abcd", "abcd1234", "1234qwer", "qwer1234", "asdf1234", "zxcv1234",
    "1qaz2wsx", "1qaz2wsx3edc",
    "p@ssw0rd", "pssw0rd", "passw0rd", "passw0rd1", "trustno1",
    "sunshine1", "princess1", "football1", "master123", "a12345678",
})


def _is_blacklisted(password: str) -> bool:
    lower = password.lower()
    if lower in WEAK_PASSWORD_BLACKLIST:
        return True
    # 去掉符号后再比对，拦截 P@ssw0rd! / Password1! 之类变体
    stripped = _STRIP_NON_ALNUM.sub("", lower)
    return bool(stripped) and stripped in WEAK_PASSWORD_BLACKLIST


def _count_runs(seq: list) -> int:
    """统计 3 位连续片段数（升序或降序；None 打断；重叠各计一次）。"""
    runs = 0
    for i in range(len(seq) - 2):
        a, b, c = seq[i], seq[i + 1], seq[i + 2]
        if a is None or b is None or c is None:
            continue
        if (b - a == 1 and c - b == 1) or (b - a == -1 and c - b == -1):
            runs += 1
    return runs


def _count_repeat_groups(seq: list) -> int:
    """统计 ≥3 个连续相同字符的组数。"""
    groups = 0
    run = 1
    for i in range(1, len(seq) + 1):
        if i < len(seq) and seq[i] == seq[i - 1]:
            run += 1
        else:
            if run >= 3:
                groups += 1
            run = 1
    return groups


def score_password(password: str) -> int:
    """计算密码得分（长度分 + 类别分 − 扣分）。仅当长度 ≥ 8 时有意义。"""
    n = len(password)
    # 长度分
    score = min(n, 8) * _LENGTH_FIRST
    if n > 8:
        score += (min(n, 11) - 8) * _LENGTH_MID
    if n > 11:
        score += (n - 11) * _LENGTH_LONG

    # 类别判定 + 连续 / 重复序列（字母折算小写参与码位比较）
    has_lower = has_upper = has_digit = has_special = False
    run_seq: list = []  # 特殊字符为 None，打断连续片段
    rep_seq: list = []  # 全部字符参与重复判定
    for ch in password:
        o = ord(ch)
        if 97 <= o <= 122:      # a-z
            has_lower = True
            run_seq.append(o)
            rep_seq.append(o)
        elif 65 <= o <= 90:     # A-Z
            has_upper = True
            run_seq.append(o + 32)
            rep_seq.append(o + 32)
        elif 48 <= o <= 57:     # 0-9
            has_digit = True
            run_seq.append(o)
            rep_seq.append(o)
        else:                   # 特殊字符
            has_special = True
            run_seq.append(None)
            rep_seq.append(o)

    score += (_LOWER_SCORE if has_lower else 0) + (_UPPER_SCORE if has_upper else 0)
    score += (_DIGIT_SCORE if has_digit else 0) + (_SPECIAL_SCORE if has_special else 0)

    # 扣分项
    score -= min(_RUN_CAP, _count_runs(run_seq) * _RUN_PENALTY)
    score -= min(_REPEAT_CAP, _count_repeat_groups(rep_seq) * _REPEAT_PENALTY)
    return score


def classify_password(password: str) -> int:
    """判定密码段位，返回等级 0-7。"""
    if not password or len(password) < PASSWORD_MIN_LEN:
        return 0

    score = score_password(password)
    level = 1
    for i, threshold in enumerate(_TIER_THRESHOLDS):
        if score >= threshold:
            level = i + 2
    if _is_blacklisted(password):
        level = 1
    return level


def tier_name(level: int) -> str:
    """段位等级转名称（0-7，越界按无段位处理）。"""
    return TIER_NAMES[level] if 0 <= level < len(TIER_NAMES) else TIER_NAMES[0]
