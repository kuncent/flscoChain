import http from './http'

/** 跨专业综合实训平台 登录 */
export const authApi = {
  /** 明文密码 RSA 加密（用于账号密码登录；POST 传体，密码不再走 URL） */
  encrypt: (pwd: string) => http.post('/auth/encrypt', { pwd }),
  /** 登录：账号密码（username + passwordEncode）或 智云 SSO（TOKEN） */
  login: (data: { username?: string; passwordEncode?: string; TOKEN?: string }) =>
    http.post('/auth/login', data),
  /** 会话校验：后端对 Bearer JWT 真实验签（不调用外部智云 SSO） */
  session: () => http.get('/auth/session'),
  /** 班级学生列表（教师查看同班学生 + 实训进度概要） */
  classStudents: () => http.get('/auth/class-students') as Promise<any>,
  /** 平台整体实训进度概览（按角色返回不同粒度：学生=个人 / 教师=班级 / 管理员=全校） */
  platformProgress: () => http.get('/auth/platform-progress') as Promise<any>,
}

/** 学生成绩管理（教师 / 管理员可见） */
export const gradesApi = {
  list: (params: { student_id?: string; student_name?: string; course?: string; class_id?: string } = {}) =>
    http.get('/grades/list', { params }) as Promise<any>,
  stats: () => http.get('/grades/stats') as Promise<any>,
  upsert: (data: {
    student_id: string
    student_name: string
    course: string
    score: number
    wallet?: string
    class_id?: string
    school_id?: string
    remark?: string
  }) => http.post('/grades/upsert', data),
  remove: (id: number) => http.delete(`/grades/${id}`),
  /** 按 wallet 实时计算实训成绩明细（不入库，仅返回预览） */
  computeTraining: (data: { wallet: string; manual_score?: number }) =>
    http.post('/grades/compute-training', data),
  /** 批量刷新所有已绑定 wallet 记录的实训成绩 + 综合成绩 */
  refreshTraining: () => http.post('/grades/refresh-training'),
  /** 学生端：按 wallet 查看自己的成绩 */
  myGrades: (wallet: string) =>
    http.get('/grades/my', { params: { wallet } }) as Promise<any>,
  /** 报告→成绩闭环：按 wallet 自动创建/更新成绩草稿 */
  autoDraft: (data: { wallet: string; student_id?: string; student_name?: string; course?: string }) =>
    http.post('/grades/auto-draft', null, { params: data }) as Promise<any>,
}

export const chainApi = {
  status: () => http.get('/chain/status') as Promise<any>,
  tutorial: (wallet = 'default') => http.get('/chain/tutorial', { params: { wallet } }) as Promise<any>,
  execStep: (step: number, wallet = 'default') => http.post('/chain/tutorial/exec', { step, wallet }) as Promise<any>,
  execCommand: (step: number, command: string, wallet = 'default') =>
    http.post('/chain/tutorial/command', { step, command, wallet }) as Promise<any>,
  progress: (wallet = 'default') => http.get('/chain/tutorial/progress', { params: { wallet } }) as Promise<any>,
  resetProgress: (wallet = 'default') => http.post('/chain/tutorial/progress/reset', { wallet }) as Promise<any>,
  /** 组织-节点-角色矩阵（4 逻辑节点 ↔ 6 联盟组织 + 角色职责摘要，公开只读） */
  roleMatrix: () => http.get('/chain/tutorial/rolematrix') as Promise<any>,
  /** 班级搭链进度聚合（教师/管理员；classId 为空时后端按 JWT 身份定位班级） */
  classProgress: (classId = '') =>
    http.get('/chain/tutorial/progress/class', { params: classId ? { class_id: classId } : {} }) as Promise<any>,
}

// 云桌面文件操作 API
export const cloudApi = {
  // 读取虚拟文件
  readFile: (path: string) => http.get('/cloud/files', { params: { path } }) as Promise<any>,
  // 保存虚拟文件
  saveFile: (data: { path: string; content: string }) => http.post('/cloud/files', data) as Promise<any>,
  // 获取目录树结构
  getTree: (path?: string) => http.get('/cloud/tree', { params: { path } }) as Promise<any>,
  // 命令自动补全
  autocomplete: (prefix: string) => http.get('/cloud/autocomplete', { params: { prefix } }) as Promise<any>,
}

