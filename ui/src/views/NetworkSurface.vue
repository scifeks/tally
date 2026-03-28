<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  ColDef,
  CellValueChangedEvent,
  ValueGetterParams,
} from 'ag-grid-community'
import { myTheme } from '../ag-grid-theme.js'
import { getConfig, getFindings, patchFinding } from '../api'
import type { FieldSpec, Finding, FindingPatch } from '../api'

const rowData = reactive<Finding[]>([])
const columnDefs = ref<ColDef<Finding>[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const defaultColDef: ColDef<Finding> = {
  resizable: true,
  sortable: true,
  filter: true,
  valueFormatter: (params) => (params.value == null ? '' : String(params.value)),
}

/** Apply server-supplied field spec to a base column definition. */
function applySpec(base: ColDef<Finding>, spec: FieldSpec | undefined): ColDef<Finding> {
  if (!spec) return { ...base, editable: false }
  const out: ColDef<Finding> = { ...base, editable: true }
  if (spec.editor === 'select' && spec.options) {
    out.cellEditor = 'agSelectCellEditor'
    out.cellEditorParams = { values: spec.options }
  } else if (spec.editor === 'boolean') {
    out.cellRenderer = 'agCheckboxCellRenderer'
    out.cellEditor = 'agCheckboxCellEditor'
  }
  return out
}

function buildColumnDefs(fields: Record<string, FieldSpec>): ColDef<Finding>[] {
  const e = (key: string) => fields[key]
  return [
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
    applySpec({ headerName: 'Severity', field: 'severity', width: 120 }, e('severity')),
    {
      headerName: 'TLS',
      colId: 'meta_tls_version',
      editable: false,
      valueGetter: (params: ValueGetterParams<Finding>) =>
        (params.data?.meta?.tls_version as string | undefined) ?? '',
      width: 120,
    },
    applySpec({ headerName: 'Notes', field: 'description', flex: 1, minWidth: 200 }, e('description')),
  ]
}

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
    // Revert in-memory data directly — setDataValue would re-fire cellValueChanged
    // and bypass any guard because onCellValueChanged is async.
    const field = event.colDef.field
    if (field) (event.data as unknown as Record<string, unknown>)[field] = event.oldValue
    event.api.refreshCells({ rowNodes: [event.node!], force: true })
  }
}

onMounted(async () => {
  try {
    const [config, findings] = await Promise.all([
      getConfig(),
      getFindings({ tool: 'nmap' }),
    ])
    columnDefs.value = buildColumnDefs(config.editable_fields)
    rowData.push(...findings)
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
