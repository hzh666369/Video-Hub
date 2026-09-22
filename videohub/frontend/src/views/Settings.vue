<script setup>
import { computed, nextTick, onMounted, ref } from "vue"
import {
  PhCrownSimple as CrownSimple,
  PhUsers as Users,
  PhPlus as Plus,
  PhTrash as Trash,
  PhCheckCircle as CheckCircle,
  PhWarningCircle as WarningCircle,
  PhArrowsClockwise as ArrowsClockwise,
  PhCopy as Copy,
  PhChartBar as ChartBar,
  PhCaretDown as CaretDown,
  PhPencilSimple as PencilSimple,
  PhLockKey as LockKey,
  PhX as X,
} from "@phosphor-icons/vue"
import api from "../api/client"
import { useAuthStore } from "../stores/auth"
import { PERMISSIONS } from "../utils/permissions"
import { toast } from "../stores/toast"
import VhSpinner from "../components/VhSpinner.vue"
import VhExpandCard from "../components/VhExpandCard.vue"

const auth = useAuthStore()
const routes = ref([])
const defaultRoute = ref("")
const newRoute = ref({ name: "", prefix: "" })
const users = ref([])
const newUser = ref({ username: "", password: "" })
const resetResult = ref(null)
const resettingId = ref(null)
const deletingId = ref(null)
const addingUser = ref(false)
const error = ref("")
const saving = ref(false)

const isAdmin = computed(() => !!auth.user?.is_admin)
/* 折叠态按权限初始化：默认展开首个有权限的区块；无任何权限的入口已被路由守卫拦下 */
const sec = ref({
  routes: auth.can("routes"),
  users: !auth.can("routes") && auth.can("users"),
  access: !auth.can("routes") && !auth.can("users") && auth.can("access"),
})

/* ---- 访问记录 ---- */
const ACTION_LABELS = { visit: "页面访问", login: "登录", register: "注册", parse: "解析视频" }
const accessSummary = ref([])
const accessLoading = ref(false)
const detailUser = ref(null) // 当前查看明细的用户（汇总行对象）
const detailItems = ref([])
const detailTotal = ref(0)
const detailPage = ref(1)
const detailLoading = ref(false)
const detailRef = ref(null) // 明细面板元素（展开后滚动跟随定位）
const PAGE_SIZE = 20

async function loadAccess() {
  accessLoading.value = true
  try {
    const { data } = await api.get("/admin/access/summary")
    accessSummary.value = data.items
  } catch (e) { error.value = e.friendly }
  finally { accessLoading.value = false }
}

async function openDetail(u) {
  if (detailUser.value?.user_id === u.user_id) { detailUser.value = null; return }
  detailUser.value = u
  detailItems.value = []
  detailTotal.value = 0
  detailPage.value = 1
  /* 面板渲染后立即滚动跟随到明细区，加载态期间即可看见（reduced-motion 退化为瞬时定位） */
  await nextTick()
  detailRef.value?.scrollIntoView({
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "start",
  })
  await fetchDetail()
}

async function fetchDetail() {
  if (!detailUser.value) return
  detailLoading.value = true
  try {
    const { data } = await api.get("/admin/access/logs", {
      params: { user_id: detailUser.value.user_id, page: detailPage.value, page_size: PAGE_SIZE },
    })
    detailItems.value = detailPage.value === 1 ? data.items : [...detailItems.value, ...data.items]
    detailTotal.value = data.total
  } catch (e) { error.value = e.friendly }
  finally { detailLoading.value = false }
}

async function loadMoreDetail() {
  detailPage.value += 1
  await fetchDetail()
}

function fmtTime(iso) {
  if (!iso) return "—"
  return iso.replace("T", " ").slice(0, 19)
}

/* ---- VIP 线路脏检查：与已保存状态不一致时才显示保存按钮 ---- */
function routeSnapshot() {
  return JSON.stringify({ routes: routes.value, default: defaultRoute.value })
}
const savedSnapshot = ref(null)
const routesDirty = computed(() => savedSnapshot.value !== null && routeSnapshot() !== savedSnapshot.value)

async function loadRoutes() {
  const { data } = await api.get("/settings")
  routes.value = data.vip_routes
  defaultRoute.value = data.vip_default_route || ""
  savedSnapshot.value = routeSnapshot()
}

async function loadUsers() {
  const { data } = await api.get("/users")
  users.value = data
}

