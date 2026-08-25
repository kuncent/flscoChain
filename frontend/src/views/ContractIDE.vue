<template>
  <div class="ide dq-enter-up">
    <!-- 工程与文件树 -->
    <div class="side dq-card">
      <div class="dq-card-title">
        工程
        <el-button size="small" @click="newProject" style="margin-left:auto">新建</el-button>
      </div>
      <el-select v-model="curPid" placeholder="选择工程" size="small" @change="loadFiles" style="width:100%;margin-bottom:10px">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>

      <div class="file-ops">
        <el-input v-model="newPath" size="small" placeholder="新文件名 e.g. MyToken.sol" @keyup.enter="createFile" />
        <el-button size="small" @click="createFile">+</el-button>
      </div>

      <div class="file-tree">
        <div
          v-for="f in files"
          :key="f.id"
          class="file-item"
          :class="{ active: f.id === curFid }"
          @click="openFile(f)"
        >
          <el-icon><Document /></el-icon>
          <span class="dq-mono">{{ f.path }}</span>
          <el-icon class="del" @click.stop="delFile(f.id)"><Delete /></el-icon>
        </div>
        <EmptyIllustration
          v-if="!files.length"
          type="contract"
          :hide-text="true"
          style="margin-top:6px; padding: 10px 4px;"
        />
        <div v-if="!files.length" class="ft-empty-text">暂无工程文件，点击上方「新建」或选择下方内置协议模板</div>
      </div>

      <div class="builtin">
        <div class="dq-card-title" style="font-size:13px">内置协议</div>
        <div class="proto" v-for="b in builtin" :key="b.name" @click="loadBuiltin(b)">
          <span class="dq-tag">{{ b.name }}</span>
          <span class="proto-file">{{ b.file }}</span>
        </div>
      </div>
    </div>

    <!-- 编辑器 -->
    <div class="editor-area dq-card">
      <div class="editor-toolbar">
        <span class="cur-file dq-mono">{{ curFile?.path || '未打开文件' }}</span>
        <div class="ops">
          <el-button size="small" @click="save" :disabled="!curFid">保存</el-button>
          <el-button size="small" type="primary" @click="compile" :disabled="!curFile">编译</el-button>
          <el-button size="small" type="warning" @click="audit" :disabled="!curFile">安全审计</el-button>
          <el-button size="small" type="success" @click="deploy" :disabled="!curFile">部署</el-button>
        </div>
      </div>

      <!-- Monaco 占位：切 tab 瞬时显示 UI，后台再异步加载 10MB+ Monaco -->
      <div class="monaco-wrap">
        <div v-if="!editorReady" class="monaco-skeleton">
          <div class="sk-spinner"></div>
          <div class="sk-text">
            <div class="sk-t1">Monaco 编辑器加载中…</div>
            <div class="sk-t2 dq-mono">首次进入需加载 ~12MB 语法高亮模块，不影响其它页面。加载完成后切换 tab 瞬时响应。</div>
          </div>
        </div>
        <div class="monaco" ref="monacoRef" :style="{ opacity: editorReady ? 1 : 0, pointerEvents: editorReady ? 'auto' : 'none' }"></div>
      </div>

      <!-- 错误输出 -->
      <div class="output">
        <div class="out-tabs">
          <span class="tab" :class="{ active: tab === 'errors' }" @click="tab = 'errors'">编译/运行错误</span>
          <span class="tab" :class="{ active: tab === 'result' }" @click="tab = 'result'">部署结果</span>
          <span class="tab" :class="{ active: tab === 'abi' }" @click="tab = 'abi'" v-if="abiFunctions.length">ABI 接口 ({{ abiFunctions.length }})</span>
          <span class="tab" :class="{ active: tab === 'audit' }" @click="tab = 'audit'">安全审计 ({{ auditResult?.issues_count ?? 0 }})</span>
        </div>
        <!-- 错误 -->
        <div class="out-body" v-if="tab === 'errors'">
          <div v-if="!errors.length" class="ok-line">✓ 编译无错误</div>
          <div v-else class="err-list">
            <div class="err-item" v-for="(e, i) in errors" :key="i">
              <span class="err-tag">ERR</span><span class="dq-mono">{{ e }}</span>
            </div>
          </div>
        </div>
        <!-- 部署结果 -->
        <div class="out-body" v-else-if="tab === 'result'">
          <template v-if="result">
            <div class="res-row" v-for="(v, k) in result" :key="k">
              <span class="res-k">{{ k }}</span>
              <span class="res-v dq-mono" :class="{ link: String(k) === '合约地址' }" @click="String(k) === '合约地址' && goInterfaces(result['合约地址'])">{{ v }}</span>
            </div>
            <div class="dq-tip" style="margin-top:10px">
              <span class="dt-label">下一步:</span>合约已部署到真实链，前往「接口调试」自动生成接口并在线调用，或在「区块链浏览器」查看交易。
            </div>
            <div class="res-ops" v-if="result['合约地址']">
              <el-button size="small" type="primary" @click="goInterfaces(result['合约地址'])">前往接口调试</el-button>
              <el-button size="small" @click="goExplorer(result['合约地址'])">在浏览器查看</el-button>
            </div>
          </template>
          <div v-else class="placeholder-out">（执行编译/部署后输出在此）</div>
        </div>
        <!-- ABI 接口 -->
        <div class="out-body" v-else-if="tab === 'abi'">
          <div class="abi-tip">部署后，这些函数将自动在「接口调试」页生成可调用表单。view/pure 为只读，其余为状态变更（消耗 Gas、产生事件）。</div>
          <div class="abi-fn" v-for="fn in abiFunctions" :key="fn.signature">
            <span class="fn-name dq-mono">{{ fn.name }}</span>
            <span class="fn-args dq-mono">({{ fn.inputs }})</span>
            <span class="dq-tag" :class="fn.mutability === 'view' || fn.mutability === 'pure' ? '' : 'warn'">{{ fn.mutability }}</span>
            <span class="fn-ret dq-mono" v-if="fn.outputs">→ {{ fn.outputs }}</span>
          </div>
        </div>
        <!-- 安全审计 -->
        <div class="out-body" v-else-if="tab === 'audit'">
          <div v-if="auditResult" class="audit-container">
            <div class="audit-score" :class="scoreClass">
              <span class="score-num">{{ auditResult.score }}</span>
              <span class="score-label">安全评分</span>
            </div>
            <div class="audit-summary">
              <div class="summary-item">
                <span class="summary-label">问题总数</span>
                <span class="summary-value">{{ auditResult.issues_count }}</span>
              </div>
              <div class="summary-item severity-high">
                <span class="summary-label">高危</span>
                <span class="summary-value">{{ auditResult.high }}</span>
              </div>
              <div class="summary-item severity-medium">
                <span class="summary-label">中危</span>
                <span class="summary-value">{{ auditResult.medium }}</span>
              </div>
              <div class="summary-item severity-low">
                <span class="summary-label">低危</span>
                <span class="summary-value">{{ auditResult.low }}</span>
              </div>
            </div>
            <div class="audit-issues" v-if="auditResult.issues?.length">
              <div class="audit-item" v-for="(issue, idx) in auditResult.issues" :key="idx" :class="'severity-' + issue.severity">
                <div class="issue-header">
                  <span class="severity-tag">{{ issue.severity.toUpperCase() }}</span>
                  <span class="issue-type dq-mono">{{ issue.type }}</span>
                  <span class="issue-line dq-mono" v-if="issue.line">行 {{ issue.line }}</span>
                </div>
                <div class="issue-message">{{ issue.message }}</div>
                <div class="issue-suggestion" v-if="issue.suggestion">
                  <span class="suggestion-label">建议：</span>{{ issue.suggestion }}
                </div>
              </div>
            </div>
            <div v-else class="audit-empty">未发现安全问题</div>
          </div>
          <div v-else class="audit-empty">点击「安全审计」按钮开始检测</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, onBeforeUnmount, nextTick, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
