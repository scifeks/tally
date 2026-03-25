<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  ColDef,
  CellValueChangedEvent,
  ValueGetterParams,
} from 'ag-grid-community'
import { myTheme } from '../ag-grid-theme.js'
import { getFindings, patchFinding } from '../api'
import type { Finding, FindingPatch } from '../api'

const rowData = reactive<Finding[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const defaultColDef: ColDef<Finding> = {
  resizable: true,
  sortable: true,
  filter: true,
  valueFormatter: (params) => (params.value == null ? '' : String(params.value)),
}

const columnDefs: ColDef<Finding>[] = [
  { headerName: 'ID', field: 'id', editable: false, width: 80 },
  { headerName: 'Host', field: 'host', editable: false, width: 140 },
  {
    headerName: 'Hostname',
    colId: 'meta_hostname',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.hostname as string | undefined) ?? '',
    width: 180,
  },
  { headerName: 'Port', field: 'port', editable: false, width: 80 },
  {
    headerName: 'Service',
    colId: 'meta_service',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.service as string | undefined) ?? '',
    width: 120,
  },
  {
    headerName: 'Version',
    colId: 'meta_service_version',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.service_version as string | undefined) ?? '',
    width: 160,
  },
  {
    headerName: 'Transport',
    colId: 'meta_transport',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.transport as string | undefined) ?? '',
    width: 100,
  },
  {
    headerName: 'State',
    colId: 'meta_state',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.state as string | undefined) ?? '',
    width: 100,
  },
  {
    headerName: 'Severity',
    field: 'severity',
    editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: { values: ['critical', 'high', 'medium', 'low', 'informational'] },
    width: 120,
  },
  {
    headerName: 'TLS',
    colId: 'meta_tls_version',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.tls_version as string | undefined) ?? '',
    width: 120,
  },
  { headerName: 'Notes', field: 'description', editable: true, flex: 1, minWidth: 200 },
]

async function onCellValueChanged(event: CellValueChangedEvent<Finding>) {
  const id = event.data.id
  const colId = event.colDef.colId ?? event.colDef.field ?? ''
  const patch: FindingPatch = {}

  if (colId === 'severity') patch.severity = event.newValue as string
  else if (colId === 'description') patch.description = event.newValue as string
  else return

  try {
    const updated = await patchFinding(id, patch)
    Object.assign(event.data, updated)
    event.api.refreshCells({ rowNodes: [event.node!], force: true })
  } catch {
    const key = event.colDef.colId ?? event.colDef.field
    if (key) event.node?.setDataValue(key, event.oldValue)
  }
}

onMounted(async () => {
  try {
    rowData.push(...(await getFindings({ tool: 'nmap' })))
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Failed to load network findings'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div style="height: calc(100vh - 50px); width: 100%;">
    <div v-if="loading" style="padding: 16px; font-family: monospace;">Loading…</div>
    <div v-else-if="loadError" style="padding: 16px; color: #ff4444; font-family: monospace;">
      {{ loadError }}
    </div>
    <AgGridVue
      v-else
      style="height: 100%; width: 100%;"
      :column-defs="columnDefs"
      :row-data="rowData"
      :default-col-def="defaultColDef"
      :theme="myTheme"
      @cell-value-changed="onCellValueChanged"
    />
  </div>
</template>
