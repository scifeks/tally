<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  ColDef,
  CellValueChangedEvent,
  ValueGetterParams,
  ValueSetterParams,
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
  { headerName: 'Tool', field: 'tool', editable: false, width: 100 },
  {
    headerName: 'Severity',
    field: 'severity',
    editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: { values: ['critical', 'high', 'medium', 'low', 'informational'] },
    width: 120,
  },
  {
    headerName: 'Confidence',
    field: 'confidence',
    editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: { values: ['confirmed', 'probable', 'potential'] },
    width: 130,
  },
  {
    headerName: 'Type',
    colId: 'finding_type',
    editable: true,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      params.data?.finding_type?.join(', ') ?? '',
    valueSetter: (params: ValueSetterParams<Finding>) => {
      params.data.finding_type = (params.newValue as string)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      return true
    },
    width: 150,
  },
  { headerName: 'File', field: 'file', editable: false, width: 220 },
  {
    headerName: 'Rule / Alert',
    colId: 'rule_alert',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      params.data?.rule_id ||
      (params.data?.meta?.alert_name as string | undefined) ||
      '',
    width: 160,
  },
  { headerName: 'Description', field: 'description', editable: true, flex: 1, minWidth: 200 },
  { headerName: 'URL', field: 'url', editable: false, width: 220 },
  {
    headerName: 'Status',
    field: 'status',
    editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: { values: ['active', 'false_positive', 'fixed', 'wont_fix'] },
    width: 140,
  },
  {
    headerName: 'Report?',
    colId: 'should_report',
    editable: true,
    cellRenderer: 'agCheckboxCellRenderer',
    cellEditor: 'agCheckboxCellEditor',
    valueGetter: (params: ValueGetterParams<Finding>) => Boolean(params.data?.should_report),
    valueSetter: (params: ValueSetterParams<Finding>) => {
      params.data.should_report = params.newValue ? 1 : 0
      return true
    },
    width: 90,
  },
  {
    headerName: 'Title',
    colId: 'meta_title',
    editable: true,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.title as string | undefined) ?? '',
    valueSetter: (params: ValueSetterParams<Finding>) => {
      params.data.meta.title = params.newValue as string
      return true
    },
    width: 200,
  },
  {
    headerName: 'Remediation',
    colId: 'meta_remediation',
    editable: true,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      (params.data?.meta?.remediation as string | undefined) ?? '',
    valueSetter: (params: ValueSetterParams<Finding>) => {
      params.data.meta.remediation = params.newValue as string
      return true
    },
    width: 250,
  },
  {
    headerName: 'CWE',
    colId: 'cwe',
    editable: false,
    valueGetter: (params: ValueGetterParams<Finding>) =>
      params.data?.cwe?.join(', ') ?? '',
    width: 120,
  },
]

async function onCellValueChanged(event: CellValueChangedEvent<Finding>) {
  const id = event.data.id
  const colId = event.colDef.colId ?? event.colDef.field ?? ''
  const patch: FindingPatch = {}

  if (colId === 'severity') patch.severity = event.newValue as string
  else if (colId === 'confidence') patch.confidence = event.newValue as string
  else if (colId === 'finding_type') patch.finding_type = event.data.finding_type
  else if (colId === 'description') patch.description = event.newValue as string
  else if (colId === 'status') patch.status = event.newValue as string
  else if (colId === 'should_report') patch.should_report = Boolean(event.newValue)
  else if (colId === 'meta_title') patch.meta_title = event.newValue as string
  else if (colId === 'meta_remediation') patch.meta_remediation = event.newValue as string
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
    const [codeFindings, webFindings] = await Promise.all([
      getFindings({ domain: 'code' }),
      getFindings({ domain: 'web' }),
    ])
    rowData.push(...codeFindings, ...webFindings)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Failed to load findings'
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