/* ⚡ 关键优化：Monaco 改为动态 import()
 * - 顶层不加载 10MB+ Monaco，切 tab 主线程不被阻塞
 * - 页面先显示骨架，UI 瞬时响应（dq-fade 过渡正常播放）
 * - 200ms 后后台异步加载 Monaco，用户感觉不到"整页刷新"
 * - keep-alive 缓存后再次进入瞬间打开
 */
import { ideApi, contractApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '@/stores/app'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

type MonacoModule = typeof import('monaco-editor')

const router = useRouter()
const app = useAppStore()
const projects = ref<any[]>([])
const curPid = ref('')
const files = ref<any[]>([])
const curFid = ref('')
const curFile = ref<any>(null)
const newPath = ref('')
const builtin = ref<any[]>([])
const errors = ref<string[]>([])
const result = ref<any>(null)
const tab = ref<'errors' | 'result' | 'abi' | 'audit'>('errors')
const auditResult = ref<any>(null)
const lastAbi = ref<any[]>([])
const editorReady = ref(false)
// shallowRef 避免 Vue 对 Monaco 大对象做响应式 Proxy，节省 100ms+
const monacoMod = shallowRef<MonacoModule | null>(null)
const monacoRef = ref<HTMLElement>()
// 编辑器实例用模块作用域变量，不进入 Vue 响应式系统
let editor: any = null

// 从 ABI 提取可读函数列表
const abiFunctions = computed(() => {
  return lastAbi.value
    .filter((x: any) => x.type === 'function')
    .map((x: any) => ({
      name: x.name,
      inputs: (x.inputs || []).map((i: any) => `${i.type} ${i.name}`).join(', '),
      outputs: (x.outputs || []).map((o: any) => o.type).join(','),
      mutability: x.stateMutability || (x.constant ? 'view' : 'nonpayable'),
      signature: x.name + (x.inputs || []).map((i: any) => i.type).join(','),
    }))
})

function goInterfaces(addr: string) {
  router.push('/interfaces?addr=' + addr)
  ElMessage.success(`已跳转接口调试，合约 ${addr.slice(0, 10)}... 已就绪`)
}
function goExplorer(addr: string) {
  router.push('/explorer/address/' + addr)
}

async function loadProjects() {
  projects.value = (await ideApi.projects()) as any
  if (!curPid.value && projects.value.length) {
    curPid.value = projects.value[0].id
    await loadFiles()
  }
}

/* 工程命名规范：中文/字母/数字/下划线/中划线，≤30 字符（与后端一致） */
const PROJECT_NAME_RE = /^[\w\u4e00-\u9fa5\- ]{1,30}$/
function validateProjectName(v: string): boolean {
  if (!v || !v.trim()) { return false }
  if (!PROJECT_NAME_RE.test(v.trim())) { return false }
  return true
}

async function newProject() {
  const { value } = await ElMessageBox.prompt(
    '工程名称（中文 / 字母 / 数字 / 下划线 / 中划线，≤30 字符）',
    '新建工程',
    {
      inputPattern: PROJECT_NAME_RE,
      inputErrorMessage: '命名不规范：仅支持中文、字母、数字、下划线、中划线，长度 1-30 字符',
      inputValidator: (v: string) => validateProjectName(v),
    },
  )
  try {
    await ideApi.createProject(value.trim())
    await loadProjects()
    ElMessage.success(`工程「${value.trim()}」创建成功`)
  } catch (e: any) {
    // 后端错误透出（重名 / 非法字符等）
    ElMessage.error(e?.response?.data?.detail || e?.message || '工程创建失败')
  }
}

async function loadFiles() {
  if (!curPid.value) return
  files.value = (await ideApi.files(curPid.value)) as any
  if (files.value.length) await openFile(files.value[0])
  else curFile.value = null
}

/* 合约文件命名规范：*.sol 结尾（Solidity 源文件） */
const SOL_RE = /^[\w\u4e00-\u9fa5\-]+\.sol$/

async function createFile() {
  if (!curPid.value || !newPath.value) return
  let path = newPath.value.trim()
  if (path && !path.toLowerCase().endsWith('.sol')) path += '.sol'
  if (!SOL_RE.test(path)) {
    ElMessage.warning('合约文件名不规范：仅支持中文、字母、数字、下划线、中划线，且以 .sol 结尾')
    return
  }
  try {
    await ideApi.saveFile({ project_id: curPid.value, path, content: '' })
    newPath.value = ''
    await loadFiles()
    ElMessage.success(`合约文件 ${path} 已创建，可在此编译部署调试`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '文件创建失败')
  }
}

async function openFile(f: any) {
  const full = (await ideApi.getFile(f.id)) as any
  curFile.value = full
  if (editor) editor.setValue(full.content || '')
}

async function save() {
  if (!curFile.value) return
  curFile.value.content = editor.getValue()
  await ideApi.saveFile({
    id: curFile.value.id, project_id: curPid.value,
    path: curFile.value.path, content: curFile.value.content,
  })
  ElMessage.success('已保存到云端')
}

async function delFile(fid: string) {
  await ideApi.deleteFile(fid)
  await loadFiles()
}

async function loadBuiltin(b: any) {
  // 把内置合约载入新文件
  const path = b.file
  if (!curPid.value) {
    await ideApi.createProject('default')
    await loadProjects()
  }
  await ideApi.saveFile({ project_id: curPid.value, path, content: b.source })
  await loadFiles()
  ElMessage.success(`已载入 ${b.name} 模板`)
}

async function compile() {
  if (!curFile.value) return
  result.value = null
  errors.value = []
  const r: any = await contractApi.compile({ name: curFile.value.path.replace('.sol', ''), source: editor.getValue() })
  if (r.errors?.length) errors.value = r.errors
  curFile.value._abi = r.abi
  curFile.value._bytecode = r.bytecode
  curFile.value._standard = r.standard
  lastAbi.value = r.abi || []
  tab.value = 'errors'
  if (r.ok) {
    result.value = {
      '状态': '✓ 编译成功',
      '协议标准': r.standard || '自定义',
      'ABI 函数数': String(r.abi?.length || 0),
      '字节码长度': String(r.bytecode?.length || 0),
      'solc 版本': r.solc_version || '-',
    }
    ElMessage.success('编译成功，可点击「ABI 接口」查看函数列表')
  } else {
    ElMessage.error('编译失败，查看错误输出')
  }
}

async function deploy() {
  if (!curFile.value) return
  if (!curFile.value._abi) {
    ElMessage.warning('请先编译')
    return
  }
  // 检测构造函数参数
  const ctor = (curFile.value._abi as any[]).find((x: any) => x.type === 'constructor')
  const ctorInputs = ctor?.inputs || []
  let ctorArgs: any[] | null = []
  if (ctorInputs.length) {
    ctorArgs = await promptCtorArgs(ctorInputs)
    if (ctorArgs === null) return // 用户取消
  }
  errors.value = []
  tab.value = 'result'
  try {
    const r: any = await contractApi.deploy({
      name: curFile.value.path.replace('.sol', ''),
      source: editor.getValue(),
      abi: curFile.value._abi,
      bytecode: curFile.value._bytecode,
      deployer: app.currentWallet,
      standard: curFile.value._standard,
      ctor_args: ctorArgs.length ? ctorArgs : undefined,
    })
    result.value = {
      '状态': '✓ 部署成功（真实链已写入）',
      '合约地址': r.address,
      '交易哈希': r.tx_hash,
      '区块号': String(r.block_number),
      'Gas 消耗': String(r.gas_used || 0),
      '协议标准': r.standard || '自定义',
      '部署者': app.currentWallet,
      '构造参数': ctorArgs.length ? ctorArgs.join(', ') : '无',
    }
    ElMessage.success('部署成功，前往「接口调试」调用')
    app.refreshStatus()
  } catch (e: any) {
    errors.value = [e.response?.data?.detail || e.message]
    tab.value = 'errors'
  }
}

async function audit() {
  if (!curFile.value) return
  try {
    const r: any = await contractApi.audit({
      source: editor.getValue(),
      name: curFile.value.path.replace('.sol', ''),
    })
    auditResult.value = r
    tab.value = 'audit'
    ElMessage.success('安全审计完成')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '安全审计失败')
  }
}

