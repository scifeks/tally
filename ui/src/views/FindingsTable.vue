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
    { headerName: 'Tool', field: 'tool', editable: false, width: 100 },
    applySpec({ headerName: 'Severity', field: 'severity', width: 120 }, e('severity')),
    applySpec({ headerName: 'Confidence', field: 'confidence', width: 130 }, e('confidence')),
    applySpec(
      {
        headerName: 'Type',
        colId: 'finding_type',
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
      e('finding_type'),
    ),
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
    applySpec({ headerName: 'Description', field: 'description', flex: 1, minWidth: 200 }, e('description')),
    { headerName: 'URL', field: 'url', editable: false, width: 220 },
    applySpec({ headerName: 'Status', field: 'status', width: 140 }, e('status')),
    applySpec(
      {
        headerName: 'Report?',
        colId: 'should_report',
        valueGetter: (params: ValueGetterParams<Finding>) => Boolean(params.data?.should_report),
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.should_report = params.newValue ? 1 : 0
          return true
        },
        width: 90,
      },
      e('should_report'),
    ),
    applySpec(
      {
        headerName: 'Title',
        colId: 'meta_title',
        valueGetter: (params: ValueGetterParams<Finding>) =>
          (params.data?.meta?.title as string | undefined) ?? '',
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.meta.title = params.newValue as string
          return true
        },
        width: 200,
      },
      e('meta_title'),
    ),
    applySpec(
      {
        headerName: 'Remediation',
        colId: 'meta_remediation',
        valueGetter: (params: ValueGetterParams<Finding>) =>
          (params.data?.meta?.remediation as string | undefined) ?? '',
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.meta.remediation = params.newValue as string
          return true
        },
        width: 250,
      },
      e('meta_remediation'),
    ),
    {
      headerName: 'CWE',
      colId: 'cwe',
      editable: false,
      valueGetter: (params: ValueGetterParams<Finding>) =>
        params.data?.cwe?.join(', ') ?? '',
      width: 120,
    },
  ]
}

let _reverting = false

async function onCellValueChanged(event: CellValueChangedEvent<Finding>) {

  if (_reverting) return
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
    _reverting = true
    try {
      const key = event.colDef.colId ?? event.colDef.field
      if (key) event.node?.setDataValue(key, event.oldValue)
    } finally {
      _reverting = false
    }
  }
}

onMounted(async () => {
  try {
    const [config, codeFindings, webFindings] = await Promise.all([
      getConfig(),
      getFindings({ domain: 'code' }),
      getFindings({ domain: 'web' }),
    ])
    columnDefs.value = buildColumnDefs(config.editable_fields)
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
