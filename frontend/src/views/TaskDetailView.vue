<script setup lang="ts">
import { ArrowLeft, Refresh, Upload } from '@element-plus/icons-vue'
import {
  ElMessage,
  ElMessageBox,
  genFileId,
  type UploadInstance,
  type UploadProps,
  type UploadRawFile,
} from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import type { DetectionItem, DetectionTask, Evaluation, EvaluationProgressEvent } from '../types'
import {
  canEvaluateTask,
  categoryChangeEntries,
  formatCategoryMismatches,
  isDialogCancelled,
  percent,
  statusText,
  taskProgress,
} from '../utils'

const route = useRoute(),
  router = useRouter(),
  task = ref<DetectionTask>(),
  evaluations = ref<Evaluation[]>([]),
  drawer = ref(false),
  activeItem = ref<DetectionItem>(),
  evaluationFile = ref<UploadRawFile>(),
  evaluationUpload = ref<UploadInstance>()
const suggestionPlanBusy = ref(false)
const evaluating = ref(false)
const evaluationProgress = ref(0)
const evaluationStage = ref('')
const evaluationProgressStatus = ref<'' | 'success' | 'exception'>('')
const evaluationEvents = ref<EvaluationProgressEvent[]>([])
const suggestionActionLabels = { create: '新增', update: '修改', archive: '归档' } as const
let timer: number | undefined
let evaluationSource: EventSource | undefined
const latest = computed(() => evaluations.value[0]),
  hasPendingSuggestionPlan = computed(
    () =>
      Boolean(latest.value?.suggestions?.length) &&
      latest.value.suggestions.every((item) => item.status === 'pending'),
  ),
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
const handleEvaluationExceed: UploadProps['onExceed'] = (files) => {
  const replacement = files[0] as UploadRawFile
  evaluationUpload.value?.clearFiles()
  replacement.uid = genFileId()
  evaluationUpload.value?.handleStart(replacement)
  evaluationFile.value = replacement
}
function clearEvaluationFile() {
  evaluationUpload.value?.clearFiles()
  evaluationFile.value = undefined
}
async function evaluate() {
  if (!evaluationFile.value) return ElMessage.warning('请选择人工标注 JSON')
  if (evaluating.value) return
  const data = new FormData()
  data.append('file', evaluationFile.value)
  evaluating.value = true
  evaluationProgress.value = 0
  evaluationStage.value = '正在上传人工标注'
  evaluationEvents.value = []
  evaluationProgressStatus.value = ''
  try {
    const response = await api.post<Evaluation>(`/evaluations/tasks/${route.params.id}`, data, {
      onUploadProgress(event) {
        if (!event.total) return
        const uploadPercent = Math.round((event.loaded / event.total) * 10)
        evaluationProgress.value = Math.min(10, uploadPercent)
        if (event.loaded >= event.total) {
          evaluationStage.value = '人工标注已上传，正在创建后台评测'
        }
      },
    })
    evaluations.value = [response.data, ...evaluations.value]
    evaluationProgress.value = response.data.insight_progress
    evaluationStage.value = response.data.insight_stage
    evaluationEvents.value = response.data.insight_events || []
    await subscribeEvaluation(response.data.id)
    await load()
    const completed = evaluations.value.find((item) => item.id === response.data.id)
    evaluationProgress.value = 100
    if (completed?.insight_status === 'fallback') {
      evaluationProgressStatus.value = 'exception'
      evaluationStage.value = completed.insight_stage
      ElMessage.warning('比较完成，但 AI 优化建议生成失败')
    } else {
      evaluationProgressStatus.value = 'success'
      evaluationStage.value = completed?.insight_stage || '比较完成'
      ElMessage.success('评测完成')
    }
  } catch (e) {
    const message = (e as Error).message
    evaluationProgressStatus.value = 'exception'
    evaluationStage.value = `比较失败：${message}`
    ElMessage.error(message)
  } finally {
    evaluating.value = false
  }
}

function subscribeEvaluation(evaluationId: string) {
  return new Promise<void>((resolve, reject) => {
    evaluationSource?.close()
    const source = new EventSource(`/api/v1/evaluations/${evaluationId}/events`)
    evaluationSource = source
    let finished = false
    source.addEventListener('progress', (event) => {
      const progressEvent = JSON.parse(
        (event as MessageEvent<string>).data,
      ) as EvaluationProgressEvent
      evaluationProgress.value = progressEvent.progress
      evaluationStage.value = progressEvent.stage
      if (!evaluationEvents.value.some((item) => item.sequence === progressEvent.sequence)) {
        evaluationEvents.value.push(progressEvent)
      }
    })
    source.addEventListener('complete', () => {
      finished = true
      source.close()
      evaluationSource = undefined
      resolve()
    })
    source.addEventListener('failed', (event) => {
      finished = true
      source.close()
      evaluationSource = undefined
      const payload = JSON.parse((event as MessageEvent<string>).data) as { stage?: string }
      reject(new Error(payload.stage || '评测事件流失败'))
    })
    source.onerror = () => {
      if (finished) return
      source.close()
      evaluationSource = undefined
      reject(new Error('评测进度连接中断，请刷新页面查看最新结果'))
    }
  })
}

