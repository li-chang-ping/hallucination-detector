<script setup lang="ts">
import { Plus, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadInstance, type UploadRawFile } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import type { DetectionTask, KnowledgeBase } from '../types'
import { formatTime, statusText } from '../utils'

const router = useRouter()
const tasks = ref<DetectionTask[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const createVisible = ref(false)
const submitting = ref(false)
const uploadRef = ref<UploadInstance>()
const selectedFile = ref<UploadRawFile>()
const form = ref({ name: '', knowledge_base_id: '' })

async function load() {
  loading.value = true
  try {
    const [taskResponse, kbResponse] = await Promise.all([
      api.get<DetectionTask[]>('/tasks'),
      api.get<KnowledgeBase[]>('/knowledge-bases'),
    ])
    tasks.value = taskResponse.data
    knowledgeBases.value = kbResponse.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function selectFile(file: { raw?: UploadRawFile }) {
  selectedFile.value = file.raw
}

async function createTask() {
  if (!form.value.name || !form.value.knowledge_base_id || !selectedFile.value) {
    return ElMessage.warning('请完整填写任务信息并选择回复 JSON')
  }
  const data = new FormData()
  data.append('name', form.value.name)
  data.append('knowledge_base_id', form.value.knowledge_base_id)
  data.append('file', selectedFile.value)
  submitting.value = true
  try {
    const response = await api.post<DetectionTask>('/tasks', data)
    ElMessage.success('检测任务已创建')
    createVisible.value = false
    router.push(`/tasks/${response.data.id}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function action(task: DetectionTask, name: 'pause' | 'resume' | 'cancel') {
  try {
    await api.post(`/tasks/${task.id}/${name}`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div class="page-heading">
    <div>
      <h2>检测任务</h2>
      <p>批量审计客服回复，追踪证据、分类与检出率。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="createVisible = true">新建检测任务</el-button>
  </div>
  <el-card class="panel" shadow="never">
    <div class="toolbar">
      <el-input placeholder="按任务名称搜索" clearable style="width: 280px" />
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>
    <el-table
      :data="tasks"
      v-loading="loading"
      @row-click="(row: DetectionTask) => router.push(`/tasks/${row.id}`)"
    >
      <el-table-column label="任务" min-width="220"
        ><template #default="{ row }"
          ><strong>{{ row.name }}</strong>
          <div class="mono-id">{{ row.id }}</div></template
        ></el-table-column
      >
      <el-table-column label="状态" width="130"
        ><template #default="{ row }"
          ><span :class="['status-dot', `status-${row.status}`]" />{{
            statusText[row.status as keyof typeof statusText]
          }}</template
        ></el-table-column
      >
      <el-table-column label="进度" width="190"
        ><template #default="{ row }"
          ><el-progress
            :percentage="
              row.total_count
                ? Math.round(((row.completed_count + row.error_count) / row.total_count) * 100)
                : 0
            " /></template
      ></el-table-column>
      <el-table-column prop="model_name" label="模型" width="175" />
      <el-table-column label="创建时间" width="180"
        ><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column
      >
      <el-table-column label="操作" width="210" @click.stop
        ><template #default="{ row }">
          <el-button
            v-if="['running', 'queued', 'preparing'].includes(row.status)"
            link
            type="warning"
            @click.stop="action(row, 'pause')"
            >暂停</el-button
          >
          <el-button
            v-if="row.status === 'paused'"
            link
            type="primary"
            @click.stop="action(row, 'resume')"
            >继续</el-button
          >
          <el-button
            v-if="!['completed', 'partial', 'cancelled'].includes(row.status)"
            link
            type="danger"
            @click.stop="action(row, 'cancel')"
            >取消</el-button
          >
          <el-button link type="primary" @click.stop="router.push(`/tasks/${row.id}`)"
            >查看</el-button
          >
        </template></el-table-column
      >
    </el-table>
    <div v-if="!tasks.length && !loading" class="empty-hint">尚无检测任务</div>
  </el-card>
  <el-dialog v-model="createVisible" title="新建检测任务" width="560px">
    <el-form label-position="top"
      ><el-form-item label="任务名称"
        ><el-input v-model="form.name" placeholder="例如：1 月客服回复审计"
      /></el-form-item>
      <el-form-item label="知识库"
        ><el-select
          v-model="form.knowledge_base_id"
          placeholder="选择检索证据来源"
          style="width: 100%"
          ><el-option
            v-for="kb in knowledgeBases"
            :key="kb.id"
            :label="`${kb.name}（${kb.entry_count} 条）`"
            :value="kb.id" /></el-select
      ></el-form-item>
      <el-form-item label="回复数据"
        ><el-upload
          ref="uploadRef"
          class="upload-box"
          drag
          :auto-upload="false"
          :limit="1"
          accept=".json"
          :on-change="selectFile"
          ><el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或点击选择 JSON 文件</div>
          <template #tip
            ><div class="el-upload__tip">每项包含 id、user_question、system_reply</div></template
          ></el-upload
        ></el-form-item
      > </el-form
    ><template #footer
      ><el-button @click="createVisible = false">取消</el-button
      ><el-button type="primary" :loading="submitting" @click="createTask"
        >创建并开始</el-button
      ></template
    >
  </el-dialog>
</template>
