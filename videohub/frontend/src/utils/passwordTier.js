/**
 * 密码强度段位判定（青铜 ~ 王者，共 7 段）—— v2.0 积分制
 *
 * 与后端 backend/app/services/password_tier.py 是同一套规则的两份实现，
 * 修改任何一侧必须同步另一侧，完整规则见 docs/密码段位说明书.md。
 *
 * 得分 = 长度分 + 类别分 − 连续片段扣分 − 重复字符扣分；黑名单命中封顶青铜。
 * 单调性保证：每追加 1 个字符长度分最少 +4，而 1 个新字符最多新增 1 个
 * 连续片段或 1 组重复（两者互斥）最多 -4，因此追加字符段位只升不降。
 *
 * 段位：1 青铜 / 2 白银 / 3 黄金 / 4 铂金 / 5 钻石 / 6 星耀 / 7 王者
 * 0 表示无段位（长度不足 8 位，不满足最低有效段位）
 */

export const TIERS = [
  { level: 0, key: "none", label: "无段位", color: "#8a93a3" },
  { level: 1, key: "bronze", label: "青铜", color: "#d08a4e" },
  { level: 2, key: "silver", label: "白银", color: "#a9b6c9" },
  { level: 3, key: "gold", label: "黄金", color: "#e8b83d" },
  { level: 4, key: "platinum", label: "铂金", color: "#5fd0e4" },
  { level: 5, key: "diamond", label: "钻石", color: "#5fa8ff" },
  { level: 6, key: "star", label: "星耀", color: "#b18cff" },
  { level: 7, key: "king", label: "王者", color: "#ff6b6b" },
]

export const PASSWORD_MIN_LEN = 8

/* ---- 积分参数（与后端 password_tier.py 保持一致） ---- */
const LEN_FIRST = 6 // 前 8 位每字符得分
const LEN_MID = 4 // 9-11 位每字符得分
const LEN_LONG = 8 // 12 位起每字符得分
const SCORE_LOWER = 10
const SCORE_UPPER = 12
const SCORE_DIGIT = 8
const SCORE_SPECIAL = 14
const RUN_PENALTY = 4 // 每个 3 位连续片段
const RUN_CAP = 12
const REPEAT_PENALTY = 4 // 每组 ≥3 连续相同字符
const REPEAT_CAP = 8
// 白银 / 黄金 / 铂金 / 钻石 / 星耀 / 王者 的得分下限（低于首档为青铜）
const TIER_THRESHOLDS = [70, 80, 90, 100, 110, 120]

/* 常见弱密码黑名单（小写；命中后段位封顶青铜） */
const WEAK_BLACKLIST = new Set([
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
])

function isBlacklisted(password) {
  const lower = password.toLowerCase()
  if (WEAK_BLACKLIST.has(lower)) return true
  // 去掉符号后再比对，拦截 P@ssw0rd! / Password1! 之类变体
  const stripped = lower.replace(/[^a-z0-9]/g, "")
  return stripped.length > 0 && WEAK_BLACKLIST.has(stripped)
}

/** 统计 3 位连续片段数（升序或降序；null 打断；重叠各计一次） */
function countRuns(seq) {
  let runs = 0
  for (let i = 0; i + 2 < seq.length; i++) {
    const a = seq[i]
    const b = seq[i + 1]
    const c = seq[i + 2]
    if (a === null || b === null || c === null) continue
    const d1 = b - a
    const d2 = c - b
    if ((d1 === 1 && d2 === 1) || (d1 === -1 && d2 === -1)) runs++
  }
  return runs
}

/** 统计 ≥3 个连续相同字符的组数 */
function countRepeatGroups(seq) {
  let groups = 0
  let run = 1
  for (let i = 1; i <= seq.length; i++) {
    if (i < seq.length && seq[i] === seq[i - 1]) {
      run++
    } else {
      if (run >= 3) groups++
      run = 1
    }
  }
  return groups
}

/**
 * 计算密码得分（长度分 + 类别分 − 扣分）。
 * 仅当长度 ≥ 8 时有意义。
 */
export function scorePassword(password) {
  const n = password.length
  // 长度分
  let score = Math.min(n, 8) * LEN_FIRST
  if (n > 8) score += (Math.min(n, 11) - 8) * LEN_MID
  if (n > 11) score += (n - 11) * LEN_LONG

  // 类别判定 + 连续 / 重复序列（字母折算小写参与码位比较）
  let hasLower = false
  let hasUpper = false
  let hasDigit = false
  let hasSpecial = false
  const runSeq = [] // 特殊字符为 null，打断连续片段
  const repSeq = [] // 全部字符参与重复判定
  for (const ch of password) {
    const code = ch.codePointAt(0)
    if (code >= 97 && code <= 122) {
      hasLower = true
      runSeq.push(code)
      repSeq.push(code)
    } else if (code >= 65 && code <= 90) {
      hasUpper = true
      runSeq.push(code + 32)
      repSeq.push(code + 32)
    } else if (code >= 48 && code <= 57) {
      hasDigit = true
      runSeq.push(code)
      repSeq.push(code)
    } else {
      hasSpecial = true
      runSeq.push(null)
      repSeq.push(code)
    }
  }
  score += (hasLower ? SCORE_LOWER : 0) + (hasUpper ? SCORE_UPPER : 0)
  score += (hasDigit ? SCORE_DIGIT : 0) + (hasSpecial ? SCORE_SPECIAL : 0)

  // 扣分项
  score -= Math.min(RUN_CAP, countRuns(runSeq) * RUN_PENALTY)
  score -= Math.min(REPEAT_CAP, countRepeatGroups(repSeq) * REPEAT_PENALTY)
  return score
}

/**
 * 判定密码段位，返回等级 0-7。
 */
export function classifyPassword(password) {
  if (typeof password !== "string" || password.length < PASSWORD_MIN_LEN) return 0

  const score = scorePassword(password)
  let tier = 1
  for (let i = 0; i < TIER_THRESHOLDS.length; i++) {
    if (score >= TIER_THRESHOLDS[i]) tier = i + 2
  }
  if (isBlacklisted(password)) tier = 1
  return tier
}
