<template>
  <section class="page" data-module="rental-reminder">
    <header class="page-head">
      <div>
        <h2>到期提醒</h2>
        <p class="page-desc">提醒里的到期日期、状态与场租合同台账同源；已到期的合同只提示处置、不再提供续租入口。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/rental">前往场租合同台账</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text" role="alert">{{ errorMessage }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>提醒内容</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="String(item.id)">
          <td v-for="column in columns" :key="column">{{ item[column] ?? '—' }}</td>
          <td>{{ item['提醒'] }}</td>
          <td>
            <RouterLink v-if="item.can_renew" class="link" to="/rental">去申请续租</RouterLink>
            <span v-else class="muted-text">已到期，不能续租</span>
          </td>
        </tr>
        <tr v-if="!items.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无即将到期或已到期的合同</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ items.length }} 条到期提醒，到期日期与台账保持一致</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Reminder = {
  id: number
  合同编号: string
  站点名称: string
  出租方: string
  到期日期: string
  状态: string
  提醒: string
  can_renew: boolean
  [key: string]: string | number | boolean
}

const ENDPOINT = '/api/rental/reminders'
const columns = ['合同编号', '站点名称', '出租方', '到期日期', '状态']

const items = ref<Reminder[]>([])
const errorMessage = ref('')

onMounted(async () => {
  try {
    const payload = await fetchJson<{ items: Reminder[] }>(ENDPOINT)
    items.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '到期提醒读取失败'
  }
})
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.btn { text-decoration: none; display: inline-block; }
</style>
