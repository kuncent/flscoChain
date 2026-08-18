import http from './http'

/** 跨专业综合实训平台 登录 */
export const authApi = {
  /** 明文密码 RSA 加密（用于账号密码登录） */
  encrypt: (pwd: string) => http.get('/auth/encrypt', { params: { pwd } }),
  /** 登录：账号密码（username + passwordEncode）或 智云 SSO（TOKEN） */
  login: (data: { username?: string; passwordEncode?: string; TOKEN?: string }) =>
    http.post('/auth/login', data),
  /** 单点登录 · 会话校验：仅校验当前是否保持登录态（不调用外部智云 SSO） */
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
}

export const chainApi = {
  status: () => http.get('/chain/status') as Promise<any>,
  tutorial: (wallet = 'default') => http.get('/chain/tutorial', { params: { wallet } }) as Promise<any>,
  execStep: (step: number, wallet = 'default') => http.post('/chain/tutorial/exec', { step, wallet }) as Promise<any>,
  progress: (wallet = 'default') => http.get('/chain/tutorial/progress', { params: { wallet } }) as Promise<any>,
  resetProgress: (wallet = 'default') => http.post('/chain/tutorial/progress/reset', { wallet }) as Promise<any>,
}

export const contractApi = {
  builtin: () => http.get('/contracts/builtin'),
  getBuiltin: (name: string) => http.get(`/contracts/builtin/${name}`),
  compile: (data: { name: string; source: string }) => http.post('/contracts/compile', data),
  deploy: (data: any) => http.post('/contracts/deploy', data),
  deployed: () => http.get('/contracts/deployed'),
  getDeployed: (addr: string) => http.get(`/contracts/deployed/${addr}`),
  call: (data: any) => http.post('/contracts/call', data),
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
  currentRole: (wallet: string) => http.get('/eco/role/current', { params: { wallet } }),
  contractStatus: () => http.get('/eco/contracts/status'),
  builtinContracts: () => http.get('/eco/contracts/builtin'),
  /** 一键编译 + 部署内置绿色合约 */
  deployContract: (name: string, deployer: string = '0xlearner') =>
    http.post('/eco/contracts/deploy', { name, deployer }),
  issueEnergy: (wallet: string, role_key: string) => http.post('/eco/energy/issue', { wallet, role_key }),
  energyRecords: (wallet?: string) => http.get('/eco/energy/records', { params: { wallet } }),
  energyBalance: (wallet: string) => http.get('/eco/energy/balance', { params: { wallet } }),
  trees: () => http.get('/eco/trees'),
  addTree: (data: any) => http.post('/eco/trees/add', data),
  exchangeCertificate: (wallet: string, species_id: number) => http.post('/eco/certificates/exchange', { wallet, species_id }),
  certificates: (owner?: string) => http.get('/eco/certificates/list', { params: { owner } }),
  exchangeBadge: (wallet: string, badge_type: string) => http.post('/eco/badges/exchange', { wallet, badge_type }),
  badges: (owner?: string) => http.get('/eco/badges/list', { params: { owner } }),
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
}
