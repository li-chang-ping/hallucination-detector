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
  knowledge_base_id: string
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
  created_at: string
}

export interface CategoryMismatch {
  id: string
  expected_category: string
  predicted_primary_category: string | null
  predicted_categories: string[]
}
