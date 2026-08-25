<template>
  <div class="cloud dq-enter-up">
    <!-- 左侧：步骤导航 + 进度 -->
    <div class="left">
      <div class="dq-card steps-card">
        <div class="dq-card-title">
          联盟链搭建实训
          <span class="dq-live" style="margin-left:auto"><span class="dot"></span>真实 EVM</span>
        </div>

        <!-- 总进度环 + 数据行 -->
        <div class="progress-head">
          <!-- SVG 进度环 -->
          <div class="ring-wrap">
            <svg class="ring" viewBox="0 0 120 120">
              <defs>
                <linearGradient id="cd-ring-g" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stop-color="#00e6c3"/>
                  <stop offset="100%" stop-color="#4d8dff"/>
                </linearGradient>
              </defs>
              <circle cx="60" cy="60" r="48" fill="none" stroke="var(--dq-border)" stroke-width="9"/>
              <circle
                cx="60" cy="60" r="48" fill="none"
                stroke="url(#cd-ring-g)" stroke-width="9" stroke-linecap="round"
                :stroke-dasharray="ringDash" :stroke-dashoffset="ringOffset"
                transform="rotate(-90 60 60)"
                style="transition: stroke-dashoffset .6s cubic-bezier(0.4, 0, 0.2, 1)"
              />
            </svg>
            <div class="ring-inner">
              <div class="ring-pct dq-grad-text">{{ progressPct }}%</div>
              <div class="ring-sub">总进度</div>
            </div>
          </div>
          <!-- 进度信息 -->
          <div class="ph-info">
            <div class="ph-row">
              <span class="ph-k">已完成</span>
              <span class="ph-v dq-mono"><b>{{ doneSteps.length }}</b> / {{ steps.length }} 步</span>
            </div>
            <div class="ph-row">
              <span class="ph-k">累计耗时</span>
              <span class="ph-v dq-mono">{{ totalDuration }}</span>
            </div>
            <div class="ph-row">
              <span class="ph-k">当前块高</span>
              <span class="ph-v dq-mono">#{{ chainHeight }}</span>
            </div>
            <div class="ph-ops">
              <el-button size="small" @click="resetAll" :disabled="!doneSteps.length">
                <el-icon><RefreshLeft /></el-icon>重置全部
              </el-button>
              <el-button size="small" @click="rollback" :disabled="!doneSteps.length">
                <el-icon><Back /></el-icon>回退上一步
              </el-button>
            </div>
          </div>
        </div>

        <!-- 小进度条（与环互补） -->
        <div class="progress-bar">
          <div class="pb-fill" :style="{ width: progressPct + '%' }"></div>
        </div>

        <el-steps direction="vertical" :active="active" finish-status="success" class="dq-steps">
          <el-step
            v-for="(s, i) in steps"
            :key="s.step"
            :title="stepTitle(s, i)"
            :description="stepDesc(s, i)"
            :status="doneSteps.includes(s.step) ? 'success' : (i === active ? 'process' : 'wait')"
            @click.native="active = i"
          />
        </el-steps>
      </div>

      <!-- 当前步骤详情 -->
      <div class="dq-card step-detail" v-if="cur">
        <div class="step-head">
          <span class="step-no">步骤 {{ cur.step }}</span>
          <span class="step-title">{{ cur.title }}</span>
          <span class="step-duration dq-tag info" v-if="stepDurations[cur.step]">
            <el-icon><Timer /></el-icon>耗时 {{ stepDurations[cur.step] }}
          </span>
          <span class="step-done-at dq-tag" v-else-if="doneSteps.includes(cur.step)">
            <el-icon><CircleCheckFilled /></el-icon>已完成
          </span>
        </div>
        <p class="desc">{{ cur.desc }}</p>

        <!-- 原理讲解 -->
        <div class="dq-principle" v-if="cur.principle">
          <div class="dp-label">◆ 原理讲解</div>
          <div>{{ cur.principle }}</div>
        </div>

        <!-- 需要执行的命令（严格按顺序执行） -->
        <div class="section-label">
          需要执行的命令（按顺序执行 {{ cmdDoneCount }}/{{ cur.commands.length }}）
        </div>
        <div class="cmds">
          <div
            class="dq-cmd-line"
            :class="cmdState(i)"
            v-for="(c, i) in cur.commands"
            :key="i"
            @dblclick="fillCommand(c)"
            title="双击填充到输入框"
          >
            <span class="prompt">{{ cmdStateIcon(i) }}</span>
            <code>{{ c }}</code>
          </div>
        </div>

        <!-- 预期输出 -->
        <div class="section-label">预期输出</div>
        <el-alert :title="cur.expected" type="info" :closable="false" show-icon />

        <!-- 提示 -->
        <div class="dq-tip" v-if="cur.tip">
          <span class="dt-label">学习提示:</span>{{ cur.tip }}
        </div>

        <!-- 知识点小结 -->
        <div class="knowledge-box">
          <div class="kb-head">
            <span class="kb-icon">💡</span>
            <span class="kb-title">知识点小结 · Step {{ cur.step }}</span>
            <el-button type="text" size="small" class="kb-toggle" @click="kbOpen = !kbOpen">
              <el-icon><component :is="kbOpen ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
            </el-button>
          </div>
          <div class="kb-body" v-show="kbOpen">
            <ul class="kb-list">
              <li v-for="(k, i) in curKnowledge" :key="i"><i class="kb-dot"></i>{{ k }}</li>
            </ul>
          </div>
        </div>

        <div class="ops">
          <el-button size="small" @click="goPrev" :disabled="active === 0">
            <el-icon><ArrowLeft /></el-icon>上一步
          </el-button>
          <el-button @click="goNext" :disabled="active >= steps.length - 1">
            下一步&nbsp;<el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 右侧：监控面板 + 云桌面终端 -->
    <div class="right-panel">
      <!-- 实时监控面板 -->
      <div class="dq-card monitor-card">
        <div class="dq-card-title">
          <el-icon><Monitor /></el-icon>
          实时监控
          <span class="monitor-status" :class="nodeStatusClass">
            <span class="status-dot"></span>
            {{ nodeStatusText }}
          </span>
        </div>
        <div class="monitor-grid">
          <div class="monitor-item">
            <div class="mi-label">区块高度</div>
            <div class="mi-value">#{{ chainHeight }}</div>
          </div>
          <div class="monitor-item">
            <div class="mi-label">共识节点</div>
            <div class="mi-value">4/4</div>
          </div>
          <div class="monitor-item">
            <div class="mi-label">出块速度</div>
            <div class="mi-value">~3s</div>
          </div>
          <div class="monitor-item">
            <div class="mi-label">交易数</div>
            <div class="mi-value">{{ txCount }}</div>
          </div>
        </div>
        <div class="node-list">
          <div class="node-item" v-for="node in nodes" :key="node.id">
            <span class="node-id">{{ node.id }}</span>
            <span class="node-role">{{ node.role }}</span>
            <span class="node-status" :class="node.status">
              <span class="dot"></span>
              {{ node.status === 'running' ? '运行中' : '已停止' }}
            </span>
          </div>
        </div>
      </div>

      <!-- 云桌面终端 + 文件浏览器 + 编辑器（标签页切换） -->
      <div class="dq-card terminal-card">
        <div class="dq-card-title">
          云桌面
          <span class="dq-tag info" style="margin-left:auto">手动输入 · 真实执行</span>
        </div>
        
        <!-- 标签页切换 -->
        <div class="tab-bar">
          <div 
            class="tab-item" 
            :class="{ active: activeTab === 'terminal' }"
            @click="activeTab = 'terminal'"
          >
            <el-icon><Monitor /></el-icon>
            终端
          </div>
          <div 
            class="tab-item" 
            :class="{ active: activeTab === 'files' }"
            @click="activeTab = 'files'"
          >
            <el-icon><FolderOpened /></el-icon>
            文件浏览器
          </div>
          <div 
            class="tab-item" 
            :class="{ active: activeTab === 'editor' }"
            @click="activeTab = 'editor'"
            :style="{ opacity: currentFile ? 1 : 0.5 }"
          >
            <el-icon><Document /></el-icon>
            编辑器
            <span v-if="currentFile && fileModified" class="modified-dot"></span>
          </div>
        </div>

        <!-- 终端面板 -->
        <div class="tab-content" v-show="activeTab === 'terminal'">
          <div class="term-wrap">
            <div class="term" ref="termRef"></div>
          </div>
          <div class="term-foot">
            <span class="tf-hint">💡 在终端内直接输入命令，回车执行；上下键切换历史；Tab 补全。</span>
            <div class="tf-kw">
              <span>PBFT</span>
              <span>EVM</span>
              <span>Solidity</span>
              <span>Web3</span>
            </div>
          </div>
        </div>

        <!-- 文件浏览器面板 -->
        <div class="tab-content" v-show="activeTab === 'files'">
          <div class="file-browser">
            <div class="file-toolbar">
              <el-button size="small" @click="createNewFile">
                <el-icon><Plus /></el-icon>新建文件
              </el-button>
              <el-button size="small" @click="createNewFolder">
                <el-icon><FolderAdd /></el-icon>新建文件夹
              </el-button>
              <el-button size="small" @click="refreshFileTree">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </div>
            <div class="file-tree">
              <div 
                class="tree-item" 
                v-for="item in fileTree" 
                :key="item.path"
                :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }"
              >
                <span 
                  class="tree-toggle" 
                  @click="toggleFolder(item)"
                  v-if="item.type === 'folder'"
                >
                  <el-icon v-if="item.expanded"><ArrowDown /></el-icon>
                  <el-icon v-else><ArrowRight /></el-icon>
                </span>
                <span class="tree-icon" v-else></span>
                <span class="tree-icon">
                  <el-icon v-if="item.type === 'folder'">
                    <FolderOpened v-if="item.expanded" />
                    <Folder v-else />
                  </el-icon>
                  <el-icon v-else><Document /></el-icon>
                </span>
                <span 
                  class="tree-name" 
                  @click="item.type === 'file' && openFile(item)"
                  :class="{ 'is-file': item.type === 'file' }"
                >
                  {{ item.name }}
                </span>
                <span class="tree-actions">
                  <el-button 
                    size="small" 
                    type="text" 
                    @click.stop="deleteFile(item)"
                    v-if="item.type === 'file'"
                  >
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 编辑器面板 -->
        <div class="tab-content" v-show="activeTab === 'editor'">
          <div class="editor-panel" v-if="currentFile">
            <div class="editor-toolbar">
              <span class="file-path">{{ currentFile.path }}</span>
              <span class="file-status" :class="{ modified: fileModified }">
                {{ fileModified ? '● 未保存' : '✓ 已保存' }}
              </span>
              <el-button size="small" @click="saveFile" :disabled="!fileModified">
                <el-icon><Check /></el-icon>保存
              </el-button>
              <el-button size="small" @click="closeFile">
                <el-icon><Close /></el-icon>关闭
              </el-button>
            </div>
            <div class="editor-wrap" ref="editorRef"></div>
          </div>
          <div class="editor-empty" v-else>
            <el-icon><Document /></el-icon>
            <p>请在文件浏览器中选择一个文件以打开编辑器</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, onActivated, computed, nextTick, watch, shallowRef } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { chainApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import { safeGet, safeSet, fmtDuration } from '@/utils/storage'
import * as monaco from 'monaco-editor'

const app = useAppStore()
const steps = ref<any[]>([])
const active = ref(0)
const loading = ref(false)
const termRef = ref<HTMLElement>()
const currentLine = ref('')        // 终端行内输入缓冲（替代旧 cmdInput）
const cmdHistory = ref<string[]>([])
const historyIdx = ref(-1)
const termBusy = ref(false)        // 命令执行中，屏蔽键盘输入
const kbOpen = ref(true)

/* ---------- 标签页切换 ---------- */
const activeTab = ref<'terminal' | 'files' | 'editor'>('terminal')

/* ---------- 虚拟文件系统 ---------- */
interface FileNode {
  name: string
  path: string
  type: 'file' | 'folder'
  content?: string
  children?: FileNode[]
  expanded?: boolean
  depth: number
  parent?: string
}

const FS_KEY = 'cloud_fs_v1'

function getDefaultFS(): FileNode[] {
  return [
    {
      name: 'nodes', path: '/nodes', type: 'folder', expanded: true, depth: 0,
      children: [
        {
          name: 'node0', path: '/nodes/node0', type: 'folder', expanded: false, depth: 1,
          children: [
            { name: 'config.ini', path: '/nodes/node0/config.ini', type: 'file', depth: 2, content: `[p2p]\nlisten_ip=0.0.0.0\nlisten_port=30300\nchannel_listen_ip=0.0.0.0\nchannel_listen_port=20200\njsonrpc_listen_ip=0.0.0.0\njsonrpc_listen_port=8545\n\n[consensus]\nconsensus_type=pbft\nmax_tx_num=1000\n\n[state]\ntype=mpt\n\n[storage]\ntype=rocksdb\n` },
            { name: 'genesis.ini', path: '/nodes/node0/genesis.ini', type: 'file', depth: 2, content: `[consensus]\nconsensus_type=pbft\nmax_block_limit=3\n` },
          ]
        },
        {
          name: 'node1', path: '/nodes/node1', type: 'folder', expanded: false, depth: 1,
          children: [
            { name: 'config.ini', path: '/nodes/node1/config.ini', type: 'file', depth: 2, content: `[p2p]\nlisten_ip=0.0.0.0\nlisten_port=30301\n` },
          ]
        },
      ]
    },
    {
      name: 'contracts', path: '/contracts', type: 'folder', expanded: true, depth: 0,
      children: [
        { name: 'GreenEnergy.sol', path: '/contracts/GreenEnergy.sol', type: 'file', depth: 1, content: `// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n\nimport "./ERC20.sol";\n\ncontract GreenEnergy is ERC20 {\n    mapping(string => bool) public mintRole;\n    address public owner;\n\n    constructor(uint256 initialSupply) ERC20("GreenEnergy", "GEE", 0) {\n        owner = msg.sender;\n        _mint(msg.sender, initialSupply);\n        mintRole["metro"] = true;\n        mintRole["bus"] = true;\n        mintRole["bike"] = true;\n        mintRole["takeout"] = true;\n        mintRole["recycle"] = true;\n    }\n\n    function mintRole(string memory role, address to, uint256 amount) public {\n        require(mintRole[role], "Not authorized");\n        _mint(to, amount);\n    }\n}\n` },
        { name: 'ERC20.sol', path: '/contracts/ERC20.sol', type: 'file', depth: 1, content: `// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n\ncontract ERC20 {\n    string public name;\n    string public symbol;\n    uint8 public decimals;\n    uint256 public totalSupply;\n    mapping(address => uint256) public balanceOf;\n\n    constructor(string memory _name, string memory _symbol, uint8 _decimals) {\n        name = _name;\n        symbol = _symbol;\n        decimals = _decimals;\n    }\n\n    function _mint(address to, uint256 amount) internal {\n        totalSupply += amount;\n        balanceOf[to] += amount;\n    }\n}\n` },
      ]
    },
    {
      name: 'scripts', path: '/scripts', type: 'folder', expanded: false, depth: 0,
      children: [
        { name: 'build_chain.sh', path: '/scripts/build_chain.sh', type: 'file', depth: 1, content: `#!/bin/bash\n# 构建联盟链节点\nNODES="node0 node1 node2 node3"\nfor node in $NODES; do\n  echo "Building $node..."\n  cp -r template/ $node/\n  echo "Done: $node"\ndone\n` },
        { name: 'start_all.sh', path: '/scripts/start_all.sh', type: 'file', depth: 1, content: `#!/bin/bash\n# 启动所有节点\nfor node in node0 node1 node2 node3; do\n  cd $node && bash start.sh &\ndone\necho "All nodes started"\n` },
      ]
    },
    { name: 'README.md', path: '/README.md', type: 'file', depth: 0, content: `# 绿色低碳联盟链实训\n\n本实训环境模拟了一个 4 节点 PBFT 共识的联盟链，映射 6 个绿色低碳组织。\n\n## 目录结构\n- nodes/ - 节点配置\n- contracts/ - 智能合约\n- scripts/ - 部署脚本\n` },
  ]
}

function loadFS(): FileNode[] {
  const raw = safeGet<FileNode[] | null>(FS_KEY, null)
  return Array.isArray(raw) ? raw : getDefaultFS()
}

const fileSystem = ref<FileNode[]>(loadFS())
const persistFS = () => safeSet(FS_KEY, fileSystem.value)

/* 扁平化文件树（用于渲染） */
const fileTree = computed<FileNode[]>(() => {
  const result: FileNode[] = []
  function walk(nodes: FileNode[]) {
    for (const node of nodes) {
      result.push(node)
      if (node.type === 'folder' && node.expanded && node.children) {
        walk(node.children)
      }
    }
  }
  walk(fileSystem.value)
  return result
})

function toggleFolder(item: FileNode) {
  item.expanded = !item.expanded
}

function findNode(path: string, nodes: FileNode[] = fileSystem.value): FileNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.children) {
      const found = findNode(path, node.children)
      if (found) return found
    }
  }
  return null
}

