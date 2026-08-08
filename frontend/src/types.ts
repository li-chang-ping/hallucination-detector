export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type TaskStatus =
  'preparing' | 'queued' | 'running' | 'paused' | 'completed' | 'partial' | 'failed' | 'cancelled'

export interface Category {
  id: string
  name: string
  description: string
  default_severity: Severity
  prompt_guidance: string
  is_active: boolean
  is_archived: boolean
  created_at?: string
  updated_at?: string
}

export interface CategoryVersion {
  id: string
  category_id: string
  snapshot: Record<string, any>
  source: string
  note: string
  created_at: string
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  embedding_model: string
  entry_count: number
  created_at: string
}

export interface KnowledgeEntry {
  id: string
  external_id: string
  knowledge_base_id: string
  title: string
  content: string
  extra_metadata: Record<string, unknown>
}

export interface DetectionItem {
  id: string
  input_id: string
  position: number
  user_question: string
  system_reply: string
  status: string
  evidence_snapshot: Array<Record<string, any>>
  error_message: string | null
  is_hallucination: boolean | null
  category_names: string[]
  primary_category: string | null
  severity: Severity | null
  confidence: number | null
  rationale: string | null
  prompt_tokens: number
  completion_tokens: number
}

export interface DetectionTask {
  id: string
  name: string
  knowledge_base_id: string | null
  status: TaskStatus
  model_name: string
  total_count: number
  completed_count: number
  error_count: number
  created_at: string
  updated_at: string
  items?: DetectionItem[]
}

export interface Evaluation {
  id: string
  task_id: string
  metrics: Record<string, any>
  ground_truth_count: number
  insight_status: 'pending' | 'running' | 'completed' | 'fallback' | 'unknown'
  insight_error: string | null
  insight_progress: number
  insight_stage: string
  insight_events: EvaluationProgressEvent[]
  optimization_context: EvaluationOptimizationContext
  created_at: string
  analyses: EvaluationAnalysis[]
  suggestions: CategorySuggestion[]
}

export interface EvaluationOptimizationContext {
  history_round_count?: number
  target_taxonomy_names?: string[]
  evaluation_history?: Array<Record<string, unknown>>
  recurring_mismatches?: Array<{
    expected_category: string
    predicted_category: string
    round_count: number
    case_ids: string[]
  }>
  regression_cases?: Array<{
    input_id: string
    previous_prediction: string
    current_prediction: string
    expected_category: string
  }>
  category_conflicts?: Array<Record<string, string>>
}

export interface EvaluationProgressEvent {
  sequence: number
  stage: string
  progress: number
  status: string
  created_at: string
}

export interface EvaluationAnalysis {
  id: string
  input_id: string
  error_type: 'false_negative' | 'false_positive'
  human_category: string | null
  predicted_category: string | null
  reason: string
  likely_cause: string
  evidence_summary: string
}

export interface CategorySuggestion {
  id: string
  category_id: string | null
  action: 'create' | 'update' | 'archive'
  target_category_name: string
  reason: string
  proposed_changes: Partial<
    Pick<Category, 'name' | 'description' | 'prompt_guidance' | 'default_severity'>
  >
  impact_analysis: {
    resolved_mismatch_pairs?: Array<Record<string, string>>
    resolved_case_ids?: string[]
    historical_evidence?: Record<string, unknown>
    regression_risk?: 'low' | 'medium' | 'high'
    regression_risk_reason?: string
  }
  status: 'pending' | 'applied' | 'rejected'
  created_at: string
  decided_at: string | null
}

export interface CategoryMismatch {
  id: string
  expected_category: string
  predicted_category: string | null
}