export const contractApi = {
  builtin: () => http.get('/contracts/builtin'),
  getBuiltin: (name: string) => http.get(`/contracts/builtin/${name}`),
  compile: (data: { name: string; source: string }) => http.post('/contracts/compile', data),
  deploy: (data: any) => http.post('/contracts/deploy', data),
  deployed: () => http.get('/contracts/deployed'),
  getDeployed: (addr: string) => http.get(`/contracts/deployed/${addr}`),
  call: (data: any) => http.post('/contracts/call', data),
  audit: (data: { source: string; name: string }) => http.post('/contracts/audit', data),
}

export const ideApi = {
  projects: () => http.get('/ide/projects'),
  createProject: (name: string) => http.post('/ide/projects', { name }),
  deleteProject: (pid: string) => http.delete(`/ide/projects/${pid}`),
  files: (pid: string) => http.get(`/ide/projects/${pid}/files`),
  getFile: (fid: string) => http.get(`/ide/files/${fid}`),
  saveFile: (data: any) => http.post('/ide/files', data),
  deleteFile: (fid: string) => http.delete(`/ide/files/${fid}`),
  interfaces: (pid: string) => http.get(`/ide/projects/${pid}/interfaces`),
}

export const explorerApi = {
  overview: () => http.get('/explorer/overview'),
  blocks: (page = 1, size = 20) => http.get('/explorer/blocks', { params: { page, size } }),
  block: (n: number) => http.get(`/explorer/blocks/${n}`),
  txs: (limit = 50, address?: string) => http.get('/explorer/txs', { params: { limit, address } }),
  tx: (hash: string) => http.get(`/explorer/txs/${hash}`),
  contracts: () => http.get('/explorer/contracts'),
  contract: (addr: string) => http.get(`/explorer/contracts/${addr}`),
  address: (addr: string) => http.get(`/explorer/address/${addr}`),
  // 方向一：Gas 分析
  gasAnalysis: (limit = 100) => http.get('/explorer/gas/analysis', { params: { limit } }),
  gasTrend: (hours = 24) => http.get('/explorer/gas/trend', { params: { hours } }),
  // 方向二：代币经济 + 数据一致性
  tokenEconomics: () => http.get('/explorer/token/economics'),
  dataConsistency: () => http.get('/explorer/data/consistency'),
  // 方向三：性能监控
  performanceMetrics: () => http.get('/explorer/performance/metrics'),
}

export const monitorApi = {
  monitor: (addr: string) => http.get(`/monitor/${addr}`),
  methods: (addr: string) => http.get(`/monitor/${addr}/methods`),
  recent: (addr: string, limit = 50) => http.get(`/monitor/${addr}/recent`, { params: { limit } }),
}

export const nftApi = {
  mint: (data: any) => http.post('/nft/mint', data),
  list: (standard?: string) => http.get('/nft/list', { params: { standard } }),
  get: (id: string) => http.get(`/nft/${id}`),
  buy: (data: any) => http.post('/nft/buy', data),
  trades: (id: string) => http.get(`/nft/${id}/trades`),
  /** 全量数字 NFT 成交记录（跨 token，权威数据源，供市场页交易时间线展示） */
  tradesAll: (limit = 200) => http.get('/nft/trades', { params: { limit } }),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/nft/upload', fd)
  },
}

export const walletApi = {
  issue: (data: any) => http.post('/wallet/issue', data),
  tokens: () => http.get('/wallet/tokens'),
  balance: (wallet: string, addr: string) => http.get('/wallet/balance', { params: { wallet, token_address: addr } }),
  balances: (wallet: string) => http.get(`/wallet/balances/${wallet}`),
  transfer: (data: any) => http.post('/wallet/transfer', data),
  transfers: (wallet: string) => http.get(`/wallet/transfers/${wallet}`),
}