function openFile(item: FileNode) {
  currentFile.value = item
  fileModified.value = false
  activeTab.value = 'editor'
  nextTick(() => initEditor())
}

function closeFile() {
  if (fileModified.value) {
    ElMessageBox.confirm('文件尚未保存，确定关闭吗？', '提示', { type: 'warning' }).then(() => {
      currentFile.value = null
      destroyEditor()
    }).catch(() => {})
  } else {
    currentFile.value = null
    destroyEditor()
  }
}

function createNewFile() {
  ElMessageBox.prompt('请输入文件名（含路径，如 /contracts/MyContract.sol）', '新建文件', {
    confirmButtonText: '创建',
    cancelButtonText: '取消',
    inputValue: '/contracts/',
  }).then(({ value }) => {
    if (!value) return
    const parts = value.split('/')
    const fileName = parts.pop()!
    const parentPath = parts.join('/') || '/'
    const parent = findNode(parentPath)
    if (!parent || parent.type !== 'folder') {
      ElMessage.error('父目录不存在')
      return
    }
    if (!parent.children) parent.children = []
    parent.children.push({
      name: fileName,
      path: value,
      type: 'file',
      content: '',
      depth: parent.depth + 1,
    })
    parent.expanded = true
    persistFS()
    ElMessage.success(`文件 ${value} 已创建`)
  }).catch(() => {})
}

