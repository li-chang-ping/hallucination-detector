<script setup lang="ts">
import { DataAnalysis, Files, List, MagicStick } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/tasks')) return '/tasks'
  return route.path
})
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="sidebar">
      <div class="brand">
        <div class="brand-mark"><MagicStick /></div>
        <div><strong>客服回复幻觉检测</strong></div>
      </div>
      <el-menu :default-active="activeMenu" router class="nav-menu">
        <el-menu-item index="/tasks"
          ><el-icon><DataAnalysis /></el-icon><span>检测任务</span></el-menu-item
        >
        <el-menu-item index="/knowledge"
          ><el-icon><Files /></el-icon><span>知识库管理</span></el-menu-item
        >
        <el-menu-item index="/categories"
          ><el-icon><List /></el-icon><span>幻觉定义管理</span></el-menu-item
        >
      </el-menu>
      <div class="sidebar-note"><span class="online-dot" />本地服务模式</div>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <div>
          <span class="crumb">工作台</span><strong>{{ route.meta.title }}</strong>
        </div>
        <el-tag type="success" effect="plain">DeepSeek V4 Flash</el-tag>
      </el-header>
      <el-main class="main-content"><router-view /></el-main>
    </el-container>
  </el-container>
</template>
