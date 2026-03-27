<script setup lang="ts">
import { ref } from 'vue'

interface PillParams {
  value: boolean
  activeLabel: string
  inactiveLabel: string
  activeColor: string
  inactiveColor: string
  onToggle: (newValue: boolean) => Promise<void>
}

const props = defineProps<{ params: PillParams }>()

const loading = ref(false)

async function handleClick() {
  if (loading.value) return
  loading.value = true
  try {
    await props.params.onToggle(!props.params.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <button
    class="pill-toggle"
    :style="{
      backgroundColor: params.value ? params.activeColor : 'transparent',
      borderColor: params.value ? params.activeColor : params.inactiveColor,
      color: params.value ? '#ffffff' : params.inactiveColor,
      opacity: loading ? 0.55 : 1,
      cursor: loading ? 'wait' : 'pointer',
    }"
    :disabled="loading"
    @click.stop="handleClick"
  >
    {{ params.value ? params.activeLabel : params.inactiveLabel }}
  </button>
</template>

<style scoped>
.pill-toggle {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 9999px;
  border-width: 1.5px;
  border-style: solid;
  font-size: 11px;
  font-weight: 600;
  font-family: inherit;
  line-height: 18px;
  transition: opacity 0.15s ease, background-color 0.15s ease;
  white-space: nowrap;
}
.pill-toggle:hover:not(:disabled) {
  opacity: 0.8;
}
</style>