async function save() {
  error.value = ""
  saving.value = true
  const body = {
    vip_routes: routes.value,
    vip_default_route: defaultRoute.value || null,
  }
  try {
    await api.put("/settings", body)
    await loadRoutes()
    toast.success("设置已保存，线路配置已生效")
  } catch (e) {
    toast.error(e.friendly || "保存失败，请稍后重试")
  } finally { saving.value = false }
}

function addRoute() {
  const name = newRoute.value.name.trim()
  if (!newRoute.value.name || !newRoute.value.prefix) {
    toast.error("请填写线路名称和前缀后再添加")
    return
  }
  /* 名称是行的唯一 key，前端先查重（与编辑确认同口径），避免同名导致渲染错乱 */
  if (routes.value.some((r) => r.name === name)) {
    toast.error(`线路名称「${name}」已存在`)
    return
  }
  routes.value = [...routes.value, { ...newRoute.value }]
  newRoute.value = { name: "", prefix: "" }
  toast.info(`线路「${routes.value[routes.value.length - 1].name}」已添加，记得点击「保存设置」生效`)
}

function removeRoute(name) {
  routes.value = routes.value.filter((r) => r.name !== name)
  if (defaultRoute.value === name) defaultRoute.value = ""
}

/* ---- 行内编辑：编辑缓冲独立于 routes，取消可还原；确认后才写入（脏检查随之亮出保存按钮） ---- */
const editingIndex = ref(-1)
const editRoute = ref({ name: "", prefix: "" })

function startEdit(i) {
  editingIndex.value = i
  editRoute.value = { ...routes.value[i] }
}

function cancelEdit() {
  editingIndex.value = -1
}

function confirmEdit(i) {
  const name = editRoute.value.name.trim()
  const prefix = editRoute.value.prefix.trim()
  if (!name || !prefix) {
    toast.error("请填写线路名称和前缀后再确认")
    return
  }
  if (!/^https:\/\//.test(prefix)) {
    toast.error("前缀必须以 https:// 开头")
    return
  }
  if (routes.value.some((r, idx) => idx !== i && r.name === name)) {
    toast.error(`线路名称「${name}」已存在`)
    return
  }
  const oldName = routes.value[i].name
  routes.value = routes.value.map((r, idx) => (idx === i ? { name, prefix } : r))
  /* 默认线路跟随重命名，避免保存时"默认线路不在线路列表中"的校验失败 */
  if (defaultRoute.value === oldName) defaultRoute.value = name
  editingIndex.value = -1
  toast.info(`线路「${name}」已修改，记得点击「保存设置」生效`)
}

/* ---- 拖拽排序：按住行拖到目标位置松手（编辑期间整体禁用，避免 editingIndex 失真） ---- */
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)
const dropPos = ref("before") // 落点在目标行的上方/下方，按指针 Y 与行中点比较

function onDragStart(i, e) {
  dragIndex.value = i
  e.dataTransfer.effectAllowed = "move"
  // Firefox 必须有 setData 才能触发后续 dragover/drop
  e.dataTransfer.setData("text/plain", String(i))
}

function onDragOver(i, e) {
  if (dragIndex.value === -1) return
  e.preventDefault()
  e.dataTransfer.dropEffect = "move"
  const rect = e.currentTarget.getBoundingClientRect()
  dropPos.value = e.clientY < rect.top + rect.height / 2 ? "before" : "after"
  dragOverIndex.value = i
}

function onDrop(i) {
  const from = dragIndex.value
  if (from !== -1 && from !== i) {
    // 插入点换算成"移除自己之后"的下标；与原位置相同则视为未移动
    let to = dropPos.value === "after" ? i + 1 : i
    if (to > from) to -= 1
    if (to !== from) {
      const arr = [...routes.value]
      const [moved] = arr.splice(from, 1)
      arr.splice(to, 0, moved)
      routes.value = arr
      toast.info(`线路「${moved.name}」已调整顺序，记得点击「保存设置」生效`)
    }
  }
  resetDrag()
}

function resetDrag() {
  dragIndex.value = -1
  dragOverIndex.value = -1
}

/* 用户名实时查重：输完用户名即提示，不必等点击「添加用户」（忽略大小写 + 去空格，与提交口径一致） */
const usernameTaken = computed(() => {
  const name = newUser.value.username.trim().toLowerCase()
  return name !== "" && users.value.some((u) => u.username.toLowerCase() === name)
})

