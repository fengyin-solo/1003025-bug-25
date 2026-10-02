<template>
  <section class="page" data-module="rental">
    <header class="page-head">
      <div>
        <h2>场租合同管理</h2>
        <p class="page-desc">维护场租合同，围绕合同编号、站点名称、出租方、年租金做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记场租合同</button>
        <button class="btn" type="button" @click="exportRows">导出场租合同清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="errorMessage" class="error-text" role="alert">{{ errorMessage }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="actionsFor(row).length">
              <button
                v-for="action in actionsFor(row)"
                :key="action"
                class="link"
                type="button"
                :disabled="busyId === String(row.id)"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">已到期，无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无场租合同数据，可先登记场租合同</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条场租合同记录</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="closeCreate">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="rental-create-title">
        <div class="modal-head">
          <h3 id="rental-create-title">登记场租合同</h3>
          <button class="link" type="button" @click="closeCreate">关闭</button>
        </div>

        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in formFields" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
            <input
              v-model="form[field.key]"
              :type="field.type"
              :placeholder="field.placeholder"
            />
          </label>

          <p v-if="formError" class="error-text" role="alert">{{ formError }}</p>

          <div class="modal-foot">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '提交中…' : '提交登记' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ActionResult = { ok: boolean; message: string; entry: Row | null }

const ENDPOINT = '/api/rental'
const columns = ["合同编号", "站点名称", "出租方", "年租金", "签约日期", "到期日期", "续租条款", "合同状态"]
const statuses = ["执行中", "即将到期", "续租中", "已到期"]

// 状态机在前端的镜像：每个状态允许发起的动作；已到期为终态、不给任何动作
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  执行中: ["登记到期"],
  即将到期: ["申请续租", "确认到期"],
  续租中: ["确认到期"],
  已到期: [],
}

const formFields = [
  { key: '合同编号', label: '合同编号', required: true, type: 'text', placeholder: '如 RENT-0005' },
  { key: '站点名称', label: '站点名称', required: true, type: 'text', placeholder: '如 城东基站' },
  { key: '出租方', label: '出租方', required: true, type: 'text', placeholder: '出租方全称' },
  { key: '年租金', label: '年租金（元）', required: true, type: 'text', placeholder: '如 36000' },
  { key: '到期日期', label: '到期日期', required: true, type: 'date', placeholder: 'YYYY-MM-DD' },
  { key: '签约日期', label: '签约日期', required: false, type: 'date', placeholder: 'YYYY-MM-DD' },
  { key: '续租条款', label: '续租条款', required: false, type: 'text', placeholder: '续租约定（选填）' },
] as const
const REQUIRED_LABELS: Record<string, string> = {
  合同编号: '合同编号',
  站点名称: '站点名称',
  出租方: '出租方',
  年租金: '年租金',
  到期日期: '到期日期',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const busyId = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const creating = ref(false)
const submitting = ref(false)
const formError = ref('')
const form = reactive<Record<string, string>>({})

const stats = computed(() => [
  { label: '执行中合同', value: rows.value.filter((row) => row.status === '执行中').length },
  { label: '即将到期合同', value: rows.value.filter((row) => row.status === '即将到期').length },
  { label: '续租中合同', value: rows.value.filter((row) => row.status === '续租中').length },
  { label: '已到期合同', value: rows.value.filter((row) => row.status === '已到期').length },
])

function statusOf(row: Row): string {
  return String(row.status ?? row['合同状态'] ?? '')
}

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[statusOf(row)] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function resetForm() {
  for (const field of formFields) {
    form[field.key] = ''
  }
}

function openCreate() {
  // 上一次失败的填写内容原样保留，成功或主动取消后才清空
  if (!creating.value) {
    resetForm()
  }
  formError.value = ''
  creating.value = true
}

function closeCreate() {
  creating.value = false
  formError.value = ''
}

function validateForm(): string {
  const missing = Object.keys(REQUIRED_LABELS)
    .filter((key) => !form[key]?.trim())
    .map((key) => REQUIRED_LABELS[key])
  if (missing.length) {
    return `请补全必填项：${missing.join('、')}`
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form['到期日期'].trim())) {
    return '到期日期格式不正确，应为 YYYY-MM-DD'
  }
  return ''
}

async function submitCreate() {
  // 提交前先在前端拦一道必填；后端还会再校一遍
  formError.value = validateForm()
  if (formError.value) {
    return
  }
  submitting.value = true
  try {
    const values: Record<string, string> = {}
    for (const field of formFields) {
      const text = form[field.key]?.trim()
      if (text) {
        values[field.key] = text
      }
    }
    const payload = await requestJson<ActionResult>('', {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    if (!payload.ok) {
      // 提交没成功：表单内容保留，错误点名，用户改完直接重试
      formError.value = payload.message || '登记未生效，请检查后重试'
      return
    }
    creating.value = false
    resetForm()
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '登记请求失败，请重试'
  } finally {
    submitting.value = false
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(`${ENDPOINT}${path}`, init)
  let payload: T | null = null
  try {
    payload = (await response.json()) as T
  } catch {
    // 响应体不是 JSON，落到下面统一报错
  }
  if (!response.ok || payload === null) {
    throw new Error(`接口返回 ${response.status}，操作未生效，请重试`)
  }
  return payload
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  busyId.value = String(row.id)
  try {
    const payload = await requestJson<ActionResult>(`/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!payload.ok) {
      // 例如「已到期，不能再续租」「当前状态不能执行」——直接把原因亮给用户
      errorMessage.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场租合同操作失败，请重试'
  } finally {
    busyId.value = ''
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const payload = await requestJson<{ items: Row[]; total: number }>(`?${query}`)
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场租合同列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.required-mark { color: #b42318; font-style: normal; margin-left: 2px; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 520px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 8px;
  padding: 16px 18px;
}
.modal-head { display: flex; justify-content: space-between; align-items: center; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; margin-top: 12px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.modal-form .error-text { grid-column: 1 / -1; margin: 0; }
.modal-foot { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 8px; }
</style>