export const achievementApi = {
  list: () => http.get('/achievements'),
  myAchievements: () => http.get('/achievements/my'),
  check: (wallet: string) => http.post('/achievements/check', { wallet }),
  stats: () => http.get('/achievements/stats'),
  challenges: () => http.get('/achievements/challenges'),
  myChallenges: () => http.get('/achievements/challenges/my'),
  startChallenge: (challenge_id: string) => http.post('/achievements/challenges/start', { challenge_id }),
  updateProgress: (challenge_id: string, progress: number) =>
    http.post('/achievements/challenges/progress', { challenge_id, progress }),
}

/** 联盟运营微任务（L5 · 10 微任务，服务端自动验收） */
export const missionsApi = {
  /** 拉取任务清单 + 每项服务端自动验收状态（verify.verified / verify.progress / verify.source） */
  curriculum: (wallet: string) =>
    http.get('/missions/curriculum', { params: { wallet } }) as Promise<any>,
}

export const reportApi = {
  /** 获取实训报告聚合数据 */
  aggregate: () => http.get('/report/aggregate'),
  /** 下载 Markdown 版实训报告（后端生成，比前端更准） */
  download: (fmt: 'md' | 'json' = 'md') => http.get(`/report/download?format=${fmt}`, { responseType: 'blob' }),
}

export const chainApiExtra = {
  /** 切换链模式（dev / 教师用） */
  setMode: (mode: 'fisco' | 'evm' | 'mock') => http.post('/chain/mode', { mode }),
}

/** 绿色低碳联盟链 · 高级实战 */
export const ecoApi = {
  roles: () => http.get('/eco/roles'),
  selectRole: (wallet: string, role_key: string) => http.post('/eco/role/select', { wallet, role_key }),
  /** 清除联盟角色选择，回到普通用户身份 */
  clearRole: (wallet: string) => http.post('/eco/role/clear', { wallet }),
  currentRole: (wallet: string) => http.get('/eco/role/current', { params: { wallet } }),
  contractStatus: () => http.get('/eco/contracts/status'),
  builtinContracts: () => http.get('/eco/contracts/builtin'),
  /** 一键编译 + 部署内置绿色合约 */
  deployContract: (name: string, deployer: string = '0xlearner') =>
    http.post('/eco/contracts/deploy', { name, deployer }),
  issueEnergy: (wallet: string, role_key: string, proof: Record<string, any> = {}, force = false) =>
    http.post('/eco/energy/issue', { wallet, role_key, proof, force }),
  energyRecords: (wallet?: string) => http.get('/eco/energy/records', { params: { wallet } }),
  energyBalance: (wallet: string) => http.get('/eco/energy/balance', { params: { wallet } }),
  trees: () => http.get('/eco/trees'),
  addTree: (data: any) => http.post('/eco/trees/add', data),
  exchangeCertificate: (wallet: string, species_id: number) => http.post('/eco/certificates/exchange', { wallet, species_id }),
  certificates: (owner?: string) => http.get('/eco/certificates/list', { params: { owner } }),
  exchangeBadge: (wallet: string, badge_type: string, type_id?: number) =>
    http.post('/eco/badges/exchange', { wallet, badge_type, type_id }),
  badges: (owner?: string) => http.get('/eco/badges/list', { params: { owner } }),
  /** 勋章 / 骑行券类型列表 */
  badgeTypes: () => http.get('/eco/badges/types'),
  /** 管理员 / 联盟角色新增勋章（或骑行券）类型 */
  addBadgeType: (data: {
    wallet: string; badge_type: string; name: string; icon?: string; image_url?: string;
    cost_energy: number; supply: number; desc?: string
  }) => http.post('/eco/badges/types/add', data),
  /** 联盟角色铸造发放勋章 / 骑行券给居民 */
  mintBadge: (data: { wallet: string; role_key: string; type_id: number; to_wallet: string; quantity: number }) =>
    http.post('/eco/badges/mint', data),
  wallet: (wallet: string) => http.get(`/eco/wallet/${wallet}`),
  /** 记录操作成功/失败/警告（供实训报告打分 & 错误分析） */
  recordLog: (data: { wallet: string; module: string; action: string; level: string; message: string; detail?: string }) =>
    http.post('/eco/errors/record', data),
  /** 查看操作日志列表（可选按钱包过滤） */
  listLogs: (wallet?: string, limit = 200) => http.get('/eco/errors/list', { params: { wallet, limit } }),
  /** 绿色资产市场：挂牌 */
  marketList: (data: { seller: string; asset_type: string; asset_id: number; price_energy: number }) =>
    http.post('/eco/market/list', data),
  /** 绿色资产市场：查询在售 */
  marketItems: (asset_type?: string, seller?: string) =>
    http.get('/eco/market/items', { params: { asset_type, seller } }),
  /** 绿色资产市场：购买 */
  marketBuy: (buyer: string, listing_id: number) =>
    http.post('/eco/market/buy', { buyer, listing_id }),
  /** 绿色资产市场：取消挂牌 */
  marketCancel: (listing_id: number, seller: string) =>
    http.post('/eco/market/cancel', { listing_id, seller }),
  /** 绿色资产市场：已成交记录（权威数据源，供市场页交易时间线展示） */
  marketTrades: (limit = 100) => http.get('/eco/market/trades', { params: { limit } }),
  /** 角色工作台：职责 / 权限位 / 角色钱包链上活动统计 / 待办运营动作（只读聚合） */
  roleWorkbench: (role_key: string) =>
    http.get('/eco/role/workbench', { params: { role_key } }) as Promise<any>,
  /** 监管审计视角：块高 / 合约调用健康度 / 异常调用明细 / 各角色能量发放对比（全链只读聚合） */
  auditOverview: () => http.get('/eco/audit/overview') as Promise<any>,
}