const scoreClass = computed(() => {
  const s = auditResult.value?.score ?? 0
  if (s >= 80) return 'score-good'
  if (s >= 60) return 'score-warn'
  return 'score-bad'
})

// 构造函数参数表单
async function promptCtorArgs(inputs: any[]): Promise<any[] | null> {
  const fields = inputs.map((inp: any) => ({
    label: `${inp.type}  ${inp.name || ''}`,
    placeholder: _defaultPlaceholder(inp.type),
  }))
  const html = fields.map((f: any, i: number) =>
    `<div style="margin-bottom:12px">
       <label style="display:block;color:#7b8aab;font-size:12px;margin-bottom:4px;font-family:monospace">${f.label}</label>
       <input id="ctor-arg-${i}" class="el-input__inner" style="width:100%;background:#0e1424;border:1px solid #1f2a44;border-radius:4px;color:#d6e2ff;padding:8px 12px;font-family:monospace" placeholder="${f.placeholder}" />
     </div>`
  ).join('')
  try {
    await ElMessageBox({
      title: '构造函数参数',
      message: `<div style="margin:-4px 0 8px;color:#4d8dff;font-size:12px">◆ 该合约构造函数需要以下参数，部署时将编码追加到字节码末尾</div>${html}`,
      dangerouslyUseHTMLString: true,
      confirmButtonText: '部署',
      cancelButtonText: '取消',
      showCancelButton: true,
      customClass: 'ctor-dialog',
    })
  } catch {
    return null
  }
  return inputs.map((inp: any, i: number) => {
    const el = document.getElementById(`ctor-arg-${i}`) as HTMLInputElement
    return el?.value || ''
  })
}