function createNewFolder() {
  ElMessageBox.prompt('请输入文件夹路径（如 /contracts/mylib）', '新建文件夹', {
    confirmButtonText: '创建',
    cancelButtonText: '取消',
    inputValue: '/contracts/',
  }).then(({ value }) => {
    if (!value) return
    const parts = value.split('/')
    const folderName = parts.pop()!
    const parentPath = parts.join('/') || '/'
    const parent = findNode(parentPath)
    if (!parent || parent.type !== 'folder') {
      ElMessage.error('父目录不存在')
      return
    }
    if (!parent.children) parent.children = []
    parent.children.push({
      name: folderName,
      path: value,
      type: 'folder',
      expanded: false,
      children: [],
      depth: parent.depth + 1,
    })
    parent.expanded = true
    persistFS()
    ElMessage.success(`文件夹 ${value} 已创建`)
  }).catch(() => {})
}

function deleteFile(item: FileNode) {
  ElMessageBox.confirm(`确定删除 ${item.name} 吗？`, '删除文件', { type: 'warning' }).then(() => {
    // 从父节点移除
    const parts = item.path.split('/')
    parts.pop()
    const parentPath = parts.join('/') || '/'
    const parent = findNode(parentPath)
    if (parent && parent.children) {
      parent.children = parent.children.filter(c => c.path !== item.path)
    } else {
      // 顶层
      fileSystem.value = fileSystem.value.filter(c => c.path !== item.path)
    }
    if (currentFile.value?.path === item.path) {
      currentFile.value = null
      destroyEditor()
    }
    persistFS()
    ElMessage.success(`${item.name} 已删除`)
  }).catch(() => {})
}

function refreshFileTree() {
  // 触发重新渲染
  fileSystem.value = [...fileSystem.value]
  ElMessage.success('文件树已刷新')
}

/* ---------- Monaco 编辑器 ---------- */
const editorRef = ref<HTMLElement>()
const currentFile = ref<FileNode | null>(null)
const fileModified = ref(false)
let editorInstance: monaco.editor.IStandaloneCodeEditor | null = null

function getLanguageFromPath(path: string): string {
  if (path.endsWith('.sol')) return 'solidity'
  if (path.endsWith('.ini')) return 'ini'
  if (path.endsWith('.sh') || path.endsWith('.bash')) return 'shell'
  if (path.endsWith('.json')) return 'json'
  if (path.endsWith('.md')) return 'markdown'
  if (path.endsWith('.js') || path.endsWith('.ts')) return 'typescript'
  if (path.endsWith('.py')) return 'python'
  return 'plaintext'
}

function initEditor() {
  if (!editorRef.value || !currentFile.value) return
  destroyEditor()
  
  const lang = getLanguageFromPath(currentFile.value.path)
  editorInstance = monaco.editor.create(editorRef.value, {
    value: currentFile.value.content || '',
    language: lang,
    theme: 'vs-dark',
    fontSize: 13,
    fontFamily: "'JetBrains Mono', Consolas, monospace",
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    padding: { top: 12 },
    lineNumbers: 'on',
    renderLineHighlight: 'all',
    wordWrap: 'on',
  })

  editorInstance.onDidChangeModelContent(() => {
    fileModified.value = true
  })
}

function destroyEditor() {
  if (editorInstance) {
    editorInstance.dispose()
    editorInstance = null
  }
}

function saveFile() {
  if (!currentFile.value || !editorInstance) return
  currentFile.value.content = editorInstance.getValue()
  fileModified.value = false
  persistFS()
  ElMessage.success(`${currentFile.value.name} 已保存`)
}

/* ---------- 命令补全（Tab 键行内补全） ---------- */
const ALL_COMMANDS = [
  'cd', 'ls', 'cat', 'mkdir', 'touch', 'rm', 'cp', 'mv',
  'tail', 'head', 'grep', 'echo', 'chmod', 'ps', 'kill',
  'bash', 'source', 'export', 'ifconfig', 'ping',
  './build_chain.sh', './start_all.sh', './stop_all.sh',
  'fisco-bcos', 'console',
]

function tabComplete(): string | null {
  const val = currentLine.value
  if (!val || val.length < 2) return null
  const matches = ALL_COMMANDS.filter(c => c.startsWith(val) && c !== val)
  return matches.length > 0 ? matches[0] : null
}

/* ---------- 双击命令填充（写入终端行内缓冲，回车即执行） ---------- */
function fillCommand(cmd: string) {
  activeTab.value = 'terminal'
  nextTick(() => {
    term?.focus()
    // 若当前行有残留输入，先擦除后填充
    if (currentLine.value) {
      const bs = '\b \b'.repeat(currentLine.value.length)
      term.write(bs)
    }
    currentLine.value = cmd
    term.write(cmd)
    ElMessage.success('命令已填入终端，按回车执行')
  })
}

watch(activeTab, (tab) => {
  if (tab === 'terminal') {
    nextTick(() => {
      try { fit?.fit() } catch {}
      term?.focus()
    })
  }
  if (tab === 'editor' && currentFile.value) {
    nextTick(() => initEditor())
  }
})

/* ---------- 监控面板数据 ---------- */
const txCount = ref(0)
const nodes = ref([
  { id: 'node0', role: '管理员+地铁', status: 'running' },
  { id: 'node1', role: '公交+单车', status: 'running' },
  { id: 'node2', role: '外卖+回收', status: 'running' },
  { id: 'node3', role: '热备/监管', status: 'running' },
])
const nodeStatusClass = computed(() => {
  const allRunning = nodes.value.every(n => n.status === 'running')
  return allRunning ? 'status-ok' : 'status-warn'
})
const nodeStatusText = computed(() => {
  const running = nodes.value.filter(n => n.status === 'running').length
  return running === 4 ? '全部在线' : `${running}/4 在线`
})

// 定时更新交易数（模拟）
let txTimer: any = null
function startTxTimer() {
  if (txTimer) clearInterval(txTimer)
  txTimer = setInterval(() => {
    txCount.value += Math.floor(Math.random() * 3)
  }, 5000)
}

/* ---------- 持久化键 ---------- */
const DONE_KEY = 'cloud_done_v1'
const DUR_KEY = 'cloud_step_dur_v1'      // { stepNum: seconds }
const START_KEY = 'cloud_step_start_v1' // 执行开始时间戳（用于当前步）

