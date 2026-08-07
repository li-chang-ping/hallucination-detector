<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Category, CategoryVersion, Severity } from '../types'
import { categorySnapshotStatus, formatTime } from '../utils'

const categories = ref<Category[]>([])
const visible = ref(false)
const editingId = ref<string>()
const historyVisible = ref(false)
const historyCategory = ref<Category>()
const versions = ref<CategoryVersion[]>([])
const rollbackBusy = ref<string>()
const form = ref({
  name: '',
  description: '',
  default_severity: 'high' as Severity,
  prompt_guidance: '',
  is_active: true,
})
const severityLabels: Record<Severity, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
}

async function load() {
  try {
    categories.value = (
      await api.get<Category[]>('/categories', { params: { include_archived: true } })
    ).data
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
function open(item?: Category) {
  editingId.value = item?.id
  form.value = item
    ? {
        name: item.name,
        description: item.description,
        default_severity: item.default_severity,
        prompt_guidance: item.prompt_guidance,
        is_active: item.is_active,
      }
    : { name: '', description: '', default_severity: 'high', prompt_guidance: '', is_active: true }
  visible.value = true
}
async function save() {
  try {
    editingId.value
      ? await api.put(`/categories/${editingId.value}`, form.value)
      : await api.post('/categories', form.value)
    ElMessage.success('分类已保存')
    visible.value = false
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function archive(item: Category) {
  await ElMessageBox.confirm(`确认归档“${item.name}”？`, '归档分类', { type: 'warning' })
  try {
    await api.delete(`/categories/${item.id}`)
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function openHistory(item: Category) {
  historyCategory.value = item
  try {
    versions.value = (await api.get<CategoryVersion[]>(`/categories/${item.id}/versions`)).data
    historyVisible.value = true
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function rollback(version: CategoryVersion) {
  if (!historyCategory.value) return
  await ElMessageBox.confirm(
    '确认恢复到这个历史版本？当前定义也会保留为可回退版本。',
    '回退分类定义',
    { type: 'warning' },
  )
  rollbackBusy.value = version.id
  try {
    const categoryId = historyCategory.value.id
    await api.post(`/categories/${categoryId}/rollback/${version.id}`)
    ElMessage.success('分类定义已回退')
    await load()
    const current = categories.value.find((item) => item.id === categoryId)
    if (current) await openHistory(current)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    rollbackBusy.value = undefined
  }
}
onMounted(load)
</script>
<template>
  <div class="page-heading">
    <div>
      <h2>幻觉定义管理</h2>
      <p>维护业务分类、默认风险级别与模型判定指引。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="open()">新增分类</el-button>
  </div>
  <el-card class="panel" shadow="never"
    ><el-table :data="categories"
      ><el-table-column prop="name" label="分类名称" width="190"
        ><template #default="{ row }"
          ><strong>{{ row.name }}</strong
          ><el-tag v-if="row.is_archived" type="info" size="small" style="margin-left: 8px"
            >已归档</el-tag
          ></template
        ></el-table-column
      ><el-table-column prop="description" label="定义" min-width="280" /><el-table-column
        label="严重度"
        width="110"
        ><template #default="{ row }"
          ><el-tag
            :type="
              row.default_severity === 'critical'
                ? 'danger'
                : row.default_severity === 'high'
                  ? 'warning'
                  : 'info'
            "
            >{{ severityLabels[row.default_severity as Severity] }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column
        prop="prompt_guidance"
        label="判定指引"
        min-width="300"
        show-overflow-tooltip
      /><el-table-column label="启用" width="90"
        ><template #default="{ row }"
          ><el-switch
            v-model="row.is_active"
            :disabled="row.is_archived"
            @change="
              api.put(`/categories/${row.id}`, { is_active: row.is_active })
            " /></template></el-table-column
      ><el-table-column label="操作" width="195"
        ><template #default="{ row }"
          ><el-button v-if="!row.is_archived" link type="primary" @click="open(row)">编辑</el-button
          ><el-button link @click="openHistory(row)">历史</el-button
          ><el-button v-if="!row.is_archived" link type="danger" @click="archive(row)"
            >归档</el-button
          ></template
        ></el-table-column
      ></el-table
    ></el-card
  >
  <el-dialog v-model="visible" :title="editingId ? '编辑分类' : '新增分类'" width="600px"
    ><el-form label-position="top"
      ><el-form-item label="分类名称"><el-input v-model="form.name" /></el-form-item
      ><el-form-item label="分类定义"
        ><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item
      ><el-form-item label="默认严重度"
        ><el-select v-model="form.default_severity" style="width: 100%"
          ><el-option
            v-for="(label, key) in severityLabels"
            :key="key"
            :label="label"
            :value="key" /></el-select></el-form-item
      ><el-form-item label="模型判定指引"
        ><el-input v-model="form.prompt_guidance" type="textarea" :rows="3" /></el-form-item
      ><el-form-item
        ><el-checkbox v-model="form.is_active">立即启用</el-checkbox></el-form-item
      ></el-form
    ><template #footer
      ><el-button @click="visible = false">取消</el-button
      ><el-button type="primary" @click="save">保存</el-button></template
    ></el-dialog
  >
  <el-dialog
    v-model="historyVisible"
    :title="`${historyCategory?.name || ''} · 版本历史`"
    width="92%"
  >
    <el-alert
      title="每次编辑、采纳优化建议和回退都会生成版本快照。"
      type="info"
      :closable="false"
      style="margin-bottom: 14px"
    />
    <el-table :data="versions" max-height="520">
      <el-table-column label="时间" width="175" fixed>
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="变更来源" width="200" />
      <el-table-column label="分类名称" width="160">
        <template #default="{ row }">{{ row.snapshot.name }}</template>
      </el-table-column>
      <el-table-column label="分类定义" min-width="260">
        <template #default="{ row }">{{ row.snapshot.description }}</template>
      </el-table-column>
      <el-table-column label="判定指引" min-width="300">
        <template #default="{ row }">{{ row.snapshot.prompt_guidance || '—' }}</template>
      </el-table-column>
      <el-table-column label="严重度" width="90">
        <template #default="{ row }">
          {{
            severityLabels[row.snapshot.default_severity as Severity] ||
            row.snapshot.default_severity
          }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag
            :type="
              row.snapshot.is_archived ? 'info' : row.snapshot.is_active ? 'success' : 'warning'
            "
          >
            {{ categorySnapshotStatus(row.snapshot) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :loading="rollbackBusy === row.id" @click="rollback(row)"
            >回退</el-button
          >
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>