/** 学习路径单一事实源（Dashboard 路径卡从后端拉取 + 服务端核验，替代前端硬编码） */
export { learningApi, getLearningPath } from './learning'

/** 任务 #22：运营沙盘（故障演练场景 / 轮次启停 / 处置动作 / 实时 KPI 记分板） */
export const sandboxApi = {
  /** 本班场景列表（教师/管理员） */
  scenarios: () => http.get('/sandbox/scenarios') as Promise<any>,
  /** 创建场景（教师/管理员；scenario_type: node_down/consensus_stall/replay_attack/gas_spike） */
  createScenario: (data: {
    scenario_type: string; title?: string; target_tps?: number;
    duration_s?: number; quota?: number; node_index?: number
  }) => http.post('/sandbox/scenarios', data) as Promise<any>,
  /** 启动一轮演练（教师/管理员） */
  startRound: (scenario_id: number) => http.post('/sandbox/rounds/start', { scenario_id }) as Promise<any>,
  /** 停止轮次（教师/管理员；一键停止负载线程 + 恢复故障态） */
  stopRound: (round_id: number) => http.post(`/sandbox/rounds/${round_id}/stop`) as Promise<any>,
  /** 本班轮次台账（教师/管理员） */
  rounds: (limit = 20) => http.get('/sandbox/rounds', { params: { limit } }) as Promise<any>,
  /** 轮次 KPI 明细（教师/管理员） */
  kpis: (round_id: number) => http.get(`/sandbox/rounds/${round_id}/kpis`) as Promise<any>,
  /** 本班进行中的轮次 + 实时 KPI + 故障态（全员） */
  activeRound: () => http.get('/sandbox/rounds/active') as Promise<any>,
  /** 提交处置动作（全员；action_type: restart_node/audit_replay/fix_redeploy/throttle_tx） */
  submitAction: (round_id: number, data: { action_type: string; description?: string }) =>
    http.post(`/sandbox/rounds/${round_id}/action`, data) as Promise<any>,
  /** 本班沙盘故障态（节点离线标记 / 共识暂停标记） */
  nodes: () => http.get('/sandbox/nodes') as Promise<any>,
}

/** 任务 #21：事件总线（SSE 推送）客户端封装 */
export { eventStream, onBusEvent, EVENT_TYPES } from './events'
export type { BusEventType, NotifyEventPayload } from './events'