async function addUser() {
  if (addingUser.value) return
  error.value = ""
  // 只校验用户名唯一性（去空格、忽略大小写），不做注册页那套格式限制
  const username = newUser.value.username.trim()
  if (!username) {
    toast.error("请输入用户名")
    return
  }
  if (usernameTaken.value) {
    toast.error(`用户名「${username}」已存在`)
    return
  }
  addingUser.value = true
  try {
    await api.post("/users", { ...newUser.value, username })
    newUser.value = { username: "", password: "" }
    await loadUsers()
    toast.success(`用户「${username}」创建成功`)
  } catch (e) {
    // 出错时保留已填内容，方便修改后重试
    toast.error(e.friendly || "创建用户失败，请稍后重试")
  } finally { addingUser.value = false }
}

async function resetPassword(u) {
  if (!confirm(`确认将用户「${u.username}」的密码重置为随机密码？`)) return
  error.value = ""
  resettingId.value = u.id
  try {
    const { data } = await api.post(`/users/${u.id}/reset-password`)
    resetResult.value = data
  } catch (e) {
    toast.error(e.friendly || "重置失败，请稍后重试")
  } finally { resettingId.value = null }
}

async function copyResetPassword() {
  if (!resetResult.value) return
  try {
    await navigator.clipboard.writeText(resetResult.value.new_password)
    toast.success("新密码已复制到剪贴板")
  } catch {
    toast.error("复制失败，请手动选中新密码复制")
  }
}

async function removeUser(u) {
  /* 有解析记录时明确告知连带清除数量，避免管理员误删他人数据（与自助注销同口径） */
  const extra = u.record_count ? `\n其名下 ${u.record_count} 条解析记录将一并删除。` : ""
  if (!confirm(`确认删除用户「${u.username}」？${extra}\n删除后无法恢复。`)) return
  deletingId.value = u.id
  try {
    await api.delete(`/users/${u.id}`)
    await loadUsers()
    toast.success("用户已删除")
  } catch (e) {
    toast.error(e.friendly || "删除失败，请稍后重试")
  } finally { deletingId.value = null }
}

/* ---- 权限编辑（仅管理员）：逐用户勾选功能点，授权=只读可见 ---- */
const permsOpenId = ref(null)
const permsDraft = ref([])
const permsBusy = ref(false)

function openPerms(u) {
  permsOpenId.value = u.id
  permsDraft.value = PERMISSIONS.filter((p) => (u.permissions || []).includes(p.code)).map((p) => p.code)
}

function closePerms() {
  permsOpenId.value = null
  permsDraft.value = []
}

async function savePerms(u) {
  if (!u) return
  permsBusy.value = true
  try {
    const { data } = await api.put(`/users/${u.id}/permissions`, { permissions: permsDraft.value })
    u.permissions = data.permissions
    closePerms()
    toast.success(`已更新「${u.username}」的权限`)
  } catch (e) {
    toast.error(e.friendly || "权限保存失败")
  } finally {
    permsBusy.value = false
  }
}

onMounted(() => {
  if (auth.can("routes")) loadRoutes()
  if (auth.can("users")) loadUsers()
  if (auth.can("access")) loadAccess()
})
</script>

