import { createRouter, createWebHistory } from 'vue-router'
import CategoriesView from './views/CategoriesView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import TaskDetailView from './views/TaskDetailView.vue'
import TasksView from './views/TasksView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/tasks' },
    { path: '/tasks', component: TasksView, meta: { title: '检测任务' } },
    { path: '/tasks/:id', component: TaskDetailView, meta: { title: '任务详情' } },
    { path: '/knowledge', component: KnowledgeView, meta: { title: '知识库管理' } },
    { path: '/categories', component: CategoriesView, meta: { title: '幻觉定义管理' } },
  ],
})
