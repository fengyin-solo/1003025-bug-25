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
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!actionsFor(row).length" class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无场租合同数据，可先登记场租合同</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条场租合同记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记场租合同</h3>
        <label v-for="field in createFields" :key="field.name" class="form-item">
          <span>{{ field.name }}<em v-if="field.required" class="required-mark">*</em></span>
          <input
            v-model="createForm[field.name]"
            :type="field.type"
            :placeholder="field.required ? `必填，请填写${field.name}` : `选填，请填写${field.name}`"
          />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '提交登记' }}
          </button>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/rental'
const columns = ["合同编号", "站点名称", "出租方", "年租金", "签约日期", "到期日期", "续租条款", "合同状态"]
const statuses = ["执行中", "即将到期", "续租中", "已到期"]
// 每个状态可执行的动作：按 执行中→即将到期→续租中→已到期 的次序走，已到期的不能再续
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  执行中: ["登记到期", "确认到期"],
  即将到期: ["申请续租", "确认到期"],
  续租中: ["确认到期"],
  已到期: [],
}
const REQUIRED_CREATE_FIELDS = ["合同编号", "站点名称", "出租方", "年租金", "到期日期"]
const createFields = [
  { name: "合同编号", required: true, type: "text" },
  { name: "站点名称", required: true, type: "text" },
  { name: "出租方", required: true, type: "text" },
  { name: "年租金", required: true, type: "text" },
  { name: "签约日期", required: false, type: "date" },
  { name: "到期日期", required: true, type: "date" },
  { name: "续租条款", required: false, type: "text" },
]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref(statuses.map((status) => ({ label: `${status}合同`, value: 0 })))

const showCreate = ref(false)
const submitting = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row["合同状态"] ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
  createError.value = ''
}

async function submitCreate() {
  // 提交之前先校一遍必填，缺哪个点哪个的名
  const missing = REQUIRED_CREATE_FIELDS.filter((field) => !(createForm.value[field] ?? '').trim())
  if (missing.length) {
    createError.value = `缺少必填字段：${missing.join('、')}`
    return
  }
  submitting.value = true
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 提交不成留在原表单，填过的内容不丢，改完能直接重试
      createError.value = payload?.message ?? '场租合同登记失败，请稍后重试'
      return
    }
    closeCreate()
    noticeMessage.value = payload.message ?? '场租合同已登记'
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '场租合同登记失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? `场租合同${action}未生效，请稍后重试`)
    }
    noticeMessage.value = payload.message ?? `场租合同已${action}`
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场租合同操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('场租合同列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场租合同列表读取失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    stats.value = statuses.map((status) => ({
      label: `${status}合同`,
      value: Number(payload?.[status] ?? 0),
    }))
  } catch {
    // 提醒卡片读不到时保留上次结果，不打扰列表操作
  }
}

onMounted(() => {
  void reload()
  void reloadStats()
})
</script>

<style scoped>
.muted-text { color: var(--muted); }
.notice-text { color: #067647; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.modal {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal h3 { margin: 0 0 4px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.form-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.required-mark { color: #b42318; font-style: normal; margin-left: 2px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