function _defaultPlaceholder(type: string): string {
  if (type.startsWith('uint') || type.startsWith('int')) return '如 1000000'
  if (type === 'address') return '如 0x1234... 或别名 0xlearner'
  if (type === 'bool') return 'true 或 false'
  if (type === 'string') return '如 MyToken'
  if (type.startsWith('bytes')) return '0x...'
  return ''
}

/* Monaco 初始化：必须在 monaco 动态加载完成后调用 */
function initEditor() {
  const mod = monacoMod.value!
  editor = mod.editor.create(monacoRef.value!, {
    value: '// 选择左侧文件或载入内置协议\n',
    language: 'sol',
    theme: 'vs-dark',
    automaticLayout: true,
    fontSize: 14,
    minimap: { enabled: false },
  })
  mod.languages.register({ id: 'sol' })
  mod.languages.setMonarchTokensProvider('sol', {
    tokenizer: {
      root: [
        [/\b(pragma|contract|function|public|private|internal|external|returns|return|mapping|address|uint|string|bool|require|emit|event|constructor|memory|storage|view|pure|constant|if|else|for|while|import|using|struct|enum|modifier|virtual|override|new|this|super)\b/, 'keyword'],
        [/\b\d+\b/, 'number'],
        [/\/\/.*$/, 'comment'],
        [/\/\*[\s\S]*?\*\//, 'comment'],
        [/"[^"]*"/, 'string'],
        [/'[^']*'/, 'string'],
      ],
    },
  })
  editorReady.value = true
  // 如果打开了文件，立即把内容写入编辑器
  if (curFile.value?.content != null) {
    editor.setValue(curFile.value.content)
  }
}

/* ⚡ 核心生命周期：三阶段异步加载
 * - 阶段 1（0ms）：组件挂载 → 显示骨架 + 过渡动画（用户感知：瞬时切换）
 * - 阶段 2（nextTick）：并行请求轻量数据（projects/builtin），不阻塞 UI
 * - 阶段 3（180ms 后）：过渡动画已播放完毕，此时才加载 10MB+ Monaco
 *   → 用户永远感觉不到主线程阻塞，切 tab 体验从 1~2s → <150ms
 */
onMounted(async () => {
  // 阶段 1：让浏览器先把骨架 DOM 画出来
  await nextTick()
  // 阶段 2：并行拉数据，不 await（API 请求异步，不阻塞 Monaco 加载）
  contractApi.builtin().then(r => { builtin.value = r as any }).catch(() => {})
  loadProjects().catch(() => {})
  // 阶段 3：过渡结束（140ms）+ 一点缓冲，再加载 Monaco（主线程唯一可能阻塞的地方）
  const t1 = window.setTimeout(async () => {
    try {
      if (!monacoMod.value) {
        monacoMod.value = await import('monaco-editor')
      }
      await nextTick()
      initEditor()
    } catch (e: any) {
      console.warn('[ContractIDE] Monaco load failed:', e?.message || e)
      // Monaco 失败时至少保证编辑器区有可见占位，避免 UI 空白
      editorReady.value = true
    }
  }, 180)
  onBeforeUnmount(() => window.clearTimeout(t1))
})

/* keep-alive 激活时：如果 Monaco 已加载，只刷新一下 editor 布局 */
onActivated(() => {
  if (editor) {
    // defer 一帧，避免和 transition 抢占
    window.setTimeout(() => editor.layout(), 50)
  }
})

onBeforeUnmount(() => {
  try { editor?.dispose() } catch {}
  editor = null
})
</script>

<style scoped lang="scss">
.ide { display: grid; grid-template-columns: 260px 1fr; gap: 14px; height: calc(100vh - 110px); }
.side { display: flex; flex-direction: column; overflow: auto; }
.file-ops { display: flex; gap: 6px; margin-bottom: 10px; }
.file-tree { flex: 1; overflow: auto; }
.file-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-radius: 4px; cursor: pointer;
  color: var(--dq-text-dim); font-size: 13px;
  &:hover { background: var(--dq-bg-2); color: var(--dq-text); .del { opacity: 1; } }
  &.active { background: rgba(0,230,195,0.1); color: var(--dq-primary); }
  .del { margin-left: auto; opacity: 0; }
}
.builtin { border-top: 1px solid var(--dq-border); padding-top: 10px; margin-top: 10px; }
.proto { display: flex; align-items: center; gap: 8px; padding: 6px; cursor: pointer; border-radius: 4px; font-size: 12px; }
.proto:hover { background: var(--dq-bg-2); }
.proto-file { color: var(--dq-text-dim); font-family: var(--dq-mono); }