<template>
  <div class="vh-page settings">
    <header class="vh-head">
      <h1 class="vh-head-title">设置</h1>
      <p class="vh-head-sub">{{ isAdmin ? "接口密钥、VIP 解析线路与账号管理" : "已授权功能查看（只读）" }}</p>
    </header>

    <transition name="alert">
      <p v-if="error" class="error" role="alert">
        <WarningCircle size="16" weight="fill" />
        {{ error }}
      </p>
    </transition>

    <!-- VIP 线路 -->
    <VhExpandCard v-if="auth.can('routes')" v-model="sec.routes" class="section" tone="gold" padding="0 22px 22px">
      <template #head>
        <span class="section-icon gold"><CrownSimple size="18" weight="regular" /></span>
        <span class="section-text">
          <span class="section-title">VIP 解析线路</span>
          <span class="section-desc">勾选默认线路，用于 VIP 播放页内嵌；按住行可拖动排序，保存设置后生效</span>
        </span>
        <span v-if="routes.length" class="sec-count num">{{ routes.length }}</span>
      </template>

      <div v-if="routes.length" class="routes">
        <div
          v-for="(r, i) in routes"
          :key="r.name"
          class="route-row"
          :class="{
            'is-default': defaultRoute === r.name,
            'is-editing': editingIndex === i,
            dragging: dragIndex === i,
            'drop-before': dragOverIndex === i && dragIndex !== i && dropPos === 'before',
            'drop-after': dragOverIndex === i && dragIndex !== i && dropPos === 'after',
          }"
          :style="{ animationDelay: i * 0.045 + 's' }"
          :draggable="isAdmin && editingIndex === -1"
          @dragstart="onDragStart(i, $event)"
          @dragover="onDragOver(i, $event)"
          @drop="onDrop(i)"
          @dragend="resetDrag"
        >
          <template v-if="editingIndex === i">
            <form class="route-edit" @submit.prevent="confirmEdit(i)">
              <input v-model="editRoute.name" class="vh-input" placeholder="线路名称" />
              <input v-model="editRoute.prefix" class="vh-input edit-prefix" placeholder="前缀，如 https://jx.xxx/?url=" autocomplete="off" />
              <button type="submit" class="vh-btn vh-btn-primary vh-btn-sm">
                <CheckCircle size="13" weight="regular" />
                确定
              </button>
              <button type="button" class="vh-btn vh-btn-ghost vh-btn-sm" @click="cancelEdit">取消</button>
            </form>
          </template>
          <template v-else>
            <template v-if="isAdmin">
              <label class="radio">
                <span class="radio-wrap">
                  <input v-model="defaultRoute" type="radio" name="default-route" :value="r.name" />
                  <span class="radio-box" aria-hidden="true"></span>
                </span>
                <span class="radio-label">默认</span>
              </label>
            </template>
            <span class="route-name">{{ r.name }}</span>
            <span class="route-prefix num">{{ r.prefix }}</span>
            <div v-if="isAdmin" class="route-actions">
              <button class="vh-btn vh-btn-ghost vh-btn-sm" @click="startEdit(i)">
                <PencilSimple size="13" weight="regular" />
                编辑
              </button>
              <button class="vh-btn vh-btn-danger vh-btn-sm" @click="removeRoute(r.name)">
                <Trash size="13" weight="regular" />
                删除
              </button>
            </div>
          </template>
        </div>
      </div>
      <p v-else class="blank">暂无线路，在下方添加</p>

      <form v-if="isAdmin" class="add-row" @submit.prevent="addRoute">
        <input v-model="newRoute.name" class="vh-input" placeholder="线路名称" />
        <input v-model="newRoute.prefix" class="vh-input prefix" placeholder="前缀，如 https://jx.xxx/?url=" autocomplete="off" />
        <button type="submit" class="vh-btn vh-btn-ghost">
          <Plus size="14" weight="bold" />
          添加
        </button>
      </form>

      <div v-if="isAdmin && routesDirty" class="save-row">
        <button class="vh-btn vh-btn-primary save-btn" :disabled="saving" @click="save">
          <VhSpinner v-if="saving" variant="ring" :size="15" :weight="2" />
          <span>{{ saving ? "保存中" : "保存设置" }}</span>
        </button>
      </div>
    </VhExpandCard>

    <!-- 用户管理 -->
    <VhExpandCard v-if="auth.can('users')" v-model="sec.users" class="section" padding="0 22px 22px">
      <template #head>
        <span class="section-icon"><Users size="18" weight="regular" /></span>
        <span class="section-text">
          <span class="section-title">用户管理</span>
          <span class="section-desc">管理平台账号，管理员账号不可删除</span>
        </span>
        <span v-if="users.length" class="sec-count num">{{ users.length }}</span>
      </template>

      <ul class="users">
        <li v-for="(u, i) in users" :key="u.id" class="user-row" :style="{ animationDelay: i * 0.04 + 's' }">
          <span class="avatar" aria-hidden="true">{{ u.username.slice(0, 1).toUpperCase() }}</span>
          <div class="user-info">
            <span class="user-name">{{ u.username }}</span>
            <span v-if="u.is_admin" class="admin-chip">管理员</span>
          </div>
          <button
            v-if="isAdmin && !u.is_admin"
            class="vh-btn vh-btn-ghost vh-btn-sm"
            @click="openPerms(u)"
          >
            <LockKey size="13" weight="regular" />
            权限
          </button>
          <div v-if="isAdmin" class="user-actions">
            <button
              class="vh-btn vh-btn-ghost vh-btn-sm"
              :disabled="resettingId === u.id"
              @click="resetPassword(u)"
            >
              <ArrowsClockwise size="13" weight="regular" />
              重置密码
            </button>
            <button
              v-if="!u.is_admin"
              class="vh-btn vh-btn-danger vh-btn-sm"
              :disabled="deletingId === u.id"
              @click="removeUser(u)"
            >
              <VhSpinner v-if="deletingId === u.id" variant="ring" :size="13" :weight="2" />
              <Trash v-else size="13" weight="regular" />
              {{ deletingId === u.id ? "删除中" : "删除" }}
            </button>
          </div>
        </li>
      </ul>

      <transition name="alert">
        <p v-if="resetResult" class="reset-result" role="status">
          <CheckCircle size="15" weight="fill" />
          用户「{{ resetResult.username }}」的密码已重置为：
          <code class="reset-pwd">{{ resetResult.new_password }}</code>
          <button class="vh-btn vh-btn-ghost vh-btn-sm" @click="copyResetPassword">
            <Copy size="13" weight="regular" />
            复制
          </button>
          <button class="reset-close" aria-label="关闭" @click="resetResult = null">×</button>
        </p>
      </transition>

      <form v-if="isAdmin" class="add-row users-add" @submit.prevent="addUser">
        <input
          v-model="newUser.username"
          class="vh-input"
          :class="{ 'is-taken': usernameTaken }"
          placeholder="用户名"
          autocomplete="off"
        />
        <input v-model="newUser.password" class="vh-input" type="password" placeholder="密码" autocomplete="new-password" />
        <button type="submit" class="vh-btn vh-btn-ghost" :disabled="addingUser">
          <VhSpinner v-if="addingUser" variant="ring" :size="14" :weight="2" />
          <Plus v-else size="14" weight="bold" />
          {{ addingUser ? "创建中" : "添加用户" }}
        </button>
      </form>

      <transition name="alert">
        <p v-if="isAdmin && usernameTaken" class="dup-hint" role="status">
          <WarningCircle size="14" weight="fill" />
          用户名「{{ newUser.username.trim() }}」已存在，换一个吧
        </p>
      </transition>
    </VhExpandCard>

    <!-- 访问记录 -->
    <VhExpandCard v-if="auth.can('access')" v-model="sec.access" class="section access" padding="0 22px 22px">
      <template #head>
        <span class="section-icon"><ChartBar size="18" weight="regular" /></span>
        <span class="section-text">
          <span class="section-title">访问记录</span>
          <span class="section-desc">按用户汇总访问与解析情况，点击行查看完整访问明细（本地日志同步落盘 backend/logs）</span>
        </span>
        <button class="vh-btn vh-btn-ghost vh-btn-sm" :disabled="accessLoading" @click.stop="loadAccess">
          <ArrowsClockwise size="13" weight="regular" :class="{ spin: accessLoading }" />
          刷新
        </button>
      </template>

      <div v-if="accessSummary.length" class="acc-table" role="table" aria-label="访问记录汇总">
        <div class="acc-row acc-head" role="row">
          <span>用户名</span>
          <span>最近访问</span>
          <span class="acc-num">今日访问</span>
          <span class="acc-num">历史访问</span>
          <span class="acc-num">解析个数</span>
          <span class="acc-more" aria-hidden="true"></span>
        </div>
        <button
          v-for="u in accessSummary"
          :key="u.user_id"
          class="acc-row acc-body"
          :class="{ open: detailUser?.user_id === u.user_id }"
          role="row"
          @click="openDetail(u)"
        >
          <span class="acc-user">
            <span class="avatar sm" aria-hidden="true">{{ u.username.slice(0, 1).toUpperCase() }}</span>
            {{ u.username }}
            <span v-if="u.is_admin" class="admin-chip">管理员</span>
          </span>
          <span class="acc-time num">{{ fmtTime(u.last_visit_at) }}</span>
          <span class="acc-num num">{{ u.today_count }}</span>
          <span class="acc-num num strong">{{ u.total_count }}</span>
          <span class="acc-num num gold">{{ u.parse_count }}</span>
          <CaretDown size="13" weight="bold" class="acc-caret" :class="{ flip: detailUser?.user_id === u.user_id }" />
        </button>
      </div>
      <p v-else class="blank">{{ accessLoading ? "加载中…" : "暂无访问记录（自本版本上线后开始统计）" }}</p>

      <!-- 单用户完整明细 -->
      <div v-if="detailUser" ref="detailRef" class="acc-detail">
        <p class="acc-detail-title">
          「{{ detailUser.username }}」的访问明细
          <span class="num">共 {{ detailTotal }} 条</span>
        </p>
        <ul v-if="detailItems.length" class="acc-list">
          <li v-for="it in detailItems" :key="it.id" class="acc-item">
            <span class="acc-chip" :class="`is-${it.action}`">{{ ACTION_LABELS[it.action] || it.action }}</span>
            <span class="acc-item-detail" :title="it.detail || ''">{{ it.detail || "—" }}</span>
            <span class="acc-item-time num">{{ fmtTime(it.created_at) }}</span>
          </li>
        </ul>
        <p v-else class="blank">{{ detailLoading ? "加载中…" : "暂无明细" }}</p>
        <button
          v-if="detailItems.length < detailTotal"
          class="vh-btn vh-btn-ghost vh-btn-sm acc-more-btn"
          :disabled="detailLoading"
          @click="loadMoreDetail"
        >
          <ArrowsClockwise v-if="detailLoading" size="13" weight="regular" class="spin" />
          加载更多（{{ detailItems.length }}/{{ detailTotal }}）
        </button>
      </div>
    </VhExpandCard>

    <!-- 权限编辑弹层（仅管理员） -->
    <teleport to="body">
      <transition name="pwd-fade">
        <div v-if="permsOpenId !== null" class="pwd-mask" @click.self="closePerms">
          <section class="pwd-dialog" role="dialog" aria-label="功能点权限">
            <header class="pwd-head">
              <h2 class="pwd-title">
                <LockKey size="17" weight="regular" />
                功能点权限
              </h2>
              <button class="pwd-close" aria-label="关闭" @click="closePerms">
                <X size="16" weight="bold" />
              </button>
            </header>
            <div class="perms-list">
              <label v-for="p in PERMISSIONS" :key="p.code" class="perms-item">
                <input v-model="permsDraft" type="checkbox" :value="p.code" />
                <span>{{ p.label }}</span>
              </label>
            </div>
            <p class="perms-note">授权 = 只读可见；修改线路、增删用户等写操作仍仅限管理员。</p>
            <button
              class="vh-btn vh-btn-aurora pwd-submit"
              :disabled="permsBusy"
              @click="savePerms(users.find((u) => u.id === permsOpenId))"
            >
              <span>{{ permsBusy ? "保存中" : "保存" }}</span>
            </button>
          </section>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<style scoped>
