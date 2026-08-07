<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Category, Severity } from '../types'

const categories = ref<Category[]>([])
const visible = ref(false)
const editingId = ref<string>()
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
    categories.value = (await api.get<Category[]>('/categories')).data
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
          ><strong>{{ row.name }}</strong></template
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
            @change="
              api.put(`/categories/${row.id}`, { is_active: row.is_active })
            " /></template></el-table-column
      ><el-table-column label="操作" width="140"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="open(row)">编辑</el-button
          ><el-button link type="danger" @click="archive(row)">归档</el-button></template
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
</template>
