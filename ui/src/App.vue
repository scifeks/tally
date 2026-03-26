<script setup lang="ts">
import { ref } from 'vue'
import { initToken } from './api'
import FindingsTable from './views/FindingsTable.vue'
import NetworkSurface from './views/NetworkSurface.vue'

// initToken() runs synchronously at setup time so the token is stored in
// authStore before any child component mounts and makes API calls.
const tokenOk = initToken()
const error = ref<string | null>(
  tokenOk
    ? null
    : 'No authentication token found. Please launch the UI via the `findings visualize` command.'
)
const activeTab = ref<'findings' | 'network'>('findings')
</script>

<template>
  <div
    v-if="error"
    style="display: flex; justify-content: center; align-items: center; height: 100vh; font-family: monospace; padding: 24px; text-align: center;"
  >
    {{ error }}
  </div>
  <div v-else>
    <nav style="padding: 8px 12px; border-bottom: 1px solid #429356; background: #21222C;">
      <button
        @click="activeTab = 'findings'"
        :style="{ fontWeight: activeTab === 'findings' ? 'bold' : 'normal', marginRight: '8px' }"
      >
        Code &amp; Web Findings
      </button>
      <button
        @click="activeTab = 'network'"
        :style="{ fontWeight: activeTab === 'network' ? 'bold' : 'normal' }"
      >
        Network Surface
      </button>
    </nav>
    <FindingsTable v-if="activeTab === 'findings'" />
    <NetworkSurface v-else />
  </div>
</template>