/* ---------- 已完成步骤持久化（双写：localStorage + 服务端，换浏览器/换设备也能续） ---------- */
function loadDoneSteps(): number[] {
  const raw = safeGet<any[]>(DONE_KEY, [])
  return Array.isArray(raw) ? raw.filter((x) => typeof x === 'number') : []
}
const doneSteps = ref<number[]>(loadDoneSteps())
const persistDone = () => safeSet(DONE_KEY, doneSteps.value)

/** 从服务端拉取该钱包的搭链进度（优先级高于 localStorage，取两者并集） */
async function syncProgressFromServer() {
  try {
    const wallet = app.currentWallet || '0xlearner'
    const r: any = await chainApi.progress(wallet)
    if (!r || !Array.isArray(r.steps)) return
    const serverDone = (r.steps || []).filter((s: any) => s.done).map((s: any) => s.step)
    const merged = Array.from(new Set([...doneSteps.value, ...serverDone]))
    if (merged.length > doneSteps.value.length) {
      doneSteps.value = merged
      persistDone()
    }
  } catch {
    /* 服务端拉取失败不阻塞，继续用 localStorage */
  }
}

/* ---------- 每步耗时持久化 ---------- */
type DurMap = Record<number, number>
function loadDurations(): DurMap {
  const raw = safeGet<DurMap>(DUR_KEY, {})
  const out: DurMap = {}
  if (raw && typeof raw === 'object') {
    for (const k of Object.keys(raw)) {
      const v = Number((raw as any)[k])
      if (v > 0) out[Number(k)] = v
    }
  }
  return out
}
const stepDurationsRaw = ref<DurMap>(loadDurations())
const stepDurations = computed<Record<number, string>>(() => {
  const out: Record<number, string> = {}
  for (const [k, v] of Object.entries(stepDurationsRaw.value)) {
    out[Number(k)] = fmtDuration(v)
  }
  return out
})
const persistDur = () => safeSet(DUR_KEY, stepDurationsRaw.value)

/* 累计总耗时 */
const totalDuration = computed(() => {
  const total = Object.values(stepDurationsRaw.value).reduce((a, b) => a + b, 0)
  return fmtDuration(total)
})

/* 当前执行开始时间（临时，存内存 + localStorage 防止刷新中断丢失） */
const curStartTs = ref<number | null>(null)
function startTimer() {
  curStartTs.value = Date.now()
  safeSet(START_KEY, curStartTs.value)
}
function stopTimer(stepNum: number): number {
  const start = curStartTs.value || safeGet<number | null>(START_KEY, null)
  safeSet(START_KEY, null)
  curStartTs.value = null
  if (!start) return 0
  const sec = Math.max(1, Math.round((Date.now() - start) / 1000))
  stepDurationsRaw.value[stepNum] = (stepDurationsRaw.value[stepNum] || 0) + sec
  persistDur()
  return sec
}

/* ---------- 进度环 ---------- */
const RING_CIRCUM = 2 * Math.PI * 48
const ringDash = `${RING_CIRCUM} ${RING_CIRCUM}`
const ringOffset = computed(() => {
  const pct = steps.value.length ? doneSteps.value.length / steps.value.length : 0
  return String(RING_CIRCUM * (1 - pct))
})

/* ---------- 步骤标题 / 描述扩展（注入耗时 badge） ---------- */
function stepTitle(s: any, _i: number) {
  return `${s.step}. ${s.title}`
}
/* 10 步 el-step__description 精简摘要（侧栏卡片短描述；详情在下方 principle/commands/expected 面板） */
const STEP_DESC_SHORT: Record<number, string> = {
  1: '4 节点 PBFT 配置+启动，6 组织映射',
  2: '4 fisco-bcos 进程存活+6 组织对照',
  3: 'tail 日志，PBFT 持续出块（+seal/Report）',
  4: 'console 4 命令验链（块高/Peer/Sealer/Group）',
  5: '6 成员↔4 节点↔钱包地址 三元映射表',
  6: '6 角色能量梯度：0/50/20/15/10/100',
  7: '6 钱包地址 + Step 9 后试发 1000 押金',
  8: '3 项验收：节点/余额/合约查询通过',
  9: '部署 GreenEnergy ERC20 (1,000,000)',
  10: 'name/balanceOf + 地铁+50、外卖+10 验证',
}
function stepDesc(s: any, _i: number) {
  const dur = stepDurations.value[s.step]
  const txt = STEP_DESC_SHORT[s.step] ?? s.desc
  if (dur) return `${txt} · ⏱ ${dur}`
  return txt
}

let term: Terminal
let fit: FitAddon

const cur = computed(() => steps.value[active.value])
const chainHeight = computed(() => app.chainHeight)
const progressPct = computed(() => steps.value.length ? Math.round(doneSteps.value.length / steps.value.length * 100) : 0)

/* ---------- 步骤内命令顺序状态（用于左侧命令列表展示） ---------- */
function cmdState(i: number): string {
  const idx = cur.value?.cmd_idx ?? -1
  if (i <= idx) return 'done'          // 已完成
  if (i === idx + 1) return 'active'   // 当前待执行
  return 'wait'                        // 未执行
}
function cmdStateIcon(i: number): string {
  const s = cmdState(i)
  if (s === 'done') return '✓'
  if (s === 'active') return '▶'
  return '○'
}
const cmdDoneCount = computed(() => {
  const idx = cur.value?.cmd_idx ?? -1
  return Math.min(cur.value?.commands?.length ?? 0, idx + 1)
})

