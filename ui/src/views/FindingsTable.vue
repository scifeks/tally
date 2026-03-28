<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  ColDef,
  CellValueChangedEvent,
  GridReadyEvent,
  GridApi,
  ICellRendererParams,
  IRowNode,
  ValueGetterParams,
  ValueSetterParams,
} from 'ag-grid-community'
import { myTheme } from '../ag-grid-theme.js'
import { getConfig, getFindings, patchFinding, batchPatchFindings } from '../api'
import type { FieldSpec, Finding, FindingPatch } from '../api'
import PillToggle from '../components/PillToggle.vue'

const rowData = reactive<Finding[]>([])
const columnDefs = ref<ColDef<Finding>[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const selectedCount = ref(0)
const batchLoading = ref(false)
const batchError = ref<string | null>(null)
const gridComponents = { PillToggle }

let gridApi: GridApi<Finding> | null = null

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
    {
      checkboxSelection: true,
      headerCheckboxSelection: true,
      width: 50,
      pinned: 'left' as const,
      editable: false,
      sortable: false,
      filter: false,
      resizable: false,
      suppressKeyboardEvent: () => true,
    },
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
    {
      headerName: 'Approve?',
      colId: 'should_report',
      width: 130,
      editable: false,
      suppressKeyboardEvent: () => true,
      cellRenderer: 'PillToggle',
      cellRendererParams: (params: ICellRendererParams<Finding>) => ({
        activeLabel: '✓ Approved',
        inactiveLabel: 'Approve',
        activeColor: '#22c55e',
        inactiveColor: '#ef4444',
        onToggle: async (newValue: boolean) => {
          const updated = await patchFinding(params.data!.id, { should_report: newValue })
          Object.assign(params.data!, updated)
          params.api.refreshCells({ rowNodes: [params.node!], force: true })
        },
      }),
      valueGetter: (params: ValueGetterParams<Finding>) =>
        Boolean(params.data?.should_report),
    },
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

async function onCellValueChanged(event: CellValueChangedEvent<Finding>) {
  const id = event.data.id
  const colId = event.colDef.colId ?? event.colDef.field ?? ''
  const patch: FindingPatch = {}

  if (colId === 'severity') patch.severity = event.newValue as string
  else if (colId === 'confidence') patch.confidence = event.newValue as string
  else if (colId === 'finding_type') patch.finding_type = event.data.finding_type
  else if (colId === 'description') patch.description = event.newValue as string
  else if (colId === 'status') patch.status = event.newValue as string
  else if (colId === 'meta_title') patch.meta_title = event.newValue as string
  else if (colId === 'meta_remediation') patch.meta_remediation = event.newValue as string
  else return

  try {
    const updated = await patchFinding(id, patch)
    Object.assign(event.data, updated)
    event.api.refreshCells({ rowNodes: [event.node!], force: true })
  } catch {
    // Revert in-memory data directly — setDataValue would re-fire cellValueChanged
    // and bypass any guard because onCellValueChanged is async.
    if (colId === 'finding_type') {
      event.data.finding_type = typeof event.oldValue === 'string'
        ? event.oldValue.split(',').map((s) => s.trim()).filter(Boolean)
        : []
    } else if (colId === 'meta_title') {
      event.data.meta.title = event.oldValue as string
    } else if (colId === 'meta_remediation') {
      event.data.meta.remediation = event.oldValue as string
    } else {
      const field = event.colDef.field
      if (field) (event.data as unknown as Record<string, unknown>)[field] = event.oldValue
    }
    event.api.refreshCells({ rowNodes: [event.node!], force: true })
  }
}

function onGridReady(event: GridReadyEvent<Finding>) {
  gridApi = event.api
  event.api.addEventListener('selectionChanged', () => {
    selectedCount.value = event.api.getSelectedRows().length
  })
}

async function approveSelected() {
  if (!gridApi || batchLoading.value) return
  const selectedNodes: IRowNode<Finding>[] = []
  gridApi.forEachNode((node) => {
    if (node.isSelected()) selectedNodes.push(node)
  })
  const ids = selectedNodes.map((n) => n.data!.id)
  if (!ids.length) return

  batchLoading.value = true
  batchError.value = null
  try {
    await batchPatchFindings({ ids, should_report: true })
    selectedNodes.forEach((node) => {
      if (node.data) node.data.should_report = 1
    })
    gridApi.refreshCells({ rowNodes: selectedNodes, columns: ['should_report'], force: true })
    gridApi.deselectAll()
    selectedCount.value = 0
  } catch {
    batchError.value = 'Batch approve failed — please try again.'
    setTimeout(() => {
      batchError.value = null
    }, 4000)
  } finally {
    batchLoading.value = false
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
  <div style="height: calc(100vh - 50px); width: 100%; display: flex; flex-direction: column;">
    <div v-if="loading" style="padding: 16px; font-family: monospace;">Loading…</div>
    <div v-else-if="loadError" style="padding: 16px; color: #ff4444; font-family: monospace;">
      {{ loadError }}
    </div>
    <template v-else>
      <div
        style="
          padding: 6px 12px;
          background: #21222C;
          border-bottom: 1px solid #429356;
          display: flex;
          align-items: center;
          gap: 10px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
        "
      >
        <button
          :disabled="selectedCount === 0 || batchLoading"
          :style="{
            padding: '4px 14px',
            background: selectedCount > 0 && !batchLoading ? '#429356' : '#2a2a3a',
            color: selectedCount > 0 && !batchLoading ? '#ffffff' : '#555',
            border: 'none',
            borderRadius: '4px',
            fontFamily: 'inherit',
            fontSize: '12px',
            cursor: selectedCount > 0 && !batchLoading ? 'pointer' : 'not-allowed',
          }"
          @click="approveSelected"
        >
          Approve Selected ({{ selectedCount }})
        </button>
        <span v-if="batchError" style="color: #ef4444;">{{ batchError }}</span>
      </div>
      <AgGridVue
        style="flex: 1; width: 100%;"
        :column-defs="columnDefs"
        :row-data="rowData"
        :default-col-def="defaultColDef"
        :theme="myTheme"
        :components="gridComponents"
        row-selection="multiple"
        @cell-value-changed="onCellValueChanged"
        @grid-ready="onGridReady"
      />
    </template>
  </div>
</template>