.editor-area { display: flex; flex-direction: column; overflow: hidden; }
.editor-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 10px; border-bottom: 1px solid var(--dq-border);
  .cur-file { color: var(--dq-primary); }
  .ops { display: flex; gap: 8px; }
}

/* Monaco + 骨架容器 */
.monaco-wrap {
  flex: 1; margin-top: 10px; border: 1px solid var(--dq-border); border-radius: 6px; overflow: hidden;
  position: relative; background: #070b16;
}
.monaco-skeleton {
  position: absolute; inset: 0; z-index: 2;
  display: flex; align-items: center; justify-content: center; gap: 18px;
  background: linear-gradient(135deg, rgba(7,11,22,0.98), rgba(14,20,36,0.96));
  color: var(--dq-text-dim);
  .sk-spinner {
    width: 28px; height: 28px; border-radius: 50%;
    border: 3px solid rgba(0,230,195,0.18);
    border-top-color: var(--dq-primary);
    animation: dq-spin 0.8s linear infinite;
    box-shadow: 0 0 12px rgba(0,230,195,0.25);
  }
  .sk-text { max-width: 380px;
    .sk-t1 { font-size: 13px; font-weight: 600; color: var(--dq-text); margin-bottom: 4px; }
    .sk-t2 { font-size: 11px; line-height: 1.6; color: var(--dq-text-dim); }
  }
}
@keyframes dq-spin { to { transform: rotate(360deg); } }
.monaco {
  width: 100%; height: 100%;
  transition: opacity 0.2s ease;
}

