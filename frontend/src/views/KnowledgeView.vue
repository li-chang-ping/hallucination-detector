<script setup lang="ts">
import { Delete, Plus, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadRawFile } from 'element-plus'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { KnowledgeBase, KnowledgeEntry } from '../types'

const bases = ref<KnowledgeBase[]>([]),
  entries = ref<KnowledgeEntry[]>([]),
  selected = ref<KnowledgeBase>(),
  visible = ref(false),
  importVisible = ref(false)
const editing = ref<KnowledgeEntry>(),
  importFile = ref<UploadRawFile>(),
  form = ref({ id: '', title: '', content: '', metadata: '{}' })
async function load() {
  try {
    bases.value = (await api.get<KnowledgeBase[]>('/knowledge-bases')).data
    if (selected.value) {
      selected.value = bases.value.find((x) => x.id === selected.value?.id)
      if (selected.value) await select(selected.value)
    }
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function select(kb: KnowledgeBase) {
  selected.value = kb
  entries.value = (await api.get<KnowledgeEntry[]>(`/knowledge-bases/${kb.id}/entries`)).data
}
function open(entry?: KnowledgeEntry) {
  editing.value = entry
  form.value = entry
    ? {
        id: entry.external_id,
        title: entry.title,
        content: entry.content,
        metadata: JSON.stringify(entry.extra_metadata, null, 2),
      }
    : { id: '', title: '', content: '', metadata: '{}' }
  visible.value = true
}
async function save() {
  if (!selected.value) return
  try {
    const data = {
      id: form.value.id,
      title: form.value.title,
      content: form.value.content,
      metadata: JSON.parse(form.value.metadata),
    }
    editing.value
      ? await api.put(`/knowledge-bases/${selected.value.id}/entries/${editing.value.id}`, data)
      : await api.post(`/knowledge-bases/${selected.value.id}/entries`, data)
    visible.value = false
    await load()
    ElMessage.success('知识条目已保存')
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function removeEntry(entry: KnowledgeEntry) {
  await ElMessageBox.confirm('删除后将同步移除向量索引，确认继续？', '删除条目', {
    type: 'warning',
  })
  await api.delete(`/knowledge-bases/${entry.knowledge_base_id}/entries/${entry.id}`)
  await load()
}
async function removeKb(kb: KnowledgeBase) {
  await ElMessageBox.confirm(`确认删除知识库“${kb.name}”及其全部条目？`, '删除知识库', {
    type: 'warning',
  })
  await api.delete(`/knowledge-bases/${kb.id}`)
  selected.value = undefined
  entries.value = []
  await load()
}
async function upload() {
  if (!importFile.value) return
  const data = new FormData()
  data.append('file', importFile.value)
  try {
    await api.post('/knowledge-bases/import', data)
    importVisible.value = false
    await load()
    ElMessage.success('知识库导入完成')
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
onMounted(load)
</script>
<template>
  <div class="page-heading">
    <div>
      <h2>知识库管理</h2>
      <p>通过 Ollama 中文向量模型建立可追溯的检测证据。</p>
    </div>
    <el-button type="primary" :icon="Upload" @click="importVisible = true">导入 JSON</el-button>
  </div>
  <el-row :gutter="18"
    ><el-col :span="8"
      ><el-card class="panel" shadow="never"
        ><template #header><strong>知识库</strong></template>
        <div
          v-for="kb in bases"
          :key="kb.id"
          class="evidence-card"
          style="cursor: pointer"
          @click="select(kb)"
        >
          <div style="display: flex; justify-content: space-between">
            <strong>{{ kb.name }}</strong
            ><el-button link type="danger" :icon="Delete" @click.stop="removeKb(kb)" />
          </div>
          <p>{{ kb.description || '暂无描述' }}</p>
          <el-tag size="small" effect="plain">{{ kb.entry_count }} 条</el-tag>
        </div>
        <div v-if="!bases.length" class="empty-hint">请先导入知识库</div></el-card
      ></el-col
    >
    <el-col :span="16"
      ><el-card class="panel" shadow="never"
        ><template #header
          ><div style="display: flex; justify-content: space-between">
            <strong>{{ selected?.name || '知识条目' }}</strong
            ><el-button v-if="selected" type="primary" plain :icon="Plus" @click="open()"
              >新增条目</el-button
            >
          </div></template
        ><el-table v-if="selected" :data="entries"
          ><el-table-column prop="external_id" label="外部 ID" width="120" /><el-table-column
            prop="title"
            label="标题"
            width="160"
          /><el-table-column
            prop="content"
            label="内容"
            min-width="300"
            show-overflow-tooltip
          /><el-table-column label="操作" width="130"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="open(row)">编辑</el-button
              ><el-button link type="danger" @click="removeEntry(row)">删除</el-button></template
            ></el-table-column
          ></el-table
        >
        <div v-else class="empty-hint">选择左侧知识库查看条目</div></el-card
      ></el-col
    ></el-row
  >
  <el-dialog v-model="importVisible" title="导入知识库 JSON" width="520px"
    ><el-upload
      drag
      class="upload-box"
      :auto-upload="false"
      :limit="1"
      accept=".json"
      :on-change="(f: any) => (importFile = f.raw)"
      ><div class="el-upload__text">拖入或点击选择知识库 JSON</div>
      <template #tip
        ><div class="el-upload__tip">结构：name、description、entries[]</div></template
      ></el-upload
    ><template #footer
      ><el-button @click="importVisible = false">取消</el-button
      ><el-button type="primary" @click="upload">导入并向量化</el-button></template
    ></el-dialog
  >
  <el-dialog v-model="visible" :title="editing ? '编辑知识条目' : '新增知识条目'" width="620px"
    ><el-form label-position="top"
      ><el-form-item label="外部 ID"
        ><el-input v-model="form.id" :disabled="!!editing" /></el-form-item
      ><el-form-item label="标题"><el-input v-model="form.title" /></el-form-item
      ><el-form-item label="内容"
        ><el-input v-model="form.content" type="textarea" :rows="6" /></el-form-item
      ><el-form-item label="Metadata JSON"
        ><el-input v-model="form.metadata" type="textarea" :rows="3" /></el-form-item></el-form
    ><template #footer
      ><el-button @click="visible = false">取消</el-button
      ><el-button type="primary" @click="save">保存并更新向量</el-button></template
    ></el-dialog
  >
</template>