async function initialize() {
  await load()
  const current = latest.value
  if (current && ['pending', 'running'].includes(current.insight_status)) {
    evaluating.value = true
    evaluationProgress.value = current.insight_progress
    evaluationStage.value = current.insight_stage
    evaluationEvents.value = current.insight_events || []
    try {
      await subscribeEvaluation(current.id)
      await load()
      evaluationProgress.value = 100
      evaluationStage.value = latest.value?.insight_stage || '比较完成'
      evaluationProgressStatus.value =
        latest.value?.insight_status === 'fallback' ? 'exception' : 'success'
    } catch (e) {
      evaluationProgressStatus.value = 'exception'
      evaluationStage.value = (e as Error).message
    } finally {
      evaluating.value = false
    }
  }
}
async function decideSuggestionPlan(action: 'apply' | 'reject') {
  try {
    await ElMessageBox.confirm(
      action === 'apply'
        ? '将以一个事务执行全部新增、修改和归档操作，任一步失败都会全部回滚。确认采纳整套方案？'
        : '确认忽略本次评测的整套优化方案？',
      action === 'apply' ? '采纳整套优化方案' : '忽略整套优化方案',
      { type: action === 'apply' ? 'warning' : 'info' },
    )
    suggestionPlanBusy.value = true
    await api.post(`/evaluations/${latest.value.id}/suggestions/${action}-all`)
    ElMessage.success(action === 'apply' ? '整套方案已采纳并更新幻觉定义' : '整套方案已忽略')
    await load()
  } catch (e) {
    if (!isDialogCancelled(e)) ElMessage.error((e as Error).message)
  } finally {
    suggestionPlanBusy.value = false
  }
}
onMounted(() => {
  void initialize()
  timer = window.setInterval(load, 2500)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  evaluationSource?.close()
})
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
          :percentage="taskProgress(task.total_count, task.completed_count, task.error_count)"
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
      <el-alert
        v-if="latest.insight_status === 'fallback'"
        type="warning"
        :closable="false"
        title="AI 优化建议生成失败，当前仅展示规则化误判分析"
        :description="latest.insight_error || 'DeepSeek 未返回有效的误判分析与优化建议。'"
        style="margin-bottom: 16px"
      />
      <el-alert
        v-else-if="
          latest.insight_status === 'unknown' &&
          latest.analyses?.length &&
          !latest.suggestions?.length
        "
        type="warning"
        :closable="false"
        title="该历史评测未生成优化建议"
        description="历史数据未记录 DeepSeek 分析状态；请重新上传人工标注进行比较。"
        style="margin-bottom: 16px"
      />
      <div class="metric-grid" style="margin: 0">
        <div class="metric-card">
          <span>Recall 检出率</span
          ><strong class="success-value">{{ percent(latest.metrics.recall) }}</strong
          ><small>漏检 {{ latest.metrics.fn }} 条 · 人工为幻觉，模型判正常</small>
        </div>
        <div class="metric-card">
          <span>Accuracy 正确率</span><strong>{{ percent(latest.metrics.accuracy) }}</strong
          ><small
            >正确 {{ Number(latest.metrics.tp || 0) + Number(latest.metrics.tn || 0) }} /
            {{ latest.metrics.evaluated_count || latest.ground_truth_count }} 条 ·
            幻觉判定和分类均需与人工一致</small
          >
        </div>
      </div>
      <el-alert
        v-if="latest.metrics.false_negative_ids?.length"
        type="error"
        :closable="false"
        :title="`漏检：${latest.metrics.false_negative_ids.join('、')}`"
        style="margin-top: 16px"
      /><el-alert
        v-if="latest.metrics.false_positive_ids?.length"
        type="warning"
        :closable="false"
        :title="`误报：${latest.metrics.false_positive_ids.join('、')}`"
        style="margin-top: 10px"
      /><el-alert
        v-if="latest.metrics.category_mismatches?.length"
        type="error"
        :closable="false"
        :title="`分类不一致：${formatCategoryMismatches(latest.metrics.category_mismatches)}`"
        style="margin-top: 10px"
      />
      <template v-if="latest.analyses?.length">
        <h3 class="evaluation-section-title">误判原因分析</h3>
        <div class="analysis-list">
          <div v-for="item in latest.analyses" :key="item.id" class="analysis-card">
            <div class="analysis-title">
              <el-tag :type="item.error_type === 'false_negative' ? 'danger' : 'warning'">
                {{ item.error_type === 'false_negative' ? '漏检' : '误报' }} · {{ item.input_id }}
              </el-tag>
              <span
                >人工：{{ item.human_category || '正常' }}；模型：{{
                  item.predicted_category || '正常'
                }}</span
              >
            </div>
            <p><strong>判定原因：</strong>{{ item.reason }}</p>
            <p><strong>可能成因：</strong>{{ item.likely_cause }}</p>
            <p v-if="item.evidence_summary">
              <strong>证据分析：</strong>{{ item.evidence_summary }}
            </p>
          </div>
        </div>
      </template>
      <template v-if="latest.suggestions?.length">
        <div class="suggestion-plan-heading">
          <h3 class="evaluation-section-title">幻觉定义优化建议</h3>
          <div v-if="hasPendingSuggestionPlan" class="suggestion-actions">
            <el-button
              type="primary"
              size="small"
              :loading="suggestionPlanBusy"
              @click="decideSuggestionPlan('apply')"
              >采纳整套方案</el-button
            >
            <el-button
              size="small"
              :disabled="suggestionPlanBusy"
              @click="decideSuggestionPlan('reject')"
              >全部忽略</el-button
            >
          </div>
        </div>
        <el-alert
          type="info"
          :closable="false"
          title="以下建议是一套原子迁移方案，只能整套采纳或全部忽略。"
          style="margin-bottom: 12px"
        />
        <div class="analysis-list">
          <div v-for="suggestion in latest.suggestions" :key="suggestion.id" class="analysis-card">
            <div class="analysis-title">
              <strong>{{ suggestion.target_category_name }}</strong>
              <el-tag type="primary">{{ suggestionActionLabels[suggestion.action] }}</el-tag>
              <el-tag v-if="suggestion.status === 'applied'" type="success">已采纳</el-tag>
              <el-tag v-else-if="suggestion.status === 'rejected'" type="info">已忽略</el-tag>
              <el-tag v-else>待处理</el-tag>
            </div>
            <p>{{ suggestion.reason }}</p>
            <div
              v-for="([label, value], index) in categoryChangeEntries(suggestion.proposed_changes)"
              :key="index"
              class="change-row"
            >
              <strong>{{ label }}：</strong>{{ value }}
            </div>
          </div>
        </div>
        <el-alert
          type="info"
          :closable="false"
          title="采纳前的分类定义会自动保存为历史版本，可在幻觉定义管理中回退。"
          style="margin-top: 12px"
        />
      </template>
    </el-card>
    <el-card class="panel" shadow="never"
      ><template #header
        ><div style="display: flex; justify-content: space-between; align-items: center">
          <strong>逐条检测结果</strong>
          <div style="display: flex; gap: 8px">
            <el-upload
              ref="evaluationUpload"
              :auto-upload="false"
              :limit="1"
              accept=".json"
              :show-file-list="false"
              :disabled="!canEvaluateTask(task.status) || evaluating"
              :on-change="(f: any) => (evaluationFile = f.raw)"
              :on-exceed="handleEvaluationExceed"
              ><el-button :icon="Upload">{{
                evaluationFile ? '重新选择' : '选择人工标注'
              }}</el-button></el-upload
            ><span v-if="evaluationFile" class="selected-file-name" :title="evaluationFile.name">
              已选择：{{ evaluationFile.name }}
            </span>
            <el-button
              v-if="evaluationFile"
              link
              type="danger"
              :disabled="evaluating"
              @click="clearEvaluationFile"
              >清除</el-button
            >
            <el-button
              type="primary"
              :loading="evaluating"
              :disabled="!evaluationFile || !canEvaluateTask(task.status) || evaluating"
              @click="evaluate"
              >{{ evaluating ? '正在比较' : '开始比对' }}</el-button
            >
          </div>
        </div></template
      >
      <div v-if="evaluationStage" class="evaluation-progress">
        <div class="evaluation-progress-label">
          <strong>人工标注比较进度</strong>
          <span>{{ evaluationStage }}</span>
        </div>
        <el-progress
          :percentage="evaluationProgress"
          :status="evaluationProgressStatus || undefined"
          :indeterminate="evaluating && evaluationProgress >= 30"
          :duration="2"
        />
        <div v-if="evaluationEvents.length" class="evaluation-event-list">
          <div v-for="event in evaluationEvents" :key="event.sequence" class="evaluation-event">
            <span class="evaluation-event-dot" />
            <span>{{ event.stage }}</span>
            <small>{{ event.progress }}%</small>
          </div>
        </div>
      </div>
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
          activeItem.primary_category || '正常'
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
<style scoped>
.evaluation-section-title {
  margin: 22px 0 12px;
  font-size: 16px;
}
.analysis-list {
  display: grid;
  gap: 10px;
}
.analysis-card {
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #fafcff;
}
.analysis-card p {
  margin: 9px 0 0;
  line-height: 1.65;
}
.analysis-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.change-row {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff;
  line-height: 1.55;
  white-space: pre-wrap;
}
.suggestion-actions {
  display: flex;
  gap: 8px;
}
.suggestion-plan-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.evaluation-progress {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}
.evaluation-progress-label {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.evaluation-event-list {
  display: grid;
  gap: 7px;
  max-height: 190px;
  margin-top: 12px;
  padding-top: 10px;
  overflow-y: auto;
  border-top: 1px solid var(--el-border-color-lighter);
}
.evaluation-event {
  display: grid;
  grid-template-columns: 8px 1fr auto;
  gap: 8px;
  align-items: center;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.evaluation-event-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--el-color-primary);
}
.evaluation-event small {
  color: var(--el-text-color-secondary);
}
.selected-file-name {
  max-width: 220px;
  overflow: hidden;
  color: var(--el-text-color-regular);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
