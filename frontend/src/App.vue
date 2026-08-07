<script setup lang="ts">
import { ref } from 'vue'

const ready = ref(true)
</script>

<template>
  <main class="shell">
    <h1>GroundLens</h1>
    <p>智能客服幻觉检测平台</p>
    <el-alert v-if="ready" title="前端基础设施已就绪" type="success" :closable="false" />
  </main>
</template>
