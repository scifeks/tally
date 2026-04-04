<script setup lang="ts">
import { ref } from 'vue'
import { initToken } from './api'
import FindingsTable from './views/FindingsTable.vue'

// initToken() runs synchronously at setup time so the token is stored in
// authStore before any child component mounts and makes API calls.
const tokenOk = initToken()
const error = ref<string | null>(
  tokenOk
    ? null
    : 'No authentication token found. Please launch the UI via the `findings visualize` command.'
)
</script>

<template>
  <div
    v-if="error"
    style="display: flex; justify-content: center; align-items: center; height: 100vh; font-family: monospace; padding: 24px; text-align: center;"
  >
    {{ error }}
  </div>
  <div v-else>
    <FindingsTable />
  </div>
</template>