.output { height: 220px; margin-top: 10px; border-top: 1px solid var(--dq-border); padding-top: 8px; display: flex; flex-direction: column; }
.out-tabs { display: flex; gap: 16px; margin-bottom: 8px; }
.tab { font-size: 12px; color: var(--dq-text-dim); cursor: pointer; padding-bottom: 4px; &.active { color: var(--dq-primary); border-bottom: 2px solid var(--dq-primary); } }
.out-body { flex: 1; margin: 0; background: var(--dq-bg); padding: 12px; border-radius: 6px; overflow: auto; font-size: 12px; color: var(--dq-text); border: 1px solid var(--dq-border); }

.ok-line { color: var(--dq-success); font-size: 13px; }
.err-list { display: flex; flex-direction: column; gap: 6px; }
.err-item { display: flex; gap: 8px; align-items: flex-start; padding: 6px 8px; background: rgba(255,84,112,0.06); border-radius: 4px; }
.err-tag { background: var(--dq-error); color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 700; flex-shrink: 0; }

.res-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed var(--dq-border); }
.res-k { color: var(--dq-text-dim); }
.res-v { color: var(--dq-text); text-align: right; word-break: break-all; }
.res-v.link { color: var(--dq-primary); cursor: pointer; &:hover { text-decoration: underline; } }
.res-ops { margin-top: 12px; display: flex; gap: 8px; }
.placeholder-out { color: var(--dq-text-dimmer); }
.ft-empty-text { font-size: 12px; color: var(--dq-text-dim); text-align: center; padding: 0 8px 4px; line-height: 1.6; }