/* 每步知识点（10 步版：Step 5-8 专门覆盖 6 大联盟节点） */
const KNOWLEDGE: Record<number, string[]> = {
  1: [
    '绿色低碳联盟链由 6 个组织共建：🛡️管理员 / 🚇地铁 / 🚌公交 / 🚲单车 / 📦外卖 / ♻️回收，实训用 4 节点复用承载',
    '4 共识节点承载映射：node0=管理员+地铁；node1=公交+单车；node2=外卖+回收；node3=热备/监管',
    'PBFT 共识：3f+1 节点可容忍 f 个拜占庭节点，4 节点 = 容忍 1 个恶意节点',
    'build_chain.sh 自动生成：节点证书、genesis 创世块、config.ini 配置、启动脚本；生产可改 6 物理节点',
  ],
  2: [
    '4 个进程对应 4 个逻辑节点，但通过「钱包地址 + 角色白名单」隔离出 6 个业务组织',
    '6 角色盘点：0xadmin 管理员 / 0xmetro 地铁 / 0xbus 公交 / 0xbike 单车 / 0xtakeout 外卖 / 0xrecycle 回收',
    '进程存活 ≠ 业务可用，还需要：钱包链上存在 + 角色白名单 + 合约权限 三件事同时成立',
    '生产环境通常用 systemd/supervisor 守护进程，异常退出自动重启',
  ],
  3: [
    '绿色低碳链的每笔能量发放（mint）和资产兑换都会在这些区块里打包',
    'node0 出块时：多为地铁发能量、管理员部署合约类交易',
    'node1 出块时：多为公交/单车发能量类交易',
    'node2 出块时：多为外卖/回收发能量 + NFT 兑换类交易；node3 可切 observer 只验不包',
    '`+++Generating seal` 表示 sealer 开始打包，`Report` 表示 PBFT 三阶段完成、区块落盘',
  ],
  4: [
    '控制台通过 Channel 协议连接节点（双向长连接 + 证书认证），比 JSON-RPC 更安全',
    'getBlockNumber / getPeers / getSealerList / getGroupPeers 是联盟链运维四件套',
    '6 个业务组织（admin/metro/bus/bike/takeout/recycle）共享同一个 groupId=1，通过钱包地址区分角色',
    '后续 Step 5~8 将逐一落实 6 角色的职责、能量规则、钱包注册、验收',
  ],
  // ==================== Step 5-8：6 大联盟节点组织配置（新增） ====================
  5: [
    '6 联盟组织 ↔ 4 共识节点映射（实训复用版）：node0=管理员+地铁；node1=公交+单车；node2=外卖+回收；node3=热备',
    '6 组织「四要素」：组织名 → 角色 → 承载节点 → 钱包地址，任意一步发能量都要求四要素同时匹配',
    '管理员（🛡️0xadmin）在 node0：部署合约、管理树种，不发能量（避免利益冲突）',
    '5 个业务角色在对应节点：地铁🚇+50 / 公交🚌+20 / 单车🚲+15 / 外卖📦+10 / 回收♻️+100',
  ],
  6: [
    '能量发放值按「减碳贡献」梯度设计：回收 100 > 地铁 50 > 公交 20 > 单车 15 > 外卖 10 > 管理员 0',
    '管理员发 0 能量是刻意设计：治理角色不直接发币，防止自交易（self-dealing）',
    '前端 /eco 的角色卡片顺序和能量值就来自这张规则表，后端 emit_energy 也按此表做白名单校验',
    '回收 1kg 对应 100 能量，是为了鼓励用户回收行为、配合绿色外卖减塑场景形成正循环',
  ],
  7: [
    '6 组织用 6 个独立钱包地址：0xadmin / 0xmetro / 0xbus / 0xbike / 0xtakeout / 0xrecycle',
    'ERC20 两种发能量模式：① mint（所有者造币）② transfer（余额转账），实训用 mint 白名单更直观',
    'mintRole 白名单 = [ metro, bus, bike, takeout, recycle ] 共 5 个；admin 保留 owner 权限可增删白名单',
    '生产环境推荐「管理员 → 业务角色预拨押金 + transferFrom」模型，比 mint 更合规便于审计',
  ],
  8: [
    '联盟链「上线」有 4 件事要同时通过：① 共识节点在线 ② 6 钱包链上有余额 ③ 合约权限白名单 ④ 前端角色卡片放开',
    'GreenEnergy.mint → 6 角色（owner + 5 业务角色）可调用；PlantCertificate.mint → 仅 admin（防作弊）',
    'EcoBadge.mint → admin 发勋章，bike + admin 联合发骑行券（对应单车业务）',
    '6 角色验收通过 = Step 9/10 部署代币合约后，联盟运营模块 /eco 就可以完全放开使用',
  ],
  // Step 9-10 = 原 Step 5-6（顺延）
  9: [
    'GreenEnergy 是 ERC20 标准代币，构造函数仅需 initialSupply 参数，decimals=0（整数积分）',
    '部署交易 to 字段为空、data = 字节码 + 构造函数参数 ABI 编码；EVM 执行构造函数初始化状态',
    '合约地址 = keccak256(rlp([sender,nonce]))[12:] 后 20 字节，确定性生成',
    'Deployer 用 0xadmin（管理员身份部署），6 角色通过 mintRole 白名单获得发能量授权',
  ],
  10: [
    'name() / balanceOf() 是 view 函数，本地执行不消耗 Gas 不上链',
    'mint() / transfer() 是状态变更函数，广播交易、消耗 Gas、产生 Transfer 事件日志',
    '6 角色发放链路已打通：🚇地铁→alice+50；📦外卖→learner+10；♻️回收→learner+100',
    'Step 10 完成 → 进入绿色低碳联盟链（/eco）即可体验完整 6 角色运营闭环：发放→累积→兑换→挂牌→购买→下架',
  ],
}
const curKnowledge = computed(() => (cur.value ? KNOWLEDGE[cur.value.step] || [] : []))

/* ---------- 上一步 / 下一步 ---------- */
function goPrev() { active.value = Math.max(0, active.value - 1) }
function goNext() { active.value = Math.min(steps.value.length - 1, active.value + 1) }

/* ---------- 回退上一步 ---------- */
async function rollback() {
  if (!doneSteps.value.length) return
  const last = doneSteps.value[doneSteps.value.length - 1]
  try {
    await ElMessageBox.confirm(
      `确定回退「步骤 ${last}」吗？已完成标记会移除（链上数据不会回滚）。`,
      '回退步骤',
      { type: 'warning', confirmButtonText: '确认回退', cancelButtonText: '取消' },
    )
  } catch { return }
  doneSteps.value.pop()
  persistDone()
  // 同时移除该步骤的耗时
  if (stepDurationsRaw.value[last]) {
    delete stepDurationsRaw.value[last]
    persistDur()
  }
  // 跳到被回退那步
  const idx = steps.value.findIndex((s) => s.step === last)
  if (idx >= 0) active.value = idx
  ElMessage.success(`已回退步骤 ${last}`)
}

