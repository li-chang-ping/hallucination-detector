<script setup lang="ts">
import { ArrowLeft, Refresh, Upload } from '@element-plus/icons-vue'
import { ElMessage, type UploadRawFile } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import type { DetectionItem, DetectionTask, Evaluation } from '../types'
import { percent, statusText } from '../utils'

const route = useRoute(),
  router = useRouter(),
  task = ref<DetectionTask>(),
  evaluations = ref<Evaluation[]>([]),
  drawer = ref(false),
  activeItem = ref<DetectionItem>(),
  evaluationFile = ref<UploadRawFile>()
let timer: number | undefined
const latest = computed(() => evaluations.value[0]),
  hallucinations = computed(() => task.value?.items?.filter((x) => x.is_hallucination).length || 0),
  tokens = computed(
    () =>
      task.value?.items?.reduce((sum, x) => sum + x.prompt_tokens + x.completion_tokens, 0) || 0,
  )
async function load() {
  try {
    task.value = (await api.get<DetectionTask>(`/tasks/${route.params.id}`)).data
    evaluations.value = (await api.get<Evaluation[]>(`/evaluations/tasks/${route.params.id}`)).data
    if (['completed', 'partial', 'failed', 'cancelled'].includes(task.value.status) && timer) {
      clearInterval(timer)
      timer = undefined
    }
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
function show(item: DetectionItem) {
  activeItem.value = item
  drawer.value = true
}
async function evaluate() {
  if (!evaluationFile.value) return ElMessage.warning('请选择人工标注 JSON')
  const data = new FormData()
  data.append('file', evaluationFile.value)
  try {
    await api.post(`/evaluations/tasks/${route.params.id}`, data)
    ElMessage.success('评测完成')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
onMounted(() => {
  load()
  timer = window.setInterval(load, 2500)
})
onBeforeUnmount(() => timer && clearInterval(timer))
</script>
<template>
  <div class="page-heading">
    <div>
      <el-button link :icon="ArrowLeft" @click="router.push('/tasks')">返回任务</el-button>
      <h2 style="margin-top: 8px">{{ task?.name || '任务详情' }}</h2>
      <p class="mono-id">{{ task?.id }}</p>
    </div>
    <el-button :icon="Refresh" @click="load">刷新</el-button>
  </div>
  <template v-if="task"
    ><div class="metric-grid">
      <div class="metric-card">
        <span>任务状态</span
        ><strong style="font-size: 21px"
          ><span :class="['status-dot', `status-${task.status}`]" />{{
            statusText[task.status]
          }}</strong
        ><small>{{ task.model_name }}</small>
      </div>
      <div class="metric-card">
        <span>检测进度</span
        ><strong>{{ task.completed_count + task.error_count }} / {{ task.total_count }}</strong
        ><el-progress
          :show-text="false"
          :percentage="
            Math.round(((task.completed_count + task.error_count) / task.total_count) * 100)
          "
        />
      </div>
      <div class="metric-card">
        <span>幻觉回复</span><strong class="danger-value">{{ hallucinations }}</strong
        ><small>当前已完成结果</small>
      </div>
      <div class="metric-card">
        <span>Token 用量</span><strong>{{ tokens.toLocaleString() }}</strong
        ><small>输入与输出合计</small>
      </div>
    </div>
    <el-card v-if="latest" class="panel" shadow="never"
      ><template #header><strong>人工评测结果</strong></template>
      <div class="metric-grid" style="margin: 0">
        <div class="metric-card">
          <span>Recall 检出率</span
          ><strong class="success-value">{{ percent(latest.metrics.recall) }}</strong
          ><small>漏检 {{ latest.metrics.fn }} 条</small>
        </div>
        <div class="metric-card">
          <span>Precision 准确率</span><strong>{{ percent(latest.metrics.precision) }}</strong
          ><small>误报 {{ latest.metrics.fp }} 条</small>
        </div>
        <div class="metric-card">
          <span>F1</span><strong>{{ percent(latest.metrics.f1) }}</strong
          ><small>综合指标</small>
        </div>
        <div class="metric-card">
          <span>分类命中率</span
          ><strong>{{ percent(latest.metrics.multilabel_category_hit_rate) }}</strong
          ><small>多标签包含预期分类</small>
        </div>
      </div>
      <el-alert
        v-if="latest.metrics.false_negative_ids?.length"
        type="error"
        :closable="false"
        :title="`漏检：${latest.metrics.false_negative_ids.join('、')}`"
        style="margin-top: 16px" /><el-alert
        v-if="latest.metrics.false_positive_ids?.length"
        type="warning"
        :closable="false"
        :title="`误报：${latest.metrics.false_positive_ids.join('、')}`"
        style="margin-top: 10px"
    /></el-card>
    <el-card class="panel" shadow="never"
      ><template #header
        ><div style="display: flex; justify-content: space-between; align-items: center">
          <strong>逐条检测结果</strong>
          <div style="display: flex; gap: 8px">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept=".json"
              :show-file-list="false"
              :on-change="(f: any) => (evaluationFile = f.raw)"
              ><el-button :icon="Upload">选择人工标注</el-button></el-upload
            ><el-button type="primary" :disabled="!evaluationFile" @click="evaluate"
              >开始比对</el-button
            >
          </div>
        </div></template
      >
      <el-table :data="task.items"
        ><el-table-column prop="input_id" label="ID" width="90" /><el-table-column
          prop="user_question"
          label="用户问题"
          min-width="210"
          show-overflow-tooltip
        /><el-table-column
          prop="system_reply"
          label="系统回复"
          min-width="300"
          show-overflow-tooltip
        /><el-table-column label="判定" width="100"
          ><template #default="{ row }"
            ><el-tag v-if="row.is_hallucination === true" type="danger">幻觉</el-tag
            ><el-tag v-else-if="row.is_hallucination === false" type="success">正常</el-tag
            ><el-tag v-else type="info">{{ row.status }}</el-tag></template
          ></el-table-column
        ><el-table-column prop="primary_category" label="主分类" width="150" /><el-table-column
          label="置信度"
          width="105"
          ><template #default="{ row }">{{
            row.confidence == null ? '—' : percent(row.confidence)
          }}</template></el-table-column
        ><el-table-column label="操作" width="90"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="show(row)">详情</el-button></template
          ></el-table-column
        ></el-table
      ></el-card
    ></template
  >
  <el-drawer v-model="drawer" title="检测证据与判断" size="520px"
    ><template v-if="activeItem"
      ><el-descriptions :column="1" border
        ><el-descriptions-item label="输入 ID">{{ activeItem.input_id }}</el-descriptions-item
        ><el-descriptions-item label="分类">{{
          activeItem.category_names.join('、') || '正常'
        }}</el-descriptions-item
        ><el-descriptions-item label="严重度">{{ activeItem.severity || '—' }}</el-descriptions-item
        ><el-descriptions-item label="判断依据">{{
          activeItem.rationale || activeItem.error_message || '处理中'
        }}</el-descriptions-item></el-descriptions
      >
      <h4>检索证据</h4>
      <div v-for="e in activeItem.evidence_snapshot" :key="e.id" class="evidence-card">
        <span class="mono-id"
          >{{ e.metadata?.external_id || e.id }} · distance
          {{ Number(e.distance).toFixed(3) }}</span
        >
        <p>{{ e.content }}</p>
      </div></template
    ></el-drawer
  >
</template>