.settings { max-width: 860px; }

.error {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 16px;
  padding: 10px 14px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  border: 1px solid rgba(243, 114, 127, 0.45);
  color: var(--danger);
  font-size: 13px;
}

.section { margin-bottom: 14px; }
.section :deep(.vhx-head) { padding: 20px 22px; gap: 14px; }
.section-text { display: flex; flex-direction: column; min-width: 0; }
.section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}
.section-desc { margin-top: 4px; color: var(--text-3); font-size: 13px; line-height: 1.5; }
.sec-count {
  margin-left: auto;
  padding: 2px 10px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  border: 1px solid var(--line);
  color: var(--text-3);
  font-size: 12px;
  font-weight: 600;
}

/* 分组头部（图标） */
.section-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: var(--accent-soft);
  border: 1px solid rgba(30, 215, 96, 0.28);
  color: var(--accent);
  flex-shrink: 0;
  transition: transform var(--dur-3) var(--ease-spring), background var(--dur-2) ease;
}
.section:hover .section-icon { transform: scale(1.06) rotate(-5deg); }
.section-icon.gold {
  background: var(--gold-soft);
  border-color: rgba(255, 164, 43, 0.35);
  color: var(--gold-bright);
}

/* 密钥输入：可切换明文 */
.key-input-wrap { position: relative; }
.key-eye {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: color var(--dur-1) ease, background var(--dur-1) ease;
}
.key-eye:hover { color: var(--accent); background: var(--surface-3); }
.vh-field > label { display: inline-flex; align-items: center; gap: 7px; }
.tip-btn {
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--text-3);
  cursor: help;
  transition: color var(--dur-1) ease, border-color var(--dur-1) ease;
}
.tip-btn:hover { color: var(--accent); border-color: rgba(30, 215, 96, 0.5); }