/* ---------- 重置全部（服务端 + 本地双清） ---------- */
async function resetAll() {
  if (!doneSteps.value.length) return
  try {
    await ElMessageBox.confirm(
      '确定重置整个搭链教程进度吗？所有步骤的完成状态与耗时都将清空（链上数据不会回滚）。',
      '重置进度',
      { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' },
    )
  } catch { return }
  doneSteps.value = []
  stepDurationsRaw.value = {}
  persistDone()
  persistDur()
  try { await chainApi.resetProgress(app.currentWallet || '0xlearner') } catch {}
  active.value = 0
  ElMessage.success('进度已重置，从第 1 步重新开始')
}

/* ---------- 核心：学生手动输入命令执行 ---------- */
async function execCommand(cmd: string) {
  if (!cur.value || termBusy.value) return
  cmd = cmd.trim()
  if (!cmd) return

  // 记录命令历史
  cmdHistory.value.push(cmd)
  historyIdx.value = cmdHistory.value.length
  currentLine.value = ''

  // 命令已在终端行内输入完毕（onData 回车时已显示），这里只换行
  term.write('\r\n')

  loading.value = true
  termBusy.value = true
  startTimer()
  try {
    const wallet = app.currentWallet || '0xlearner'
    const r: any = await chainApi.execCommand(cur.value.step, cmd, wallet)

    // 输出执行结果（接近真实终端：# 开头为注释行 dim 灰色，[INFO]/[OK]/[WARN]/[ERROR] 按级别着色）
    const out = r.output || ''
    if (r.ok) {
      // 成功：按真实终端日志风格分色
      out.split('\n').forEach((line: string) => {
        // 注释行 / 业务映射说明（dim 灰色，像真实 shell 注释或日志的辅助信息）
        if (/^\s*(#|<-|>>>|node\d)/.test(line) || line.startsWith('  <-')) {
          term.writeln(`\x1b[2;37m${line}\x1b[0m`)
        }
        // [完成] 步骤完成标记（青色高亮）
        else if (/^\[完成\]/.test(line)) {
          term.writeln(`\x1b[36m${line}\x1b[0m`)
        }
        // [INFO] 日志级别标签（蓝色，真实 FISCO-BCOS 日志风格）
        else if (/^\[INFO\]/.test(line)) {
          term.writeln(`\x1b[34m${line}\x1b[0m`)
        }
        // [CHECK] 健康检查标签（蓝色）
        else if (/^\[CHECK\]/.test(line)) {
          term.writeln(`\x1b[34m${line}\x1b[0m`)
        }
        // [OK] / SUCCESS / completed / start successful（绿色成功）
        else if (/^\[(OK|INFO)\]/.test(line) && line.includes('OK') || /completed|SUCCESS|start successful|all checks passed|nodes online/i.test(line)) {
          term.writeln(`\x1b[32m${line}\x1b[0m`)
        }
        // Return: 视图函数返回值 / : OK 成功标记 / succeeded! 端口连通（绿色）
        else if (/^Return[:\s]/i.test(line) || /:\s*OK\s*$/.test(line) || /succeeded!/.test(line) || /\bOK\b\s*$/.test(line)) {
          term.writeln(`\x1b[32m${line}\x1b[0m`)
        }
        // [WARN] / [ERROR] 日志级别（黄/红）
        else if (/^\[WARN\]/.test(line)) {
          term.writeln(`\x1b[33m${line}\x1b[0m`)
        }
        else if (/^\[ERROR\]/.test(line)) {
          term.writeln(`\x1b[31m${line}\x1b[0m`)
        }
        // 合约地址、交易哈希、区块号、Gas、Receipt 等 key=value 关键信息（黄色高亮）
        else if (/contract address|transaction hash|block number|tx hash|block height|transactionHash|contractAddress|blockNumber|gasUsed|blockHash|status:/i.test(line)) {
          term.writeln(`\x1b[33m${line}\x1b[0m`)
        }
        // notBefore/notAfter/subject 证书信息（青色）
        else if (/^(subject=|notBefore=|notAfter=|issuer=)/.test(line)) {
          term.writeln(`\x1b[36m${line}\x1b[0m`)
        }
        // Connection to ... 端口连通性（绿色）
        else if (/^Connection to .* succeeded/.test(line)) {
          term.writeln(`\x1b[32m${line}\x1b[0m`)
        }
        // 十六进制地址/哈希（青色）
        else if (/0x[a-fA-F0-9]{20,}/.test(line)) {
          term.writeln(`\x1b[36m${line}\x1b[0m`)
        }
        // 数值/统计（蓝色）
        else if (/balance|amount|gas used|gasUsed|count|total|数量|余额|总计/i.test(line)) {
          term.writeln(`\x1b[34m${line}\x1b[0m`)
        }
        // 空行 / 普通行
        else {
          term.writeln(line)
        }
      })
      // 成功后同步命令进度
      if (typeof r.cmd_index === 'number' && r.cmd_index >= 0) {
        cur.value.cmd_idx = r.cmd_index
        cur.value.cmd_total = r.cmd_total
      }
    } else if (r.error_type === 'order') {
      // 顺序错误：真实 shell 报错风格（bash: ...: command not found / 命令顺序约束）
      term.writeln(`\x1b[31mbash: warning: 命令执行顺序错误\x1b[0m`)
      out.split('\n').forEach((line: string) => {
        if (line.startsWith('$ ') || line.startsWith('# ')) {
          term.writeln(`\x1b[36m${line}\x1b[0m`)
        } else if (line.trim()) {
          term.writeln(`\x1b[33m${line}\x1b[0m`)
        }
      })
    } else {
      // 失败：真实 stderr 风格（红色）
      term.writeln(`\x1b[31mbash: error: 命令执行失败\x1b[0m`)
      out.split('\n').forEach((line: string) => {
        if (/语法错误|失败|Error|error/i.test(line)) {
          term.writeln(`\x1b[31m${line}\x1b[0m`)
        } else if (line.trim()) {
          term.writeln(`\x1b[37m${line}\x1b[0m`)
        }
      })
    }
    term.writeln('')
    // 命令结束后输出新的 PS1 提示符（真实 shell 行为：每条命令结束都换行出新提示符）
    term.write('\x1b[1;32mroot@fisco-vm\x1b[0m:\x1b[1;34m~/fisco\x1b[0m# ')

    const elapsed = stopTimer(cur.value.step)

    // 如果命令执行成功且步骤完成
    if (r.step_completed) {
      const wasNew = !doneSteps.value.includes(cur.value.step)
      if (wasNew) {
        doneSteps.value = [...doneSteps.value, cur.value.step]
        persistDone()
        try { app.confetti({ particleCount: 60, spread: 60, origin: { y: 0.55 }, ticks: 140 }) } catch {}
        term.writeln(`\x1b[36m└─ ✅ 步骤 ${cur.value.step} 完成 · 耗时 ${fmtDuration(elapsed)} ──────────\x1b[0m`)
        term.writeln('')
      }
      syncProgressFromServer()
      if (doneSteps.value.length === steps.value.length) {
        ElMessage({
          type: 'success',
          duration: 5500,
          message: '🎉 恭喜完成全部 10 步搭链教程！6 大联盟节点配置完成，前往绿色低碳联盟链开始完整运营体验吧',
        })
        try { app.confetti({ particleCount: 160, spread: 90, startVelocity: 50, origin: { y: 0.5 }, ticks: 220 }) } catch {}
      } else if (wasNew) {
        ElMessage.success(`步骤 ${cur.value.step} 完成 · 耗时 ${fmtDuration(elapsed)} (${progressPct.value}%)`)
      }
      app.refreshStatus()
      if (wasNew && active.value < steps.value.length - 1) {
        nextTick(() => { active.value = Math.min(steps.value.length - 1, active.value + 1) })
      }
    } else if (!r.ok) {
      term.writeln(`\x1b[31m└─ ❌ 执行失败，请按上方提示修正后重试 ──────────\x1b[0m`)
      term.writeln('')
    }
  } catch (e: any) {
    term.writeln(`\x1b[31m执行异常: ${e.message || e}\x1b[0m`)
    term.writeln('')
  } finally {
    if (curStartTs.value) stopTimer(cur.value?.step || 0)
    loading.value = false
    termBusy.value = false
  }
}

/* ---------- 命令历史导航（上下键，直接操作终端行内文本） ---------- */
function clearCurrentLine() {
  if (currentLine.value) {
    term.write('\b \b'.repeat(currentLine.value.length))
    currentLine.value = ''
  }
}

function historyUp() {
  if (cmdHistory.value.length === 0 || termBusy.value) return
  if (historyIdx.value > 0) {
    historyIdx.value--
  } else if (historyIdx.value === 0) {
    return
  } else {
    historyIdx.value = cmdHistory.value.length - 1
  }
  clearCurrentLine()
  currentLine.value = cmdHistory.value[historyIdx.value]
  term.write(currentLine.value)
}

function historyDown() {
  if (cmdHistory.value.length === 0 || termBusy.value) return
  if (historyIdx.value < cmdHistory.value.length - 1) {
    historyIdx.value++
    clearCurrentLine()
    currentLine.value = cmdHistory.value[historyIdx.value]
    term.write(currentLine.value)
  } else {
    // 到达末尾：清空当前行
    historyIdx.value = cmdHistory.value.length
    clearCurrentLine()
  }
}

/* ---------- 终端初始化（接近真实 Linux 登录 + FISCO-BCOS 运维机） ---------- */
function initTerm() {
  term = new Terminal({
    theme: {
      background: '#0a0e14',          // 接近真实终端的深炭灰（非纯黑）
      foreground: '#e6e6e6',
      cursor: '#00e6c3',
      cursorAccent: '#0a0e14',
      selectionBackground: '#264f4a',
      black: '#1f1f1f', brightBlack: '#5a5a5a',
      red: '#ff5c57', brightRed: '#ff7b7b',
      green: '#5af78e', brightGreen: '#00e6c3',
      yellow: '#f3f99d', brightYellow: '#ffcf4d',
      blue: '#9aedfe', brightBlue: '#4d8dff',
      magenta: '#ca4985', brightMagenta: '#f5379b',
      cyan: '#9aedfe', brightCyan: '#4d8dff',
      white: '#e6e6e6', brightWhite: '#ffffff',
    },
    fontFamily: "'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace",
    fontSize: 13,
    lineHeight: 1.05,
    cursorBlink: true,                // 真实终端光标闪烁
    disableStdin: false,              // 启用终端直接输入（无外部输入框）
    allowProposedApi: true,
    scrollback: 5000,
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termRef.value!)
  fit.fit()

  // 真实 SSH 登录后的 motd（/etc/motd 风格）：系统信息 + 包列表 + 当前用户
  const now = new Date()
  const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${now.toLocaleTimeString('zh-CN', { hour12: false })}`
  term.writeln('\x1b[1;32mWelcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-86-generic x86_64)\x1b[0m')
  term.writeln('')
  term.writeln(' * Documentation:  https://help.ubuntu.com')
  term.writeln(' * Management:     https://landscape.canonical.com')
  term.writeln(' * Support:        https://ubuntu.com/advantage')
  term.writeln('')
  term.writeln('Last login: ' + ts + ' from 192.168.1.100')
  term.writeln('')
  // FISCO-BCOS 运维机环境
  term.writeln('\x1b[1;36m╔══════════════════════════════════════════════════════════════╗\x1b[0m')
  term.writeln('\x1b[1;36m║  FISCO-BCOS 联盟链实训云桌面 · Ubuntu 22.04 + FISCO-BCOS 2.9.1 ║\x1b[0m')
  term.writeln('\x1b[1;36m╚══════════════════════════════════════════════════════════════╝\x1b[0m')
  term.writeln('')
  term.writeln('\x1b[2mSystem load:    0.08              Processes:           124\x1b[0m')
  term.writeln('\x1b[2mUsage of /:     18.5% of 49.15GB   Users logged in:    1\x1b[0m')
  term.writeln('\x1b[2mMemory usage:   23%                IPv4 address:        192.168.1.10\x1b[0m')
  term.writeln('\x1b[2mSwap usage:     0%                 Disk:                /dev/sda1\x1b[0m')
  term.writeln('')
  // 已安装工具清单（真实运维机风格）
  term.writeln('\x1b[33mInstalled packages (chain-related):\x1b[0m')
  term.writeln('  fisco-bcos          2.9.1       /usr/local/bin/fisco-bcos')
  term.writeln('  console             2.9.1       ~/fisco/console')
  term.writeln('  java                11.0.20     /usr/lib/jvm/java-11-openjdk')
  term.writeln('  openssl             3.0.10      /usr/bin/openssl')
  term.writeln('  curl                7.81.0      /usr/bin/curl')
  term.writeln('  netcat-openbsd      1.219       /usr/bin/nc')
  term.writeln('')
  if (Object.keys(stepDurationsRaw.value).length) {
    term.writeln(`\x1b[33m[history] 已记录 ${Object.keys(stepDurationsRaw.value).length} 步历史耗时，累计 ${totalDuration.value}\x1b[0m`)
    term.writeln('')
  }
  // 提示 + 第一行 PS1
  term.writeln('\x1b[2m# 在终端内直接输入命令，回车执行；上下键切换历史；Tab 补全\x1b[0m')
  term.writeln('')
  // 初始 PS1 提示符（真实 shell 行为：光标紧跟 # 后）
  term.write('\x1b[1;32mroot@fisco-vm\x1b[0m:\x1b[1;34m~/fisco\x1b[0m# ')

  // 终端行内输入处理（替代外部输入框）
  term.onData((data: string) => {
    if (termBusy.value) return  // 命令执行中，屏蔽输入

    // 回车（\r = Enter）
    if (data === '\r') {
      const cmd = currentLine.value
      if (cmd.trim()) {
        execCommand(cmd)
      } else {
        // 空行：只换行 + 新 PS1
        term.write('\r\n\x1b[1;32mroot@fisco-vm\x1b[0m:\x1b[1;34m~/fisco\x1b[0m# ')
      }
      return
    }

    // Backspace（\x7f = DEL）
    if (data === '\x7f' || data === '\b') {
      if (currentLine.value.length > 0) {
        currentLine.value = currentLine.value.slice(0, -1)
        term.write('\b \b')
      }
      return
    }

    // 上箭头（\x1b[A）/ 下箭头（\x1b[B）
    if (data === '\x1b[A') { historyUp(); return }
    if (data === '\x1b[B') { historyDown(); return }

    // Tab 补全（\t）
    if (data === '\t') {
      const suggestion = tabComplete()
      if (suggestion) {
        const remain = suggestion.slice(currentLine.value.length)
        currentLine.value = suggestion
        term.write(remain)
      }
      return
    }

    // Ctrl+C（\x03）：中断当前行，输出 ^C + 新 PS1
    if (data === '\x03') {
      term.write('^C\r\n\x1b[1;32mroot@fisco-vm\x1b[0m:\x1b[1;34m~/fisco\x1b[0m# ')
      currentLine.value = ''
      return
    }

    // Ctrl+V / Cmd+V 粘贴拦截
    if (data === '\x16') {
      ElMessage.warning('云桌面终端禁止粘贴，请手动输入命令')
      return
    }

    // 普通可打印字符（含 UTF-8 多字节中文）
    // 过滤其他 ANSI 控制序列（方向键左/右/Home/End/PageUp/Down 等）避免光标错位
    if (data >= ' ' || /[\x80-\xff]/.test(data)) {
      currentLine.value += data
      term.write(data)
    }
  })

  // 终端获得焦点（点击终端区域即可输入）
  termRef.value?.addEventListener('click', () => term?.focus())
  nextTick(() => term?.focus())
}

/* ---------- 生命周期 ---------- */
onMounted(async () => {
  const wallet = app.currentWallet || '0xlearner'
  const r: any = await chainApi.tutorial(wallet)
  steps.value = r.steps
  // 服务端进度 → 合并到本地（换浏览器也能续学）
  await syncProgressFromServer()
  // 如果 localStorage 里有未完成的 timer，防止其永远挂着
  const pending = safeGet<number | null>(START_KEY, null)
  if (pending) safeSet(START_KEY, null)
  await nextTick()
  initTerm()
  window.addEventListener('resize', onResize)
  // 启动交易数定时器
  startTxTimer()
})

onActivated(() => {
  app.refreshStatus()
  // 重新加载持久化数据，保证从其他页切回来时数据最新
  doneSteps.value = loadDoneSteps()
  stepDurationsRaw.value = loadDurations()
  syncProgressFromServer()
})

/* storage 事件：多标签页时互相通知 */
watch(() => app.chainHeight, () => { /* noop */ })

// watch 钱包切换：重新加载该钱包的教程步骤与进度（header 全局切换时联动）
watch(() => app.currentWallet, async (newWallet) => {
  if (!newWallet) return
  try {
    const r: any = await chainApi.tutorial(newWallet)
    steps.value = r.steps
    await syncProgressFromServer()
    // 跳到第一个未完成的步骤
    const firstUndone = steps.value.findIndex((s: any, i: number) => !doneSteps.value.includes(s.step ?? i + 1))
    active.value = firstUndone >= 0 ? firstUndone : steps.value.length - 1
  } catch { /* silent */ }
})

function onResize() { try { fit?.fit() } catch {} }

onBeforeUnmount(() => {
  term?.dispose()
  destroyEditor()
  window.removeEventListener('resize', onResize)
  if (txTimer) clearInterval(txTimer)
})
</script>

<style scoped lang="scss">
.cloud { display: grid; grid-template-columns: 450px 1fr; gap: 14px; height: calc(100vh - 110px); }
.left { display: flex; flex-direction: column; gap: 14px; overflow-y: auto; min-width: 0; padding-right: 4px; }
.steps-card { flex-shrink: 0; min-width: 0; }

/* ---------- 右侧面板布局 ---------- */
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  overflow: hidden;
}

/* ---------- 监控面板 ---------- */
.monitor-card {
  flex-shrink: 0;
  padding: 16px;
  background: linear-gradient(135deg, rgba(0, 230, 195, 0.05), rgba(77, 141, 255, 0.03));
  border: 1px solid rgba(0, 230, 195, 0.2);
}

.monitor-card .dq-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--dq-text);
}

.monitor-status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 12px;
  background: rgba(0, 230, 195, 0.1);
  color: var(--dq-primary);
}

.monitor-status.status-ok .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00e6c3;
  box-shadow: 0 0 8px rgba(0, 230, 195, 0.6);
  animation: pulse 2s ease-in-out infinite;
}

.monitor-status.status-warn {
  background: rgba(255, 207, 77, 0.1);
  color: var(--dq-warn);
}

.monitor-status.status-warn .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ffcf4d;
  box-shadow: 0 0 8px rgba(255, 207, 77, 0.6);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.monitor-item {
  text-align: center;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  transition: all 0.3s;
}

.monitor-item:hover {
  background: rgba(0, 230, 195, 0.05);
  border-color: rgba(0, 230, 195, 0.3);
  transform: translateY(-2px);
}

.mi-label {
  font-size: 11px;
  color: var(--dq-text-dim);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mi-value {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--dq-mono);
  background: var(--dq-grad-primary);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--dq-border);
  border-radius: 6px;
  transition: all 0.2s;
}

.node-item:hover {
  background: rgba(0, 230, 195, 0.03);
  border-color: rgba(0, 230, 195, 0.2);
}

.node-id {
  font-family: var(--dq-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--dq-primary);
  min-width: 60px;
}

.node-role {
  flex: 1;
  font-size: 12px;
  color: var(--dq-text-dim);
}

.node-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 10px;
}

.node-status.running {
  background: rgba(0, 230, 195, 0.1);
  color: var(--dq-primary);
}

.node-status.stopped {
  background: rgba(255, 107, 107, 0.1);
  color: var(--dq-danger);
}

.node-status .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.node-status.running .dot {
  box-shadow: 0 0 6px rgba(0, 230, 195, 0.6);
  animation: pulse 2s ease-in-out infinite;
}

/* ---------- 终端卡片 ---------- */
.terminal-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ---------- 进度头：环 + 信息 ---------- */
.progress-head {
  display: flex; gap: 16px; align-items: center; margin-bottom: 10px;
  padding: 10px; border-radius: 10px;
  background: linear-gradient(135deg, rgba(0,230,195,0.04), rgba(77,141,255,0.03));
  border: 1px solid rgba(255,255,255,0.04);
}
.ring-wrap { position: relative; width: 104px; height: 104px; flex-shrink: 0; }
.ring { width: 100%; height: 100%; }
.ring-inner {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.ring-pct {
  font-size: 22px; font-weight: 800;
  background: var(--dq-grad-primary);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  font-family: var(--dq-mono);
  letter-spacing: -0.5px;
}
.ring-sub { font-size: 10px; color: var(--dq-text-dim); margin-top: 1px; letter-spacing: 0.5px; }

.ph-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.ph-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px;
  .ph-k { color: var(--dq-text-dim); }
  .ph-v { color: var(--dq-text); font-size: 12px; b { color: var(--dq-primary); font-size: 14px; } }
}
.ph-ops {
  display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap;
  .el-button { font-size: 11px !important; padding: 5px 10px !important; }
}

.progress-bar {
  height: 6px; background: var(--dq-bg-2); border-radius: 3px; overflow: hidden; margin-bottom: 6px;
  .pb-fill { height: 100%; background: var(--dq-grad-primary); border-radius: 3px; transition: width .4s; box-shadow: 0 0 8px var(--dq-primary-glow); }
}
.dq-steps { cursor: pointer; }
:deep(.el-steps) {
  .el-step { max-width: 100%; flex-basis: auto !important; }
  .el-step__main { padding-right: 6px; }
  .el-step__title { color: var(--dq-text-dim); word-break: break-word; line-height: 1.4; &.is-process, &.is-finish { color: var(--dq-primary); } }
  .el-step__description { color: var(--dq-text-dimmer); font-size: 12px; word-break: break-word; white-space: normal; line-height: 1.5; padding-right: 0; }
  .el-step__icon { flex-shrink: 0; }
}

/* ---------- 步骤详情 ---------- */
.step-detail {
  min-width: 0;
  .step-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
  .step-no { font-family: var(--dq-mono); font-size: 12px; color: var(--dq-primary); background: rgba(0,230,195,0.1); padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
  .step-title { font-size: 16px; font-weight: 600; color: var(--dq-text); }
  .step-duration, .step-done-at { margin-left: auto; font-size: 11px; gap: 4px; }
  .desc { color: var(--dq-text-dim); margin: 0 0 12px; line-height: 1.6; word-break: break-word; }
}
.section-label { font-size: 12px; color: var(--dq-text-dim); margin: 14px 0 8px; text-transform: uppercase; letter-spacing: 1px; }
.cmds { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; min-width: 0; }
.cmds :deep(.dq-cmd-line) { max-width: 100%; code { word-break: break-all; white-space: normal; } }

/* ---------- 命令执行顺序状态 ---------- */
.cmds :deep(.dq-cmd-line) {
  &.done {
    opacity: 0.55;
    border-left-color: rgba(0, 230, 195, 0.6);
    .prompt { color: var(--dq-primary); }
    code { color: var(--dq-text-dim); }
  }
  &.active {
    border-left-color: var(--dq-primary);
    background: rgba(0, 230, 195, 0.07);
    box-shadow: 0 0 0 1px rgba(0, 230, 195, 0.15);
    .prompt { color: var(--dq-primary); font-weight: 700; }
  }
  &.wait {
    opacity: 0.7;
    border-left-color: var(--dq-border);
    .prompt { color: var(--dq-text-dimmer); }
  }
}
.ops { margin-top: 16px; display: flex; gap: 8px; align-items: center; }

/* ---------- 知识点卡片 ---------- */
.knowledge-box {
  margin-top: 14px;
  border: 1px solid rgba(255, 207, 77, 0.25);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(255,207,77,0.06), rgba(255,207,77,0.01));
  overflow: hidden;
  transition: border-color .2s;
  &:hover { border-color: rgba(255, 207, 77, 0.4); }
}
.kb-head {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px dashed rgba(255,207,77,0.2);
}
.kb-icon { font-size: 14px; }
.kb-title { font-weight: 600; color: #e6c97a; font-size: 13px; }
.kb-toggle { margin-left: auto; color: var(--dq-text-dim) !important; padding: 2px !important; }
.kb-body { padding: 10px 12px; }
.kb-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.kb-list li {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 12.5px; color: var(--dq-text); line-height: 1.65;
  .kb-dot {
    flex-shrink: 0; margin-top: 6px;
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--dq-warn); box-shadow: 0 0 4px rgba(255, 207, 77, 0.5);
  }
}

/* ---------- 终端卡片 ---------- */
.terminal-card { display: flex; flex-direction: column; min-width: 0; }
.dq-card-title { display: flex; align-items: center; }
.term-wrap {
  flex: 1; overflow: hidden;
  padding: 10px;
  background: var(--dq-bg);
  border-radius: 8px;
  border: 1px solid var(--dq-border);
  box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
  position: relative;
  &::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0;
    height: 22px;
    background: linear-gradient(180deg, rgba(14,20,36,0.95), rgba(14,20,36,0));
    pointer-events: none;
    z-index: 2;
  }
  &::after {
    content: '● ● ●  terminal@fisco-dev';
    position: absolute; top: 4px; left: 14px;
    font-size: 10px; color: var(--dq-text-dimmer);
    font-family: var(--dq-mono);
    z-index: 3;
    letter-spacing: 1px;
    opacity: 0.7;
  }
}
.term { height: 100%; padding-top: 24px; }
:deep(.xterm) { padding: 4px 8px; }

/* ---------- 终端底部提示条 ---------- */
.term-foot {
  padding-top: 10px;
  display: flex; justify-content: space-between; align-items: center;
  .tf-hint { font-size: 11px; color: var(--dq-text-dimmer); }
  .tf-kw {
    display: flex; gap: 8px;
    span {
      font-family: var(--dq-mono); font-size: 10px;
      padding: 1px 6px; border-radius: 3px;
      color: var(--dq-text-dim);
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--dq-border);
    }
  }
}

@media (max-width: 1180px) {
  .cloud { grid-template-columns: 1fr; height: auto; }
  .terminal-card { min-height: 480px; }
}

/* ---------- 标签页样式 ---------- */
.tab-bar {
  display: flex;
  gap: 2px;
  padding: 0 12px;
  border-bottom: 1px solid var(--dq-border);
  background: rgba(0, 0, 0, 0.2);
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 13px;
  color: var(--dq-text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  position: relative;

  &:hover {
    color: var(--dq-text);
    background: rgba(255, 255, 255, 0.03);
  }

  &.active {
    color: var(--dq-primary);
    border-bottom-color: var(--dq-primary);
    background: rgba(0, 230, 195, 0.05);
  }

  .modified-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--dq-warn);
    margin-left: 4px;
    animation: pulse 1.5s ease-in-out infinite;
  }
}

.tab-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  animation: fadeIn 0.2s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ---------- 文件浏览器样式 ---------- */
.file-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.file-toolbar {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--dq-border);
  background: rgba(0, 0, 0, 0.15);
}

.file-tree {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: rgba(0, 230, 195, 0.05);
  }
}

.tree-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: var(--dq-text-dim);
  flex-shrink: 0;
}

.tree-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: var(--dq-primary);
  flex-shrink: 0;
}

.tree-name {
  flex: 1;
  font-size: 13px;
  color: var(--dq-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.is-file {
    color: var(--dq-text-dim);
    &:hover {
      color: var(--dq-primary);
    }
  }
}

.tree-actions {
  opacity: 0;
  transition: opacity 0.2s;

  .tree-item:hover & {
    opacity: 1;
  }

  .el-button {
    padding: 2px 4px;
    color: var(--dq-text-dimmer);

    &:hover {
      color: var(--dq-danger);
    }
  }
}

/* ---------- 编辑器样式 ---------- */
.editor-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--dq-border);
  background: rgba(0, 0, 0, 0.15);

  .file-path {
    font-family: var(--dq-mono);
    font-size: 12px;
    color: var(--dq-text-dim);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-status {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 10px;
    background: rgba(0, 230, 195, 0.1);
    color: var(--dq-primary);

    &.modified {
      background: rgba(255, 207, 77, 0.1);
      color: var(--dq-warn);
    }
  }
}

.editor-wrap {
  flex: 1;
  overflow: hidden;
}

.editor-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--dq-text-dimmer);
  gap: 12px;

  .el-icon {
    font-size: 48px;
    opacity: 0.3;
  }

  p {
    font-size: 13px;
    margin: 0;
  }
}

/* ---------- 命令列表双击提示 ---------- */
.cmds :deep(.dq-cmd-line) {
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: rgba(0, 230, 195, 0.03);
    transform: translateX(2px);
  }
}
</style>