.abi-tip { color: var(--dq-text-dim); font-size: 11px; margin-bottom: 10px; padding: 6px 8px; background: rgba(77,141,255,0.06); border-radius: 4px; }
.abi-fn { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px dashed var(--dq-border); flex-wrap: wrap;
  &:last-child { border: none; }
  .fn-name { color: var(--dq-primary); font-weight: 600; }
  .fn-args { color: var(--dq-text-dim); font-size: 11px; }
  .fn-ret { color: var(--dq-accent); font-size: 11px; margin-left: auto; }
}

// 安全审计样式
.audit-container { display: flex; flex-direction: column; gap: 12px; }
.audit-score {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 16px; border-radius: 8px; background: var(--dq-bg-2);
  .score-num { font-size: 32px; font-weight: 700; line-height: 1; }
  .score-label { font-size: 12px; color: var(--dq-text-dim); margin-top: 6px; }
  &.score-good .score-num { color: var(--dq-success); }
  &.score-warn .score-num { color: var(--dq-warning); }
  &.score-bad .score-num { color: var(--dq-error); }
}
.audit-summary {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  .summary-item {
    display: flex; flex-direction: column; align-items: center; padding: 10px 8px;
    border-radius: 6px; background: var(--dq-bg-2);
    .summary-label { font-size: 11px; color: var(--dq-text-dim); margin-bottom: 4px; }
    .summary-value { font-size: 18px; font-weight: 600; }
    &.severity-high .summary-value { color: var(--dq-error); }
    &.severity-medium .summary-value { color: var(--dq-warning); }
    &.severity-low .summary-value { color: var(--dq-primary); }
  }
}
.audit-issues { display: flex; flex-direction: column; gap: 8px; max-height: 200px; overflow-y: auto; }
.audit-item {
  padding: 10px 12px; border-radius: 6px; border-left: 3px solid;
  background: var(--dq-bg-2);
  &.severity-high { border-left-color: var(--dq-error); }
  &.severity-medium { border-left-color: var(--dq-warning); }
  &.severity-low { border-left-color: var(--dq-primary); }
  .issue-header {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    .severity-tag {
      font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px; color: #fff;
      .severity-high & { background: var(--dq-error); }
      .severity-medium & { background: var(--dq-warning); }
      .severity-low & { background: var(--dq-primary); }
    }
    .issue-type { font-size: 11px; color: var(--dq-text); }
    .issue-line { font-size: 10px; color: var(--dq-text-dim); margin-left: auto; }
  }
  .issue-message { font-size: 12px; color: var(--dq-text); line-height: 1.5; margin-bottom: 4px; }
  .issue-suggestion {
    font-size: 11px; color: var(--dq-text-dim); line-height: 1.5;
    .suggestion-label { color: var(--dq-primary); font-weight: 500; }
  }
}
.audit-empty { text-align: center; padding: 24px 0; color: var(--dq-text-dim); font-size: 12px; }
</style>