/* 密钥统计 */
.key-stats { display: flex; gap: 12px; flex-wrap: wrap; }
.stat {
  flex: 1;
  min-width: 180px;
  padding: 14px 16px;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: border-color 0.2s ease;
}
.stat:hover { border-color: var(--line-strong); }
.stat-label { color: var(--text-3); font-size: 12px; }
.stat-value { color: var(--text-1); font-size: 15px; font-weight: 600; }
.points {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--gold-bright);
}
.points :deep(svg) { color: var(--gold); }

.key-row { display: flex; gap: 10px; align-items: flex-end; }
.grow { flex: 1; }
.save-btn {
  height: 38px;
  min-width: 110px;
  gap: 7px;
}
.save-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

/* 线路 */
.routes { display: flex; flex-direction: column; gap: 8px; }
.route-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  background: var(--bg-raise);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.25s var(--ease-out);
  animation: vh-fade-in-up 0.4s var(--ease-out) both;
}
.route-row:hover { border-color: var(--line-strong); transform: translateX(3px); }
/* 拖拽排序 */
.route-row { position: relative; }
.route-row[draggable="true"] { cursor: grab; }
.route-row[draggable="true"]:active { cursor: grabbing; }
.route-row.dragging {
  opacity: 0.45;
  border-style: dashed;
  transform: none;
}
.route-row.drop-before::before,
.route-row.drop-after::after {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  height: 2px;
  border-radius: 2px;
  background: var(--accent-strong);
  box-shadow: 0 0 6px rgba(30, 215, 96, 0.55);
  pointer-events: none;
}
.route-row.drop-before::before { top: -5px; }
.route-row.drop-after::after { bottom: -5px; }
.route-row.is-default {
  border-color: rgba(30, 215, 96, 0.4);
  background: var(--surface-3);
}
.route-row.is-editing { border-color: var(--accent-strong); transform: none; }
.route-actions { margin-left: auto; flex-shrink: 0; display: flex; gap: 8px; }
.route-edit { display: flex; flex: 1; gap: 10px; min-width: 0; align-items: center; }
.route-edit .vh-input { width: auto; }
.route-edit .vh-input.edit-prefix { flex: 1; min-width: 0; }
.radio {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-3);
  font-size: 12.5px;
  cursor: pointer;
  white-space: nowrap;
}
.radio-wrap { position: relative; display: inline-flex; }
.radio-wrap input {
  position: absolute;
  opacity: 0;
  width: 18px;
  height: 18px;
  margin: 0;
  cursor: pointer;
}
.radio-box {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  transition: background 0.16s ease, border-color 0.16s ease;
  pointer-events: none;
}
.radio-box::after {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-1);
  transform: scale(0);
  transition: transform 0.18s var(--ease-spring);
}
.radio-wrap input:checked + .radio-box {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
  animation: radio-pop 0.32s var(--ease-spring);
}
@keyframes radio-pop {
  0% { transform: scale(0.72); }
  100% { transform: scale(1); }
}
.radio-wrap input:checked + .radio-box::after { transform: scale(1); }
.radio-wrap input:focus-visible + .radio-box {
  box-shadow: 0 0 0 3px rgba(30, 215, 96, 0.25);
}
.route-name { min-width: 96px; font-weight: 600; font-size: 13.5px; color: var(--text-1); }
.route-prefix {
  flex: 1;
  min-width: 0;
  color: var(--text-3);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.blank { margin: 0; color: var(--text-3); font-size: 13px; padding: 8px 0; }

.add-row {
  display: flex;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.add-row .prefix { flex: 1; }
.add-row .vh-input { width: auto; }
.add-row .vh-input.prefix { flex: 1; min-width: 0; }

/* 用户 */
.users {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.user-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  transition: background 0.16s ease;
  border-radius: var(--r-sm);
  padding-left: 8px;
  padding-right: 8px;
  margin: 0 -8px;
  animation: vh-fade-in-up 0.4s var(--ease-out) both;
}
.user-row:hover { background: var(--bg-raise); }
.user-row + .user-row { border-top: 1px solid var(--line); }
.avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-pill);
  background: var(--surface-3);
  border: 1px solid var(--line-strong);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.user-info { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.user-name { font-size: 14px; font-weight: 500; color: var(--text-1); }
.admin-chip {
  padding: 2px 9px;
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11.5px;
  font-weight: 600;
  flex-shrink: 0;
}
.user-actions { margin-left: auto; flex-shrink: 0; display: flex; gap: 8px; }
.reset-result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--accent-soft);
  color: var(--text-1);
  font-size: 13px;
}
.reset-result svg { color: var(--accent); flex-shrink: 0; }
.reset-pwd {
  font-family: ui-monospace, monospace;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--accent);
  background: var(--surface-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  padding: 3px 8px;
  user-select: all;
}
.reset-close {
  margin-left: auto;
  border: none;
  background: none;
  color: var(--text-3);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}
