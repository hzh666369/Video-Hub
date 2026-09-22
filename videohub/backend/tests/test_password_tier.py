"""密码强度段位判定单测（v2.0 积分制）：官方示例 + 边界 + 单调性。"""

import random

from app.services.password_tier import (
    classify_password,
    score_password,
    tier_name,
)

# (密码, 期望等级, 期望段位名) —— 分值均为代码实算
CASES = [
    # ---- 青铜：<70 分 ----
    ("abcdefgh", 1, "青铜"),      # 46 分：8 位纯小写，字母表连续片段扣满 12
    ("12345678", 1, "青铜"),      # 44 分：连续片段扣满
    ("98765432", 1, "青铜"),
    ("13579246", 1, "青铜"),      # 56 分：8 位纯数字与纯字母同熵，v2 起同档
    ("abc12345", 1, "青铜"),      # 54 分：abc + 12345 连续片段扣满 12
    ("Abc12345", 1, "青铜"),      # 66 分：大小写混合救不了连续片段扣分
    ("VIP20260", 1, "青铜"),      # 68 分
    ("aaaa1111", 1, "青铜"),      # 58 分：重复扣分
    ("11111111", 1, "青铜"),      # 48 分
    ("abcdefghijk", 1, "青铜"),   # 58 分：字母表连续片段扣满（连续惩罚全域生效）
    ("Password1!", 1, "青铜"),    # 100 分但命中黑名单封顶
    ("P@ssw0rd!", 1, "青铜"),     # 去符号变体 pssw0rd 命中黑名单
    ("p@ssw0rd", 1, "青铜"),      # 80 分但命中黑名单封顶
    ("qwerty123", 1, "青铜"),     # 黑名单
    # ---- 白银：70-79 ----
    ("pwned2026", 2, "白银"),     # 70：9 位两类无连续
    ("mypassw0rd", 2, "白银"),    # 74：10 位两类无连续
    # ---- 黄金：80-89 ----
    ("MyPwd2026", 3, "黄金"),     # 82：9 位三类无连续
    ("Xk9mQ2vR7p", 3, "黄金"),    # 86：10 位三类无连续
    ("Abc123!@#", 3, "黄金"),     # 96-8=88：含特殊但连续扣分
    # ---- 铂金：90-99 ----
    ("Pwd2026!", 4, "铂金"),      # 92：8 位四类
    ("Sunshine2026", 4, "铂金"),  # 98
    # ---- 钻石：100-109 ----
    ("A1b2C3!@#$", 5, "钻石"),    # 100：10 位四类无连续
    ("Abc123!@#$%^", 5, "钻石"),  # 112-8=104：含 abc/123 连续
    ("Abcdefghij1!", 5, "钻石"),  # 112-12=100：12 位但字母表长片段
    # ---- 星耀：110-119 ----
    ("A1b2C3d4!@#$", 6, "星耀"),  # 112：12 位四类无连续（v1 王者门槛已提高）
    ("A1b2C3d4e5f!", 6, "星耀"),  # 112
    ("Xk9mQ2vR#7p&", 6, "星耀"),  # 112：12 位四类无连续
    # ---- 王者：≥120（需 13 位以上四类齐全且无连续/重复） ----
    ("Xk9mQ2vR#7p&4", 7, "王者"),     # 120：13 位四类无连续
    ("Xk9mQ2vR#7p&4nZ", 7, "王者"),   # 136
    ("Xk9mQ2vR7p4nZtab", 7, "王者"),  # 130：16 位无特殊字符，长度分足够
    # ---- 边界：无段位 ----
    ("Ab1!", 0, "无段位"),
    ("", 0, "无段位"),
    ("1234567", 0, "无段位"),
    ("ABCDEFG", 0, "无段位"),
    ("VIP2026", 0, "无段位"),
    ("admin12", 0, "无段位"),     # 7 位，黑名单不改变长度前提
]


def test_classify_password_official_examples():
    for pwd, level, name in CASES:
        assert classify_password(pwd) == level, f"{pwd!r} 期望 {name}({level})"


def test_tier_names_match_levels():
    for pwd, level, name in CASES:
        assert tier_name(classify_password(pwd)) == name, f"{pwd!r} 段位名应为 {name}"


def test_below_minimum_length_is_zero():
    for pwd in ("A1b2C3!", "abcdefg", "1234567", ""):
        assert classify_password(pwd) == 0


def test_scores_are_monotonic_per_character():
    """逐字符追加得分不降（阈值单调的前提）。"""
    bases = ["Abc12345", "MyPwd2026", "abcdefgh", "13579246", "A1b2C3d4!@#$"]
    for base in bases:
        s = score_password(base)
        cur = base
        for ch in "Xk9mQ2vR7p4!@#ab01":
            cur += ch
            assert score_password(cur) >= s, f"{base!r} 追加 {ch!r} 后得分下降"
            s = score_password(cur)


def test_tier_monotonicity_never_drops_on_extension():
    """回归测试：追加任意字符，段位只升不降（含制造新连续/重复片段的情形）。"""
    random.seed(42)
    alphabet = "abcdefghABCXYZ0123456789!@#$%^&*aaaa1111123"
    bases = [
        "Abc12345", "MyPwd2026", "A1b2C3d4!@#$", "abcdefgh",
        "13579246", "Xk9mQ2vR#7p&", "aaaa1111", "p@ssw0rd!",
        "Sunshine2026", "abc12345",
    ]
    for base in bases:
        cur = base
        tier = classify_password(cur)
        for _ in range(40):
            cur += random.choice(alphabet)
            new_tier = classify_password(cur)
            assert new_tier >= tier, f"{cur!r} 段位由 {tier} 降到 {new_tier}"
            tier = new_tier


def test_blacklist_caps_at_bronze():
    # 去符号变体也要命中：Password1! 去掉 ! 后是 password1
    assert classify_password("Password1!") == 1
    assert classify_password("P@ssw0rd!") == 1