.reset-close:hover { color: var(--text-1); }
.users-add .vh-input { flex: 1; min-width: 0; }
.users-add .vh-input.is-taken { border-color: rgba(243, 114, 127, 0.65); }
.dup-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  color: var(--danger);
  font-size: 12.5px;
}

/* 访问记录 */
.acc-table {
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}
.acc-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.6fr) minmax(120px, 1fr) repeat(3, minmax(56px, 0.55fr)) 18px;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  margin: 0 -8px;
  border-radius: var(--r-sm);
}
.acc-head {
  padding-top: 14px;
  padding-bottom: 8px;
  color: var(--text-3);
  font-size: 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  margin: 0;
}
.acc-body {
  width: 100%;
  border: 0;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, box-shadow 0.16s ease;
}
.acc-body:hover { background: var(--bg-raise); box-shadow: inset 2px 0 0 var(--accent); }
.acc-body + .acc-body { border-top: 1px solid var(--line); }
.acc-body.open { background: var(--accent-soft); }
.acc-num { text-align: right; }
.strong { font-weight: 700; color: var(--text-1); }
.gold { color: var(--gold-bright); }
.acc-user {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-1);
}
.avatar.sm {
  width: 24px;
  height: 24px;
  font-size: 11px;
  border-radius: var(--r-pill);
}
.acc-time { color: var(--text-2); font-size: 13px; }
.acc-caret {
  color: var(--text-3);
  transition: transform 0.25s var(--ease-out), color 0.16s ease;
}
.acc-caret.flip { transform: rotate(180deg); color: var(--accent); }
.acc-detail {
  margin-top: 14px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface-3);
  /* 顶部吸顶导航遮挡补偿，配合 scrollIntoView 使用 */
  scroll-margin-top: calc(var(--nav-h) + 12px);
}
.acc-detail-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0 0 10px;
  color: var(--text-1);
  font-size: 13.5px;
  font-weight: 600;
}
.acc-detail-title .num { color: var(--text-3); font-size: 12px; font-weight: 400; }
.acc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.acc-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 13px;
}
.acc-item + .acc-item { border-top: 1px solid var(--line); }
.acc-item-detail {
  flex: 1;
  min-width: 0;
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.acc-item-time { color: var(--text-3); flex-shrink: 0; }
.acc-chip {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--r-pill);
  font-size: 11.5px;
  font-weight: 600;
  background: var(--surface-3);
  border: 1px solid var(--line);
  color: var(--text-2);
}
.acc-chip.is-visit { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.acc-chip.is-login { background: var(--ok-soft); border-color: transparent; color: var(--ok); }
.acc-chip.is-register { background: var(--gold-soft); border-color: transparent; color: var(--gold-bright); }
.acc-chip.is-parse { background: var(--danger-soft); border-color: transparent; color: var(--danger); }
.acc-more-btn { margin-top: 12px; }
.spin { animation: acc-spin 0.9s linear infinite; }
@keyframes acc-spin { to { transform: rotate(360deg); } }

/* 提示过渡 */
.alert-enter-active,
.alert-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease, margin 0.25s ease, padding 0.25s ease;
  overflow: hidden;
}
.alert-enter-from,
.alert-leave-to {
  opacity: 0;
  transform: translateY(-6px);
  margin-top: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

/* ---- 移动端 ---- */
@media (max-width: 720px) {
  .section :deep(.vhx-head) { padding: 16px 18px; }
  .key-row { flex-direction: column; align-items: stretch; }
  .save-btn { width: 100%; }
  .add-row { flex-wrap: wrap; }
  .route-prefix { display: none; }
  .route-edit { flex-wrap: wrap; }
  .route-edit .vh-input.edit-prefix { flex: 1 1 100%; }
  .route-actions { margin-left: auto; }
  .user-info { flex-direction: column; align-items: flex-start; gap: 4px; }
  .acc-row { grid-template-columns: minmax(96px, 1.4fr) repeat(3, minmax(48px, 0.8fr)) 18px; }
  .acc-head span:nth-child(2),
  .acc-body .acc-time { display: none; }
}

/* ---- 权限编辑弹层（玻璃弹窗语言与 App.vue 修改密码弹层同款；
 * pwd-* 规则原定义在 App.vue 的 scoped 样式中不跨文件生效，此处为本页弹层独立复制） ---- */
.pwd-mask {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(10, 14, 24, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.pwd-dialog {
  width: 100%;
  max-width: 380px;
  padding: 22px 24px 24px;
  border-radius: 18px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border: 1px solid var(--glass-line);
  box-shadow: var(--shadow-3);
}
.pwd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.pwd-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-1);
}
.pwd-title :deep(svg) { color: var(--accent); }
.pwd-close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background var(--dur-2) ease, color var(--dur-2) ease;
}
.pwd-close:hover { background: var(--surface); color: var(--text-1); }
.pwd-submit { height: 42px; margin-top: 4px; border: 0; }
.pwd-fade-enter-active,
.pwd-fade-leave-active { transition: opacity 0.22s ease; }
.pwd-fade-enter-from,
.pwd-fade-leave-to { opacity: 0; }
.perms-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; }
.perms-item { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--text-2); cursor: pointer; }
.perms-item input { accent-color: var(--accent); width: 15px; height: 15px; }
.perms-note { margin: 0 0 14px; font-size: 12.5px; color: var(--text-3); line-height: 1.6; }
</style>
