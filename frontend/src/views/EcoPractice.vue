<template>
  <div class="eco dq-enter-up">
    <!-- 1. 顶部引导卡片：联盟治理与运营商业全景 -->
    <div class="dq-flow-card guide-card">
      <div class="dq-flow-card__inner">
        <div class="guide-head">
          <div class="guide-title">
            <span class="g-icon">🌿</span>
            绿色低碳联盟链 · 联盟治理与运营
            <span class="dq-tag dq-tag-lg">六节点共识 · 真实商业闭环</span>
            <span class="dq-live" style="margin-left: 6px"><span class="dot"></span>多合约协同</span>
          </div>
          <div class="guide-desc">
            以「绿色出行 + 碳减排」为业务背景，由 <b>6 个联盟节点</b>（管理员 / 地铁 / 公交 / 单车 / 外卖 / 回收）共同运营：
            各节点按业务规则向居民发放 <b>绿色能量（ERC20）</b>，居民凭能量兑换 <b>植树证书（ERC721）</b>、
            <b>生态勋章 / 骑行券（ERC1155）</b>，并可在绿色资产市场相互挂牌交易，形成「发放 → 累积 → 兑换 → 流通 → 回收」的能量闭环。
          </div>
        </div>

        <!-- 商业流程总览：5 步闭环 -->
        <div class="biz-flow">
          <div class="biz-step">
            <div class="bs-no">01</div>
            <div class="bs-info">
              <div class="bs-title">🛡️ 联盟链搭建</div>
              <div class="bs-desc">管理员部署 3 份合约（GreenEnergy / PlantCertificate / EcoBadge），完成联盟链初始化</div>
            </div>
          </div>
          <div class="biz-arrow">→</div>
          <div class="biz-step">
            <div class="bs-no">02</div>
            <div class="bs-info">
              <div class="bs-title">👥 联盟成员协同运营</div>
              <div class="bs-desc">6 节点各司其职：业务方按规则发放能量，管理员治理参数与树种上架</div>
            </div>
          </div>
          <div class="biz-arrow">→</div>
          <div class="biz-step">
            <div class="bs-no">03</div>
            <div class="bs-info">
              <div class="bs-title">⚡ 居民累积能量</div>
              <div class="bs-desc">居民通过地铁 / 公交 / 单车 / 外卖 / 回收等绿色行为累积链上能量余额</div>
            </div>
          </div>
          <div class="biz-arrow">→</div>
          <div class="biz-step">
            <div class="bs-no">04</div>
            <div class="bs-info">
              <div class="bs-title">🌱 资产兑换（能量回收）</div>
              <div class="bs-desc">消耗能量兑换植树证书 / 勋章 / 骑行券，能量回收到管理员国库（能量销毁机制）</div>
            </div>
          </div>
          <div class="biz-arrow">→</div>
          <div class="biz-step">
            <div class="bs-no">05</div>
            <div class="bs-info">
              <div class="bs-title">💱 资产市场流通</div>
              <div class="bs-desc">居民可在绿色资产市场挂牌出售 NFT 资产，其他居民用绿色能量购买，资产自由流通</div>
            </div>
          </div>
        </div>

        <!-- 四维度商业口径（谁发行 / 谁获取 / 谁兑换）不在本页另铺一套只读文案：
             下面的 7 张角色卡已按身份给出职能摘要与真实组织钱包。 -->
      </div>
    </div>

    <!-- 2. 合约部署状态区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">📜</span>
        合约部署状态
        <span class="role-sub">发行权已下沉到合约层：只有被加入合约 issuers 白名单的节点钱包才能 mint</span>
        <span class="dq-tag" :class="allDeployed ? '' : 'muted'" style="margin-left: auto">
          {{ deployedCount }} / 3 已部署
        </span>
      </div>
      <div class="contract-grid">
        <div
          v-for="c in contractList"
          :key="c.key"
          class="contract-card"
          :class="{ deployed: c.deployed, locked: !c.deployed }"
        >
          <div class="cc-head">
            <div class="cc-name">
              <span class="cc-icon">{{ c.deployed ? '✅' : '🔒' }}</span>
              {{ c.name }}
            </div>
            <span class="dq-tag" :class="c.tagClass">{{ c.standard }}</span>
          </div>
          <div class="cc-body">
            <template v-if="c.deployed">
              <div class="cc-addr-label">合约地址</div>
              <div class="dq-mono cc-addr" @click="copyAddr(c.address)">{{ short(c.address) }}</div>
            </template>
            <template v-else>
              <div class="cc-hint">🔒 未部署{{ canDeployContract ? '，点击下方按钮一键编译并部署到链上' : '（联盟内置合约部署属治理职能）' }}</div>
              <el-button
                v-if="canDeployContract"
                size="small"
                type="primary"
                :loading="deployingKey === c.key"
                @click="deployContract(c.key)"
              >
                <span v-if="deployingKey === c.key">编译部署中…</span>
                <span v-else>🚀 一键编译部署</span>
              </el-button>
              <div v-else class="dq-tag muted" style="margin-top: 6px">{{ denyTip(CAP.deploy) }}</div>
            </template>
          </div>
        </div>
      </div>
      <div v-if="allDeployed" class="eco-active dq-tip">
        <span class="dt-label">✨ 生态系统已激活</span>
        三份合约均已部署，可进行角色选择与能量 / 资产操作。
      </div>
    </div>

    <!-- 3. 角色选择区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">👥</span>
        选择你的角色
        <span class="role-sub">7 个身份一排：点卡片即以该身份的**真实链上钱包**操作，顶栏「当前操作钱包」、页面身份标签与业务项三处同步跟随</span>
        <span class="dq-tag" :class="`p-${identityProfile}`" style="margin-left: auto">
          当前身份：{{ identityIcon }} {{ identityName }}
        </span>
      </div>
      <div class="role-grid">
        <!-- 7 个身份同排：6 个联盟节点 + 普通用户；每张卡槽位数与高度一致，排版不被文案撑破 -->
        <div
          v-for="r in roleList"
          :key="r.key"
          class="role-card"
          :class="{ active: isRoleActive(r.key), operating: isOperatingWith(r.address) }"
          @click="selectRole(r.key)"
        >
          <div class="rc-head">
            <span class="rc-icon" :style="{ background: r.color + '1f', borderColor: r.color + '55', color: r.color }">{{ r.icon }}</span>
            <div class="rc-id">
              <div class="rc-name" :title="r.name">{{ r.name }}</div>
              <div class="rc-profile">{{ profileLabel(r.profile) }}</div>
            </div>
          </div>
          <div class="rc-state">
            <span v-if="isOperatingWith(r.address)" class="dq-tag accent tiny">操作中</span>
            <span v-else-if="isRoleActive(r.key)" class="dq-tag tiny">已选角色</span>
            <span v-else class="dq-tag tiny muted">未选用</span>
            <el-button
              class="rc-play" size="small" link
              title="不切钱包，仅以本人钱包扮演该角色（后端会另存操作人痕迹）"
              @click.stop="selectRole(r.key, true)"
            >扮演</el-button>
          </div>
          <div class="rc-desc" :title="r.desc">{{ r.desc }}</div>
          <div class="rc-wallet">
            <div class="rw-line">
              <span class="rw-k">组织钱包</span>
              <span v-if="r.alias" class="rw-alias" :title="'密钥库别名（仅展示）：' + r.alias">{{ r.alias }}</span>
            </div>
            <span
              class="rw-v dq-mono"
              :class="{ link: !!r.address }"
              :title="r.address || '后端未返回该机构地址（钱包服务未就绪）'"
              @click.stop="r.address && copyAddr(r.address)"
            >{{ r.address ? shortAddr(r.address) : '地址未就绪' }}</span>
          </div>
          <div class="rc-dims" :title="'职能：' + dimTags(r).join(' / ')">
            {{ dimsBrief(dimTags(r)) || '仅联盟治理职能' }}
          </div>
          <div class="rc-rule" :title="ruleText(r.key)">{{ ruleText(r.key) }}</div>
          <div class="rc-quota">
            <template v-if="r.quotaView">
              <div class="rq-line">
                <span>发行授信</span>
                <b :class="{ danger: r.quotaView.exhausted }">{{ r.quotaView.used }} / {{ r.quotaView.quota }}</b>
              </div>
              <div class="dq-progress dq-progress--sm">
                <div
                  class="dq-progress__bar"
                  :class="{ danger: r.quotaView.exhausted }"
                  :style="{ width: r.quotaView.pct + '%' }"
                ></div>
              </div>
            </template>
            <div v-else class="rq-line dim"><span>发行授信</span><b>不适用</b></div>
          </div>
          <div class="rc-foot" @click.stop>
            <el-button
              size="small"
              :type="isOperatingWith(r.address) ? 'success' : 'primary'"
              :plain="!isOperatingWith(r.address)"
              @click="selectRole(r.key)"
            >
              {{ isOperatingWith(r.address) ? '✓ 正以此钱包操作' : '以此钱包操作' }}
            </el-button>
          </div>
        </div>

        <!-- 第 7 张：普通用户（低碳居民）——非联盟发放角色，绑定登录账号本人链上地址 -->
        <div
          class="role-card role-resident"
          :class="{ active: residentActive, operating: residentOperating }"
          @click="selectResident"
        >
          <div class="rc-head">
            <span class="rc-icon rr-icon">👨‍🎓</span>
            <div class="rc-id">
              <div class="rc-name" title="普通用户（低碳居民）">普通用户</div>
              <div class="rc-profile">{{ profileLabel('resident') }}</div>
            </div>
          </div>
          <div class="rc-state">
            <span v-if="residentOperating" class="dq-tag accent tiny">操作中</span>
            <span v-else-if="residentActive" class="dq-tag tiny">当前身份</span>
            <span v-else class="dq-tag tiny muted">未选用</span>
          </div>
          <div class="rc-desc" :title="ROLE_META_RESIDENT_DESC">{{ ROLE_META_RESIDENT_DESC }}</div>
          <div class="rc-wallet">
            <div class="rw-line"><span class="rw-k">我的钱包</span></div>
            <span
              class="rw-v dq-mono" :class="{ link: !!myWalletAddr }"
              :title="myWalletAddr || '登录态缺失：请重新登录以获取本人链上地址'"
              @click.stop="myWalletAddr && copyAddr(myWalletAddr)"
            >{{ myWalletAddr ? shortAddr(myWalletAddr) : '未登录 / 地址未就绪' }}</span>
          </div>
          <div class="rc-dims" :title="'职能：' + residentDims.join(' / ')">{{ dimsBrief(residentDims) }}</div>
          <div class="rc-rule" :title="residentActive ? '✓ 当前操作身份' : '切回本人钱包并清除已选联盟角色'">
            {{ residentActive ? '✓ 当前操作身份' : '切回本人钱包并清除已选联盟角色' }}
          </div>
          <div class="rc-quota">
            <div class="rq-line dim"><span>发行授信</span><b>不适用</b></div>
          </div>
          <div class="rc-foot" @click.stop>
            <el-button size="small" :type="residentOperating ? 'success' : 'primary'" :plain="!residentOperating" @click="selectResident">
              {{ residentOperating ? '✓ 正以此钱包操作' : '以我的钱包操作' }}
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 3.5 角色工作台：职责 / 能力位 / 链上活动统计 / 待办运营动作 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">🧰</span>
        角色工作台
        <span v-if="currentRole?.role_key" class="dq-tag" style="margin-left: auto">
          {{ roleMeta(currentRole.role_key)?.icon }} {{ roleMeta(currentRole.role_key)?.name }}
        </span>
        <el-button
          v-if="currentRole?.role_key"
          size="small"
          :loading="wbLoading"
          style="margin-left: 8px"
          @click="loadWorkbench"
        >刷新</el-button>
      </div>
      <div v-if="!currentRole?.role_key" class="empty-tip">
        {{ residentActive
          ? '当前身份为普通用户（无联盟工作台），如需体验联盟节点职责，请选择上方 6 个联盟角色之一'
          : '请先在上方选择一个角色，工作台将展示该角色的职责、权限位与链上活动统计' }}
      </div>
      <el-collapse v-else v-model="wbActive" class="wb-collapse">
        <el-collapse-item name="wb">
          <template #title>
            <span class="wb-title">联盟节点职责 · 权限位 · 链上活动 · 待办运营动作</span>
          </template>

          <div v-if="!workbench && !wbLoading" class="empty-tip small">
            工作台数据加载失败，点击右上角「刷新」重试
          </div>
          <template v-else-if="workbench">
            <!-- 职责 + 权限位 -->
            <div class="wb-head">
              <div class="wb-desc">{{ workbench.role?.desc }}</div>
              <div class="wb-perms">
                <span v-if="workbench.permissions?.has_energy_rule" class="dq-tag accent">⚡ 能量发放节点</span>
                <span v-if="workbench.permissions?.can_issue_badge" class="dq-tag warn">🎖️ 可发放勋章</span>
                <span v-if="workbench.permissions?.can_issue_voucher" class="dq-tag info">🎫 可发放骑行券</span>
                <span v-if="workbench.permissions?.can_manage_trees" class="dq-tag">🌳 可管理树种</span>
              </div>
            </div>

            <!-- 角色钱包链上活动统计 -->
            <div class="wb-stats">
              <div class="dq-card wb-stat">
                <div class="ws-label">合约调用（本角色钱包）</div>
                <div class="ws-num">{{ workbench.activity?.contract_calls?.total ?? 0 }}</div>
                <div class="ws-sub">
                  成功 {{ workbench.activity?.contract_calls?.success ?? 0 }} ·
                  失败 {{ workbench.activity?.contract_calls?.failed ?? 0 }}
                </div>
              </div>
              <div class="dq-card wb-stat">
                <div class="ws-label">链上交易（收 / 发）</div>
                <div class="ws-num">{{ workbench.activity?.transactions?.total ?? 0 }}</div>
                <div class="ws-sub">
                  发出 {{ workbench.activity?.transactions?.sent ?? 0 }} ·
                  接收 {{ workbench.activity?.transactions?.received ?? 0 }}
                </div>
              </div>
              <div class="dq-card wb-stat">
                <div class="ws-label">绿色能量发放（本角色）</div>
                <div class="ws-num">{{ workbench.activity?.energy?.issue_count ?? 0 }}<em> 次</em></div>
                <div class="ws-sub">累计 {{ workbench.activity?.energy?.total_points ?? 0 }} 点能量</div>
              </div>
            </div>

            <!-- 待办运营动作（由权限位静态推导） -->
            <div class="wb-todos">
              <div class="dq-card-title sub-title">待办运营动作</div>
              <div class="wb-todo" v-for="t in workbench.todos || []" :key="t.key">
                <span class="wt-dot"></span>
                <div class="wt-body">
                  <div class="wt-title">{{ t.title }}</div>
                  <div class="wt-desc">{{ t.desc }}</div>
                </div>
                <span class="dq-tag muted">{{ t.source }}</span>
              </div>
              <div v-if="!(workbench.todos || []).length" class="empty-tip small">
                该角色暂无静态映射的待办动作
              </div>
            </div>
          </template>
          <div v-else class="empty-tip small">工作台数据加载中…</div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 4. 绿色能量：居民获取 / 节点发行 / 管理员治理（按能力位分派，只呈现本人职能） -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">⚡</span>
        {{ canIssueEnergy ? '绿色能量发行（本节点）' : canReceiveEnergy ? '绿色能量获取' : '绿色能量治理' }}
        <span class="dq-live" style="margin-left: auto"><span class="dot"></span>ERC20 mint</span>
      </div>
      <!-- ① 居民（能量接收方）：提交低碳行为凭证，由对应节点审核以其组织钱包上链发行 -->
      <div v-if="canReceiveEnergy" class="resident-energy">
          <div class="dq-note">
            <span class="dn-label">能量获取方式</span>
            普通用户（居民）通过 <b>5 种低碳行为</b>获取绿色能量：选择行为并提交对应业务凭证，
            由对应联盟节点自动审核（阈值校验）后以其组织钱包上链发放——这正是联盟角色的意义：
            <b>只有业务节点拥有能量发行权</b>，居民不能自铸。能量入账本人钱包，可用于兑换证书 / 勋章 / 骑行券与市场交易。
          </div>
          <div class="energy-ways">
            <div v-for="r in energyWayRoles" :key="r.key" class="energy-way-card">
              <div class="ew-head">
                <span class="ew-icon">{{ r.icon }}</span>
                <span class="ew-name">{{ r.name }}</span>
                <span class="ew-points dq-mono">+{{ pointsHint(r.energy_rule) }}</span>
              </div>
              <div class="ew-desc">{{ r.desc }}</div>
              <div class="ew-threshold dq-mono">{{ r.energy_rule.proof_field }} ≥ {{ r.energy_rule.min }} {{ r.energy_rule.unit }}</div>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="issuing && issuingRoleKey === r.key"
                @click="openProofDlg(r.key)"
              >
                提交{{ r.energy_rule.action }}凭证
              </el-button>
            </div>
          </div>
      </div>
      <!-- ② 业务节点（能量发行方）：节点只出规则与授信，不提供手动发放入口 -->
      <template v-else-if="canIssueEnergy">
        <div class="energy-ops">
          <div class="energy-info">
            发行主体：<b>{{ roleMeta(currentRole?.role_key)?.icon }} {{ roleMeta(currentRole?.role_key)?.name }}</b>
            <span class="dq-tag accent" style="margin-left: 8px">{{ pointsHint(activeIssueRole?.energy_rule || {}) }}</span>
            <span v-if="energyQuotaText" class="dq-tag" :class="quotaExhausted ? 'warn' : 'info'" style="margin-left: 6px">{{ energyQuotaText }}</span>
          </div>
          <span class="dq-tag muted">无手动发放入口</span>
        </div>
        <div class="dq-note">
          <span class="dn-label">发行链路（单向）</span>
          绿色能量<b>只能因真实低碳行为而产生</b>：普通用户在对应行为渠道提交业务凭证（里程 / 时长 / 称重），
          系统按本节点规则完成阈值与单次封顶核算后，以<b>本节点组织钱包</b>上链发行并入账到该居民钱包。
          节点侧不提供「手动发能量」按钮——发行方自铸等于无限印钞，后端一律硬拦；同一业务单号不重复发放，
          累计发行不得超过联盟授予本节点的信用额度（用尽后居民提交会被拒，需申请上调额度）。
          想亲自体验领取能量：回到上方「选择你的角色」点【普通用户】（会切回我的钱包并清除已选角色），
          再从 5 个行为渠道提交凭证。
        </div>
      </template>
      <!-- ③ 治理身份（管理员）：既不发行也不接收，只负责国库与额度 -->
      <div v-else class="dq-note">
        <span class="dn-label">联盟治理身份</span>
        管理员（国库账户）<b>既不是能量发行方也不是接收方</b>，只承担三项治理职能：
        ① <b>树种与 ERC721 发行额度</b>（下方上架树种、上调项目额度）；
        ② <b>能量国库与销毁</b>（居民兑换回收的能量进入国库，销毁后永久退出流通，防通胀）；
        ③ <b>联盟内置合约部署</b>。如需体验能量发行请切换到业务节点身份，体验获取请切回普通用户。
      </div>

      <!-- 能量台账：同一张 eco_energy_records 的两个视角 —— 节点看「我发给了谁」，居民看「我从哪来」 -->
      <template v-if="canIssueEnergy || canReceiveEnergy">
        <div class="dq-card-title sub-title rec-head">
          <span>{{ recordsView === 'issuer' ? '本节点发行列表' : '我的能量获取列表' }}</span>
          <span class="dq-tag tiny">{{ recordsView === 'issuer' ? '普通用户向本节点获取能量的逐笔明细' : '按获取渠道逐笔' }}</span>
          <span class="dq-tag tiny">
            {{ energyTotalCount > energyRecords.length
              ? `最近 ${energyRecords.length} 笔 / 共 ${energyTotalCount} 笔`
              : `共 ${energyTotalCount} 笔` }}
          </span>
          <span class="dq-tag accent tiny">累计 {{ recordsView === 'issuer' ? '发行' : '获取' }} {{ energyTotalPoints }} 能量</span>
          <span
            v-if="recordsView === 'issuer' && energyQuotaText"
            class="dq-tag tiny"
            :class="quotaExhausted ? 'warn' : 'info'"
          >{{ energyQuotaText }}</span>
        </div>
        <el-table :data="energyRecords" border size="small" v-if="energyRecords.length">
          <el-table-column :label="recordsView === 'issuer' ? '获取用户（居民钱包）' : '获取渠道'" min-width="150">
            <template #default="{ row }">
              <span
                v-if="recordsView === 'issuer'"
                class="dq-mono dim"
                :title="'能量已入账到该居民钱包：' + (row.receiver_wallet || '')"
              >{{ row.receiver_wallet ? shortAddr(row.receiver_wallet) : '-' }}</span>
              <span v-else>{{ roleMeta(row.role_key)?.icon }} {{ roleMeta(row.role_key)?.name || row.role_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="action" label="低碳行为" min-width="120">
            <template #default="{ row }">{{ row.action }}</template>
          </el-table-column>
          <el-table-column prop="proof_no" label="业务单号" min-width="140">
            <template #default="{ row }"><span class="dq-mono">{{ row.proof_no || '-' }}</span></template>
          </el-table-column>
          <el-table-column prop="points" label="能量" width="100">
            <template #default="{ row }"><span class="dq-mono energy-val">+{{ row.points }}</span></template>
          </el-table-column>
          <el-table-column prop="tx_hash" label="交易哈希" min-width="180">
            <template #default="{ row }"><span class="dq-mono dim">{{ row.tx_hash ? short(row.tx_hash) : '-' }}</span></template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-tip">
          {{ recordsView === 'issuer'
            ? '本节点还没有发行记录：居民提交该业务的低碳凭证、达到门槛后在此逐笔展示'
            : '还没有能量入账：从上方 5 个渠道任选一个提交低碳行为凭证，由对应节点审核后发放' }}
        </div>
      </template>
    </div>

    <!-- 4.5 能量国库与通胀审计：仅联盟治理身份可见（管理员 / 未切角色的教师平台账号） -->
    <div class="dq-card section-card" v-if="treasury && canViewTreasury">
      <div class="dq-card-title">
        <span class="title-icon">🏦</span>
        能量国库与通胀审计
        <span class="dq-tag" :class="treasury.inflation_audit?.conserved ? 'accent' : 'warn'" style="margin-left: auto">
          {{ treasury.inflation_audit?.conserved ? '✅ 账本守恒' : `⚠️ 账本不平（差 ${treasury.inflation_audit?.diff}）` }}
        </span>
      </div>
      <div class="dq-tip" style="margin-bottom: 10px">
        <span class="dt-label">口径:</span>
        居民兑换时能量全额转入国库账户 <span class="dq-mono" :title="treasury.treasury_wallet">{{ shortAddr(treasury.treasury_wallet) }}</span>；
        停留在国库只是「退出个人持有」，<b>只有销毁（burn）才会下降链上总供应量</b>，因此已回收未销毁 = 潜在通胀敞口。
      </div>
      <div class="tr-grid">
        <div class="tr-cell">
          <div class="tr-label">累计发行（含国库投放）</div>
          <div class="tr-num dq-mono">{{ treasury.total_issued }}</div>
        </div>
        <div class="tr-cell">
          <div class="tr-label">净发行量 = 链上总供应</div>
          <div class="tr-num dq-mono">{{ treasury.net_issuance }}</div>
        </div>
        <div class="tr-cell">
          <div class="tr-label">居民侧在途流通</div>
          <div class="tr-num dq-mono">{{ treasury.circulating }}</div>
        </div>
        <div class="tr-cell">
          <div class="tr-label">国库已回收</div>
          <div class="tr-num dq-mono">{{ treasury.total_recycled }}</div>
        </div>
        <div class="tr-cell">
          <div class="tr-label">已销毁退出流通</div>
          <div class="tr-num dq-mono">{{ treasury.total_burned }}</div>
          <div class="tr-sub">销毁率 {{ treasury.burn_rate }}%</div>
        </div>
        <div class="tr-cell">
          <div class="tr-label">待销毁敞口</div>
          <div class="tr-num dq-mono" :class="{ warn: treasury.pending_burn > 0 }">{{ treasury.pending_burn }}</div>
          <div class="tr-sub">可销毁上限 {{ treasury.pending_burn_cap }}</div>
        </div>
      </div>

      <div class="dq-card-title sub-title" style="margin-top: 14px">节点发行授信（防单点超发）</div>
      <div class="quota-list">
        <div class="quota-row" v-for="q in treasury.node_quotas || []" :key="q.role_key">
          <span class="qr-name">{{ q.icon }} {{ q.role_name }}</span>
          <span class="qr-wallet dq-mono dim" :title="q.wallet">{{ shortAddr(q.wallet) }}</span>
          <el-progress
            v-if="q.quota > 0"
            class="qr-bar"
            :percentage="Math.min(100, Number(q.used_ratio || 0))"
            :status="Number(q.used_ratio || 0) >= 100 ? 'exception' : Number(q.used_ratio || 0) >= 80 ? 'warning' : 'success'"
          />
          <span v-else class="dq-tag muted">未设上限</span>
          <span class="qr-num dq-mono">{{ q.used }} / {{ q.quota > 0 ? q.quota : '-' }}</span>
        </div>
      </div>

      <!-- 国库销毁：仅 can_burn（管理员 + 教师/平台账号）可提交 -->
      <div class="burn-box" v-if="canTreasuryOps">
        <div class="dq-card-title sub-title">国库能量销毁（不可逆）</div>
        <el-form :inline="true" size="small">
          <el-form-item label="销毁数量">
            <el-input-number v-model="burnForm.amount" :min="1" :max="treasury.pending_burn_cap || 1" style="width: 130px" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="burnForm.note" placeholder="如：2026 年度一期回收能量销毁" style="width: 220px" />
          </el-form-item>
          <el-form-item>
            <el-button type="danger" :loading="burning" :disabled="!treasury.pending_burn_cap" @click="submitBurn">
              🔥 销毁能量
            </el-button>
          </el-form-item>
        </el-form>
        <div class="dq-tip" v-if="!treasury.pending_burn_cap">
          <span class="dt-label">提示:</span>当前无已回收能量可销毁（居民兑换回收后才会产生国库流水）。
        </div>

        <!-- 账本 → 链上能量对账：本地沙盒链（进程内内存链）每次重启后合约余额全清零，
             而能量台账持久在库，不补齐就会出现「本页有能量、钱包页 0、兑换报链上余额不足」。
             后端启动时已自动对一次，本按钮供管理员当场手执（幂等，已一致的钱包不发交易）。 -->
        <el-form :inline="true" size="small" style="margin-top:2px">
          <el-form-item>
            <el-button :loading="reconciling" @click="reconcileChainEnergy">
              🔁 按能量台账补齐链上余额
            </el-button>
          </el-form-item>
          <el-form-item v-if="reconcileNote">
            <span class="dim">{{ reconcileNote }}</span>
          </el-form-item>
        </el-form>
      </div>

      <div class="dq-card-title sub-title" style="margin-top: 14px">销毁台账（最近 {{ (treasury.burns || []).length }} 笔）</div>
      <el-table :data="treasury.burns || []" border size="small" v-if="(treasury.burns || []).length">
        <el-table-column prop="amount" label="销毁量" width="100">
          <template #default="{ row }"><span class="dq-mono burn-val">-{{ row.amount }}</span></template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" min-width="140">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.operator) }}</span></template>
        </el-table-column>
        <el-table-column prop="tx_hash" label="交易哈希" min-width="180">
          <template #default="{ row }"><span class="dq-mono dim">{{ row.tx_hash ? short(row.tx_hash) : '-' }}</span></template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-tip small">暂无销毁记录</div>
    </div>

    <!-- 4.6 能量流水账本：余额的唯一事实源（发行 / 兑换回收 / 市场转让 / 销毁） -->
    <div class="dq-card section-card" v-if="energyFlows.length">
      <div class="dq-card-title">
        <span class="title-icon">🧾</span>
        能量流水账本
        <span class="dq-tag" style="margin-left: 8px">流水净额 {{ flowBalance }}</span>
        <span class="dq-tag muted" style="margin-left: 6px">与链上余额对账一致</span>
      </div>
      <el-table :data="energyFlows" border size="small">
        <el-table-column prop="kind_label" label="事件" width="130">
          <template #default="{ row }"><span class="dq-tag" :class="row.amount >= 0 ? 'accent' : 'warn'">{{ row.kind_label }}</span></template>
        </el-table-column>
        <el-table-column prop="amount" label="变动" width="100">
          <template #default="{ row }">
            <span class="dq-mono" :class="row.amount >= 0 ? 'energy-val' : 'burn-val'">{{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role_key" label="相关方" width="120">
          <template #default="{ row }">{{ row.role_key ? (roleMeta(row.role_key)?.icon || '') + ' ' + (roleMeta(row.role_key)?.name || row.role_key) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="200" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 5. 植树证书区：治理方（签发 / 目录额度）与居民（兑换 / 持有）两套视图，只发能量的节点不看到这张卡 -->
    <div class="dq-card section-card" v-if="showTreeCard">
      <div class="dq-card-title">
        <span class="title-icon">🌳</span>
        {{ canManageCatalog ? '植树证书发行与目录治理 (ERC721)' : '植树证书兑换与持有 (ERC721)' }}
        <span class="dq-tag" style="margin-left: auto">{{ canManageCatalog ? '本机构签发' : '能量 → 证书' }}</span>
      </div>
      <div class="dq-card-title sub-title" style="margin-top: 2px">
        发行形态：非同质化 ERC721 · 一证一树 · 每个树种有项目发行额度，额满即售罄
      </div>
      <div class="tree-layout">
        <!-- 治理区：上架树种（仅具备「目录治理」职能的管理员身份） -->
        <div class="dq-card tree-admin" v-if="canManageCatalog">
          <div class="dq-card-title sub-title">上架树种（联盟治理）</div>
          <el-form label-width="100px" size="small">
            <el-form-item label="树种名称">
              <el-input v-model="treeForm.name" placeholder="如：银杏树" />
            </el-form-item>
            <el-form-item label="所需能量">
              <el-input-number v-model="treeForm.required_energy" :min="1000" :step="100" />
            </el-form-item>
            <el-form-item label="发行额度">
              <el-input-number v-model="treeForm.supply" :min="0" :step="50" />
              <div class="dq-tip" style="margin-top:4px">
                <span class="dt-label">ERC721:</span>可签发的证书份数（一证一树），额满自动售罄；0 = 不限额（仅存量兼容）
              </div>
            </el-form-item>
            <el-form-item label="图片地址">
              <el-input v-model="treeForm.image_url" placeholder="https://... （选填，证书图片）" />
              <div class="dq-tip" style="margin-top:4px">
                <span class="dt-label">说明:</span>可为树种配置证书图片（https 图片地址），留空则使用默认图标 🌳
              </div>
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="treeForm.description" type="textarea" :rows="2" placeholder="树种寓意或碳汇说明" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="addingTree" @click="addTree">添加树种</el-button>
            </el-form-item>
          </el-form>
          <div class="dq-tip"><span class="dt-label">说明:</span>所需能量最低 1000；已签发证书不可变，发行额度只可上调不可下调。</div>
        </div>

        <!-- 树种列表 -->
        <div class="dq-card tree-list">
          <div class="dq-card-title sub-title">
            树种目录（公开只读）
            <span v-if="canManageCatalog" class="dq-tag info" style="margin-left: 8px">治理视角：签发方 = 本机构，持有方 = 兑换的居民</span>
            <span v-else-if="!canExchange" class="dq-tag muted" style="margin-left: 8px">{{ denyTip(CAP.exchange) }}</span>
          </div>
          <div class="tree-grid" v-if="trees.length">
            <div class="dq-card tree-item" v-for="t in trees" :key="t.id">
              <img v-if="t.image_url" class="ti-img" :src="t.image_url" :alt="t.name" @error="t.image_url = ''" />
              <div v-else class="ti-emoji">🌳</div>
              <div class="ti-name">{{ t.name }}</div>
              <div class="ti-desc">{{ t.description || '暂无描述' }}</div>
              <div class="ti-cost">所需能量：<span class="dq-mono">{{ t.required_energy }}</span></div>
              <div class="ti-quota dq-mono">
                发行额度：
                <span v-if="t.remaining < 0">不限额</span>
                <span v-else>{{ t.issued }} / {{ t.supply }}，剩余 {{ t.remaining }}</span>
                <span v-if="t.sold_out" class="dq-tag warn">已售罄</span>
                <span v-else-if="t.status === 'off'" class="dq-tag muted">已下架</span>
              </div>
              <el-button
                v-if="canExchange"
                size="small"
                type="primary"
                :disabled="t.sold_out || t.status === 'off' || energyShort(t.required_energy)"
                :loading="exchangingTree === t.id"
                @click="exchangeCertificate(t.id)"
                style="margin-top: 8px; width: 100%"
              >
                {{ treeBtnText(t) }}
              </el-button>
              <!-- 治理：上调发行额度 / 上下架（仅目录治理职能） -->
              <div v-if="canManageCatalog" class="ti-gov">
                <el-button size="small" text type="primary" @click="raiseTreeSupply(t)">上调额度</el-button>
                <el-button
                  size="small" text
                  :type="t.status === 'off' ? 'success' : 'warning'"
                  @click="toggleTreeStatus(t)"
                >{{ t.status === 'off' ? '重新上架' : '下架' }}</el-button>
              </div>
            </div>
          </div>
          <div v-else class="empty-tip">暂无树种，{{ canManageCatalog ? '请在左侧上架' : '请等待管理员上架' }}</div>
        </div>
      </div>

      <!-- 持有视图（居民）：兑换来的证书可挂牌；治理身份不持有证书，只看待签发进度 -->
      <template v-if="canExchange">
        <div class="dq-card-title sub-title" style="margin-top: 16px">
          我持有的植树证书
          <span class="dq-tag tiny">ERC721 · 一证一树不可拆挂</span>
          <el-button v-if="canTrade" size="small" type="success" plain style="margin-left: 12px" @click="$router.push('/nft?tab=green')">
            📈 前往资产市场
          </el-button>
        </div>
        <div class="cert-grid" v-if="certificates.length">
          <div class="dq-card cert-item" v-for="c in certificates" :key="c.token_id">
            <img v-if="treeImageOf(c.species_name)" class="ci-img" :src="treeImageOf(c.species_name)" :alt="c.species_name" />
            <div v-else class="ci-badge">🌱</div>
            <div class="ci-name">{{ c.species_name || c.name || '植树证书' }}</div>
            <div class="ci-meta">
              <div>Token ID: <span class="dq-mono">{{ c.token_id }}</span></div>
              <div class="dq-mono dim owner">持有者：{{ short(c.owner) }}</div>
            </div>
            <span class="dq-tag accent">ERC721</span>
            <div class="ci-ops" v-if="String(c.owner).toLowerCase() === String(wallet).toLowerCase()">
              <el-button
                v-if="!isListed('certificate', Number(c.id))"
                size="small"
                type="primary"
                plain
                :disabled="!canTrade"
                :title="canTrade ? '' : denyTip(CAP.market)"
                :loading="listingId === `cert_${c.id}`"
                @click.stop="openListDlg('certificate', Number(c.id), c.species_name || c.name || '植树证书', 1)"
              >
                💰 挂牌出售
              </el-button>
              <template v-else>
                <span class="dq-tag info">📍 在售中</span>
                <el-button size="small" type="danger" plain @click.stop="cancelListing(activeListing('certificate', Number(c.id))?.id)">下架</el-button>
              </template>
            </div>
          </div>
        </div>
        <div v-else class="empty-tip">暂无植树证书，用上方能量兑换树种后即在此展示</div>
      </template>
      <div v-else class="dq-tip" style="margin-top: 14px">
        <span class="dt-label">签发口径:</span>
        证书由本机构（联盟治理方）在链上签发，兑换后归属居民钱包，因此本钱包不持有证书；
        目录 {{ trees.length }} 种 · 本机构累计已签发 <b class="dq-mono">{{ certIssuedTotal }}</b> 份（一证一树），
        各树种的「发行额度 issued / supply」即签发进度，额满自动售罄。
      </div>
    </div>

    <!-- 6. 勋章与骑行券区：居民按能量兑换，发行节点按类型治理与发放（一张卡两套业务） -->
    <div class="dq-card section-card" v-if="showBadgeCard">
      <div class="dq-card-title">
        <span class="title-icon">🎖️</span>
        {{ canExchange ? '勋章与骑行券兑换 (ERC1155)' : '我发行的勋章与骑行券 (ERC1155)' }}
        <span class="dq-tag" style="margin-left: auto">{{ canExchange ? badgeTypes.length : myIssuedTypes.length }} 种类型</span>
      </div>
      <div class="dq-card-title sub-title" style="margin-top: 2px">
        {{ canExchange
          ? 'ERC1155 半同质化：同一类型可持有 N 份，消耗绿色能量按份兑换（已铸 minted 额满即售罄）'
          : 'ERC1155 半同质化：类型由本节点维护（谁发行、谁铸造、谁兑付），发行数量 = 类型上限 supply，上限只可上调' }}
      </div>
      <!-- 居民：兑换网格（发行方不能买自己发行的资产，故不给节点看） -->
      <div class="badge-grid" v-if="canExchange">
        <div class="dq-card badge-card" v-for="bt in badgeTypes" :key="bt.id">
          <img v-if="bt.image_url" class="bc-img" :src="bt.image_url" :alt="bt.name" @error="bt.image_url = ''" />
          <div v-else class="bc-icon">{{ bt.icon || (bt.badge_type === 'voucher' ? '🎫' : '🏅') }}</div>
          <div class="bc-name">{{ bt.name }}</div>
          <div class="bc-desc">{{ bt.desc || '绿色生活荣誉资产' }}</div>
          <div class="bc-meta">
            <span>单价 <span class="dq-mono">{{ bt.cost_energy }}</span> 能量/份</span>
            <span>已铸 <span class="dq-mono">{{ bt.minted }}</span>/{{ bt.supply }}</span>
          </div>
          <div class="bc-issuer dq-mono">
            发行方：{{ bt.issuer_role ? (roleMeta(bt.issuer_role)?.icon || '') + ' ' + (roleMeta(bt.issuer_role)?.name || bt.issuer_role) : '联盟碳汇方' }}
          </div>
          <div class="bc-qty">
            <span class="bq-label">兑换份数</span>
            <el-input-number
              size="small"
              :min="1"
              :max="badgeMaxQty(bt)"
              :model-value="qtyOf(bt)"
              @update:model-value="(v: number) => (badgeQty[String(bt.id)] = Math.max(1, Number(v) || 1))"
            />
            <span class="bq-cost dq-mono">计 {{ bt.cost_energy * qtyOf(bt) }} 能量</span>
          </div>
          <el-button
            type="primary"
            :disabled="bt.minted >= bt.supply || energyShort(bt.cost_energy * qtyOf(bt))"
            :loading="exchangingBadge === String(bt.id)"
            @click="exchangeBadgeType(bt)"
          >
            {{ badgeBtnText(bt) }}
          </el-button>
        </div>
      </div>
      <!-- 发行节点：本节点维护的类型清单（不是商品目录，而是自己的发行台账） -->
      <template v-else-if="canMintBadge">
        <el-table :data="myIssuedTypes" border size="small" v-if="myIssuedTypes.length">
          <el-table-column prop="name" label="资产名称" min-width="160">
            <template #default="{ row }">{{ row.icon || (row.badge_type === 'voucher' ? '🎫' : '🏅') }} {{ row.name }}</template>
          </el-table-column>
          <el-table-column prop="badge_type" label="形态" width="120">
            <template #default="{ row }">{{ row.badge_type === 'voucher' ? '骑行券' : '生态勋章' }}</template>
          </el-table-column>
          <el-table-column prop="cost_energy" label="居民兑换单价" width="120">
            <template #default="{ row }"><span class="dq-mono">{{ row.cost_energy }} 能量/份</span></template>
          </el-table-column>
          <el-table-column label="已铸 / 上限" width="140">
            <template #default="{ row }"><span class="dq-mono">{{ row.minted }} / {{ row.supply }}</span></template>
          </el-table-column>
          <el-table-column label="剩余可铸" width="110">
            <template #default="{ row }"><span class="dq-mono">{{ Math.max(Number(row.supply || 0) - Number(row.minted || 0), 0) }}</span></template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <span class="dq-tag" :class="Number(row.minted || 0) >= Number(row.supply || 0) ? 'warn' : 'accent'">
                {{ Number(row.minted || 0) >= Number(row.supply || 0) ? '已售罄' : '发行中' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-tip">
          本节点还没有维护任何{{ issuableForms.length ? issuableForms.join(' / ') : '资产' }}类型：请在下方「新增勋章类型」建立发行目录
        </div>
      </template>

      <!-- 联盟角色：新增勋章 / 骑行券类型 -->
      <div class="dq-card badge-admin" v-if="canAddBadgeTypes">
        <div class="dq-card-title sub-title">
          新增勋章类型（联盟角色）
          <span class="dq-tag info" style="margin-left: 8px">{{ currentRole?.role?.icon }} {{ currentRole?.role?.name }}</span>
        </div>
        <el-form :inline="true" size="small">
          <el-form-item v-if="canIssueBadgeCap && canIssueVoucherCap" label="资产类型">
            <el-radio-group v-model="badgeTypeForm.badge_type">
              <el-radio-button label="badge">生态勋章</el-radio-button>
              <el-radio-button label="voucher">骑行券</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="badgeTypeForm.badge_type === 'voucher' ? '骑行券名称' : '名称'">
            <el-input v-model="badgeTypeForm.name" :placeholder="badgeTypeForm.badge_type === 'voucher' ? '如：绿色骑行券' : '如：城市守护者'" style="width: 150px" />
          </el-form-item>
          <el-form-item label="图标">
            <el-input v-model="badgeTypeForm.icon" placeholder="emoji，如 🏅" style="width: 120px" />
          </el-form-item>
          <el-form-item label="消耗能量">
            <el-input-number v-model="badgeTypeForm.cost_energy" :min="1" :step="5" style="width: 110px" />
          </el-form-item>
          <el-form-item label="发行上限">
            <el-input-number v-model="badgeTypeForm.supply" :min="1" :step="10" style="width: 110px" />
          </el-form-item>
          <el-form-item label="图片地址">
            <el-input v-model="badgeTypeForm.image_url" placeholder="https://... （选填）" style="width: 200px" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="badgeTypeForm.desc" placeholder="勋章寓意（选填）" style="width: 180px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="addingBadgeType" @click="addBadgeType">新增</el-button>
          </el-form-item>
        </el-form>
        <div class="dq-tip">
          <span class="dt-label">说明:</span>类型由持有发行职能的业务节点维护（当前身份可发行：<b>{{ issuableForms.join(' / ') }}</b>）；
          <b>骑行券全平台仅一份、仅共享单车公司（bike）</b>可维护，因为它是券的兑付义务人；发行上限只可上调不可下调。
        </div>
      </div>

      <!-- 联盟角色铸造入口：业务方直接向居民铸造发放勋章 / 骑行券 -->
      <div class="dq-card mint-admin" v-if="canMintBadge">
        <div class="dq-card-title sub-title">
          🏭 联盟角色铸造入口
          <span class="dq-tag warn" style="margin-left: 8px">链上 FROM = {{ currentRole?.role_key }} 角色钱包</span>
        </div>
        <div class="dq-tip" style="margin-bottom: 10px">
          <span class="dt-label">说明:</span>
          联盟业务方可将勋章 / 骑行券直接铸造发放给居民钱包（ERC1155 mint），无需居民消耗能量兑换，模拟真实场景的权益空投。
        </div>
        <div v-if="!canIssueVoucherCap" class="dq-tip" style="margin-bottom: 10px">
          <span class="dt-label">权限提示:</span>
          骑行券（voucher）仅共享单车公司（bike）可维护与发放；当前角色仅可铸造发放生态勋章。
        </div>
        <el-form :inline="true" size="small">
          <el-form-item label="资产类型">
            <el-select v-model="mintTypeId" style="width: 180px">
              <el-option
                v-for="bt in mintableTypes"
                :key="bt.id"
                :label="`${bt.icon || '🎖️'} ${bt.name}（剩余 ${Math.max(bt.supply - bt.minted, 0)}）`"
                :value="bt.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="接收钱包">
            <el-select
              v-model="mintToWallet"
              filterable
              allow-create
              default-first-option
              placeholder="接收居民的真实链上钱包地址（0x…）"
              style="width: 260px"
            >
              <el-option
                v-for="w in mintTargetOptions"
                :key="w.addr"
                :label="w.label"
                :value="w.addr"
              >
                <span>{{ w.label }}</span>
                <span class="dq-mono dim" style="float: right; margin-left: 12px">{{ shortAddr(w.addr) }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="数量">
            <el-input-number v-model="mintQty" :min="1" :max="100" style="width: 100px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="mintingBadge" @click="mintBadgeTo">
              铸造发放
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 居民：我持有的勋章 / 骑行券（可拆挂） -->
      <div class="dq-card-title sub-title" style="margin-top: 16px" v-if="canExchange">
        我持有的勋章 / 骑行券
        <span class="dq-tag tiny">ERC1155 · 同类多份可按份拆挂</span>
        <el-button v-if="canTrade" size="small" type="success" plain style="margin-left: 12px" @click="$router.push('/nft?tab=green')">
          📈 前往资产市场
        </el-button>
      </div>
      <el-table :data="badges" border size="small" v-if="canExchange && badges.length">
        <el-table-column prop="badge_type" label="类型" width="140">
          <template #default="{ row }">
            <span>{{ badgeLabel(row.badge_type).icon }} {{ badgeLabel(row.badge_type).name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="token_id" label="Token ID" width="120">
          <template #default="{ row }"><span class="dq-mono">{{ row.token_id }}</span></template>
        </el-table-column>
        <el-table-column label="数量" width="120">
          <template #default="{ row }">
            <span class="dq-mono">{{ row.quantity || 1 }}</span>
            <span v-if="(row.total_held || 0) > (row.quantity || 1)" class="dq-tag info">共持 {{ row.total_held }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="持有者" min-width="160">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.owner) }}</span></template>
        </el-table-column>
        <el-table-column label="兑换时间" width="170">
          <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <template v-if="String(row.owner).toLowerCase() === String(wallet).toLowerCase()">
              <el-button
                v-if="!isListed(row.badge_type === 'voucher' ? 'voucher' : 'badge', Number(row.id))"
                size="small"
                type="primary"
                plain
                :disabled="!canTrade"
                :title="canTrade ? '' : denyTip(CAP.market)"
                :loading="listingId === `${row.badge_type === 'voucher' ? 'voucher' : 'badge'}_${row.id}`"
                @click.stop="openListDlg(row.badge_type === 'voucher' ? 'voucher' : 'badge', Number(row.id), badgeLabel(row.badge_type).name, Number(row.quantity || 1))"
              >
                挂牌
              </el-button>
              <template v-else>
                <span class="dq-tag info">📍 在售</span>
                <!-- 下架是退出通道，不做职能硬拦（即使已切到发行方身份也能收单） -->
                <el-button size="small" type="danger" plain @click.stop="cancelListing(activeListing(row.badge_type === 'voucher' ? 'voucher' : 'badge', Number(row.id))?.id)">下架</el-button>
              </template>
            </template>
            <span v-else class="dq-mono dim">-</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="canExchange && !badges.length" class="empty-tip">暂无勋章 / 骑行券，用能量兑换或由节点铸造发放后在此展示</div>

      <!-- 发行节点：本节点发行 / 发放出去的清单（链上 FROM = 机构钱包，谁发行谁可查） -->
      <template v-if="canMintBadge && !canExchange">
        <div class="dq-card-title sub-title" style="margin-top: 16px">
          本节点发行 / 发放列表
          <span class="dq-tag tiny">居民能量兑换与联盟铸造都记在本节点名下</span>
        </div>
        <el-table :data="badges" border size="small" v-if="badges.length">
          <el-table-column prop="badge_type" label="类型" width="120">
            <template #default="{ row }">{{ badgeLabel(row.badge_type).icon }} {{ badgeLabel(row.badge_type).name }}</template>
          </el-table-column>
          <el-table-column prop="name" label="资产名称" min-width="150" />
          <el-table-column label="份数" width="90">
            <template #default="{ row }"><span class="dq-mono">{{ row.quantity || 1 }}</span></template>
          </el-table-column>
          <el-table-column prop="owner" label="接收居民钱包" min-width="150">
            <template #default="{ row }"><span class="dq-mono dim" :title="row.owner">{{ short(row.owner) }}</span></template>
          </el-table-column>
          <el-table-column label="发行链路" width="130">
            <template #default="{ row }">
              <span class="dq-tag" :class="row.source === 'mint' ? 'accent' : 'info'">
                {{ row.source === 'mint' ? '铸造发放' : '能量兑换' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="能量回收" width="110">
            <template #default="{ row }">
              <span class="dq-mono">{{ Number(row.cost_energy || 0) > 0 ? `+${row.cost_energy}` : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="tx_hash" label="交易哈希" min-width="170">
            <template #default="{ row }"><span class="dq-mono dim">{{ row.tx_hash ? short(row.tx_hash) : '-' }}</span></template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-tip">
          本节点还没有发行记录：居民兑换本节点类型、或经上方铸造入口发放后，逐笔在此展示
        </div>
      </template>
    </div>

    <!-- 7. 综合钱包：当前操作钱包的资产总览（钱包候选与顶栏同表，不再手输任意地址） -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">💼</span>
        {{ isMyWallet ? '综合钱包·我的资产' : '综合钱包·组织钱包' }}
        <span class="dq-tag" style="margin-left: 8px">{{ identityIcon }} {{ identityName }}</span>
        <el-button size="small" @click="loadAll" style="margin-left: auto">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
      <el-form label-width="80px" size="small" style="margin-bottom: 12px">
        <el-form-item label="查询钱包">
          <el-select v-model="walletModel" filterable style="width: 100%" :title="wallet">
            <el-option v-for="w in walletOptions" :key="w.addr" :label="w.label" :value="w.addr">
              <span>{{ w.label }}</span>
              <span class="dq-mono dim" style="float: right; margin-left: 12px">{{ shortAddr(w.addr) }}</span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>

      <div class="wallet-grid">
        <!-- 居民看链上能量余额；节点组织钱包看发行授信余量（发行方不做持有方，余额恒 0） -->
        <div class="dq-glass energy-balance">
          <div class="eb-label">⚡ {{ energyTile.label }}</div>
          <div class="eb-num">{{ energyTile.num }}</div>
          <div class="eb-sub">{{ energyTile.sub }}</div>
        </div>

        <!-- 当前钱包持有的证书 / 勋章 / 骑行券统一视图（不再按 ERC 标准分块，
             详细展示与挂牌操作见上方「植树证书」「勋章与骑行券」两个专区） -->
        <div class="dq-card wallet-block">
          <div class="dq-card-title sub-title">
            🌱 {{ isMyWallet ? '我的绿色资产' : '组织钱包持有的绿色资产' }}
            <span class="dq-tag" style="margin-left: 8px">{{ walletAssets.length }} 项</span>
          </div>
          <div class="dq-tip" style="margin-bottom: 8px">
            <span class="dt-label">来源:</span>
            {{ isMyWallet
              ? '植树证书由 PlantCertificate（ERC721，每份唯一）消耗能量兑换；勋章 / 骑行券由 EcoBadge（ERC1155）能量兑换或联盟铸造发放获得。详细的挂牌 / 在售操作见上方资产专区。'
              : '发行方钱包不作为资产持有方：能量从这里发行、回收后进国库，兑换来的资产归居民钱包；此处只展示机构钱包的历史残留资产。' }}
          </div>
          <div v-if="walletAssets.length" class="asset-list">
            <div class="asset-item" v-for="a in walletAssets" :key="a.key">
              <span class="ai-name">{{ a.icon }} {{ a.name }}</span>
              <span class="ai-tags">
                <span class="dq-tag" :class="a.standard === 'ERC721' ? 'accent' : 'warn'">{{ a.standard }}</span>
                <span class="dq-mono dim">{{ a.idText }}</span>
                <span v-if="a.listed" class="dq-tag info">📍 在售</span>
              </span>
            </div>
          </div>
          <div v-else class="empty-tip small">
            {{ isMyWallet ? '暂无绿色资产，兑换证书 / 勋章 / 骑行券后在此展示' : '机构钱包不持有绿色资产（符合发行方口径）' }}
          </div>
        </div>
      </div>

      <div class="dq-tip">
        <span class="dt-label">口径:</span>
        能量与资产都按<b>钱包真实地址</b>归属；逐笔能量变动看上方「能量流水账本」，
        发行 / 获取台账在「绿色能量」卡里按身份展示（此处不再列一份重复表）。
      </div>
    </div>

    <!-- 8. 资产挂牌对话框 -->
    <el-dialog v-model="listDlg" title="挂牌出售绿色资产" width="480px">
      <div class="list-info" v-if="curAsset">
        <div class="li-row">
          <span>资产名称</span><b>{{ curAsset.name }}</b>
        </div>
        <div class="li-row">
          <span>资产类型</span>
          <span class="dq-tag accent">{{ assetTypeLabel(curAsset.type) }}</span>
        </div>
        <div class="li-row">
          <span>当前持有者</span>
          <span class="dq-mono dim">{{ short(wallet) }}</span>
        </div>
        <div class="li-row" v-if="curAsset.held > 1">
          <span>本行持有</span>
          <span class="dq-mono">{{ curAsset.held }} 份（同一行资产仅允许一个在售挂牌）</span>
        </div>
      </div>
      <el-form label-width="100px" style="margin-top: 12px">
        <el-form-item v-if="curAsset && curAsset.held > 1" label="挂牌份数">
          <el-input-number v-model="listQty" :min="1" :max="curAsset.held" style="width: 100%" />
          <div class="dq-tip" style="margin-top: 4px">
            <span class="dt-label">ERC1155:</span>可只拆挂部分份数，成交后剩余份数仍归你持有。
          </div>
        </el-form-item>
        <el-form-item label="挂牌总价">
          <el-input-number v-model="listPrice" :min="1" :step="10" style="width: 100%" />
          <div class="dq-tip" style="margin-top: 4px">
            <span class="dt-label">说明:</span>以绿色能量（GreenEnergy ERC20）计价，成交时买方一次性支付本单总价
            <span v-if="listQty > 1" class="dq-mono">（单价约 {{ Math.ceil(listPrice / listQty) }} / 份）</span>。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="listDlg = false">取消</el-button>
        <el-button type="primary" :loading="listing" @click="doList">确认挂牌</el-button>
      </template>
    </el-dialog>

    <!-- 10. 能量发放业务凭证表单（动态字段，按联盟角色生成） -->
    <EnergyProofForm
      ref="proofFormRef"
      v-model:visible="proofDlg"
      :role-name="activeIssueRole ? roleMeta(activeIssueRole.key)?.name : ''"
      :points="currentEnergyAction.amount"
      :rule="currentRuleObj"
      :threshold-hint="currentThresholdHint"
      :proof-no-label="currentProofNoLabel"
      :proof-no-field="currentRuleObj?.proof_no_field"
      @submit="submitProof"
    />

    <!-- 9. 绿色资产市场（买卖 / 下架 闭环）：仅具备市场流通职能的身份可见 -->
    <div class="dq-card section-card" v-if="canTrade">
      <div class="dq-card-title">
        <span class="title-icon">💱</span>
        绿色资产市场
        <span class="dq-tag" style="margin-left: 8px">在售 {{ marketList.length }} · 我挂牌 {{ myListings.length }}</span>
        <el-button size="small" @click="loadMarket" style="margin-left: auto">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
      <div class="dq-tip" style="margin-bottom: 10px">
        <span class="dt-label">流通闭环:</span>
        居民挂牌 NFT 资产 → 其他居民用绿色能量购买（ERC20 转账 + NFT transferFrom）→ 资产归属自动转移；卖家可随时下架。
        <span v-if="!canTrade" class="dq-tag warn" style="margin-left: 6px">{{ denyTip(CAP.market) }}</span>
      </div>
      <el-table :data="marketList" border size="small" v-if="marketList.length">
        <el-table-column prop="asset_name" label="资产名称" min-width="180">
          <template #default="{ row }">
            <span>{{ greenAssetIcon(row.asset_type) }} {{ row.asset_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="asset_type" label="类型" width="120">
          <template #default="{ row }">
            <span class="dq-tag" :class="row.asset_type === 'certificate' ? 'accent' : 'warn'">
              {{ assetTypeShort(row.asset_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="standard" label="协议" width="100" />
        <el-table-column prop="seller" label="卖家" min-width="160">
          <template #default="{ row }">
            <span class="dq-mono dim">{{ short(row.seller) }}</span>
            <span v-if="String(row.seller).toLowerCase() === String(wallet).toLowerCase()" class="dq-tag info" style="margin-left:6px">我</span>
          </template>
        </el-table-column>
        <el-table-column prop="price_energy" label="总价(能量)" width="130">
          <template #default="{ row }">
            <span class="dq-mono energy-val">{{ row.price_energy }}</span>
            <span v-if="(row.quantity || 1) > 1" class="dq-tag info">{{ row.quantity }} 份</span>
          </template>
        </el-table-column>
        <el-table-column label="挂牌时间" width="170">
          <template #default="{ row }"><span class="dq-mono dim">{{ fmtDateTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <!-- 自己的资产：下架 -->
            <el-button
              v-if="String(row.seller).toLowerCase() === String(wallet).toLowerCase()"
              size="small"
              type="danger"
              plain
              @click.stop="cancelListing(row.id)"
            >
              下架
            </el-button>
            <!-- 别人的资产：购买（仅具备市场职能的居民） -->
            <el-button
              v-else
              size="small"
              type="primary"
              :disabled="!canTrade || energyShort(row.price_energy)"
              :loading="buyingMarketId === row.id"
              @click.stop="buyMarket(row)"
            >
              {{ marketBuyText(row) }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-tip">市场暂无在售资产，可在上方证书 / 勋章列表中挂牌资产后由其他居民购买</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onActivated } from 'vue'
import { ecoApi } from '@/api'
import { safeErrDetail } from '@/utils/errDesc'
import { normAddr } from '@/utils/address'
import { fmtDateTime } from '@/utils/time'
import { energyRuleHint } from '@/utils/energy'
import { isChainAddress, shortAddr, useWalletStore } from '@/stores/wallets'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import EnergyProofForm from '@/components/EnergyProofForm.vue'

/* ==================== 钱包（与 Pinia store 联动） ====================
   口径：页面上所有「钱包」一律是真实链上地址（0x + 40 hex）。地址↔角色
   映射只取 useWalletStore（后端 /api/eco/roles 派生），与顶栏选择器同一张表：
   顶栏切钱包 → 这里角色高亮跟着变；这里点角色 → 顶栏钱包跟着切到该机构地址。*/
const app = useAppStore()
const wallets = useWalletStore()
const auth = useAuthStore()
const wallet = computed(() => app.currentWallet)
const setWallet = (v: string) => {
  app.setWallet(v)
  loadAll()
}

// watch store 钱包变化（header 全局切换时联动刷新）
watch(() => app.currentWallet, () => {
  loadAll()
})

/* ==================== 角色元数据（本地展示配置） ==================== */
interface RoleMeta {
  icon: string
  name: string
  desc: string
  rule: string
  color: string
  action?: string
  amount?: number
}
/* 主题色与后端 alliance_roles.ROLES[].color 逐字对齐（卡片图标 / 左边框取色），
   后端返回 color 时优先取接口值，避免两边调色板各写一套。 */
const ROLE_META: Record<string, RoleMeta> = {
  admin:     { icon: '🛡️', name: '管理员',   desc: '联盟秘书处：部署合约、维护树种与发行额度、管理能量国库', rule: '不发行能量 · 负责联盟治理', color: '#4d8dff' },
  metro:     { icon: '🚇', name: '地铁集团', desc: '城市地铁运营方', rule: '乘坐地铁 +50 起（按里程加成）',     action: '乘坐地铁',   amount: 50, color: '#00e6c3' },
  bus:       { icon: '🚌', name: '公交集团', desc: '城市公交运营方', rule: '乘坐公交 +20 起（按时长加成）',     action: '乘坐公交',   amount: 20, color: '#ffcf4d' },
  bike:      { icon: '🚲', name: '共享单车', desc: '共享单车运营方，可发放骑行券', rule: '共享单车骑行 +15 起（按里程加成）', action: '共享单车骑行', amount: 15, color: '#f5379b' },
  takeout:   { icon: '📦', name: '外卖平台', desc: '绿色外卖服务平台', rule: '无需餐具 固定 +10 能量',   action: '绿色外卖',   amount: 10, color: '#ff7849' },
  recycling: { icon: '♻️', name: '回收公司', desc: '旧物回收公司',   rule: '旧物回收 +100 起（按重量加成）',   action: '旧物回收',   amount: 100, color: '#52c41a' },
}
/* 历史别名兼容：旧 key delivery / 钱包缩写 recycle → 后端权威 key（与 alliance_roles.ROLE_ALIAS 一致） */
const ROLE_KEY_ALIAS: Record<string, string> = { delivery: 'takeout', recycle: 'recycling' }
const roleMeta = (key?: string) => (key ? ROLE_META[ROLE_KEY_ALIAS[key] || key] : undefined)

/** 角色列表：以后端 ROLES（address / energy_quota / energy_issued）+ 职能矩阵行为准，
 *  本地 ROLE_META 只补图标与文案；**不再前端硬编码 0xmetro 这类别名作钱包标识**。*/
const roleList = computed(() =>
  Object.entries(ROLE_META).map(([key, m]) => {
    const api: any = roles.value.find((x: any) => (ROLE_KEY_ALIAS[x.key] || x.key) === key) || {}
    const row: any = dutyRows.value.find((r: any) => r.key === key) || {}
    const address = normAddr(api.address || row.address || '')
    const quota = Number(api.energy_quota ?? row.energy_quota ?? 0) || 0
    const issued = Number(api.energy_issued ?? row.energy_issued ?? 0) || 0
    return {
      key, ...m,
      address: isChainAddress(address) ? address : '',
      alias: String(api.wallet_alias || row.wallet_alias || ''),
      color: String(api.color || row.color || m.color || '#4d8dff'),
      profile: row.profile || (key === 'admin' ? 'admin' : 'node'),
      dims: row.dimensions || null,
      caps: row.capabilities || [],
      quota, issued,
      /** 发行授信进度：预先算好一次，模板不再反复调 quotaOf(r) 判空 */
      quotaView: quotaOf({ quota, issued }),
    }
  }),
)
/** 职能层一句话（与后端 role_profile 同口径：admin / node / resident） */
const PROFILE_LABEL: Record<string, string> = {
  admin: '联盟治理方', node: '能量发行节点', resident: '能量需求方',
}
const profileLabel = (p?: string) => PROFILE_LABEL[p || 'resident'] || '联盟节点'
/** 居民（普通用户）卡片文案：直接取后端 RESIDENT_PROFILE 的 desc（未就绪时回落本地） */
const ROLE_META_RESIDENT_DESC = '低碳居民（本人钱包）：5 种低碳行为获能，攒能量兑换证书 / 勋章 / 骑行券，并可在市场挂牌与购买'
const residentDims = computed<string[]>(() => {
  const row: any = dutyRows.value.find((r: any) => r.key === 'resident')
  const tags = dutyCols.value
    .filter((d: any) => row?.dimensions?.[d.key])
    .map((d: any) => d.name)
  return tags.length ? tags : ['获取绿色能量', '兑换绿色资产', '二级市场交易']
})
/** 卡片上的职能标签（直接取后端 dimensions，不在前端重写角色名单） */
const dimTags = (r: any): string[] =>
  dutyCols.value.filter((d: any) => r?.dims?.[d.key]).map((d: any) => d.name)
/** 7 张卡一排后单卡宽度有限，职能只给前 2 项 + 计数，完整名单放 title  Tooltip */
const DIMS_INLINE = 2
const dimsBrief = (tags: string[]): string => {
  if (!tags.length) return ''
  if (tags.length <= DIMS_INLINE) return tags.join(' · ')
  return `${tags.slice(0, DIMS_INLINE).join(' · ')} 等 ${tags.length} 项`
}
/** 发行规则一句话：按量核算的节点写成「基础起 + 封顶」，固定点数则标明固定 */
const ruleText = (key: string): string => {
  const def: any = roles.value.find((x: any) => x.key === key)
  const rule = def?.energy_rule
  if (!rule) return ROLE_META[key]?.rule || ''
  const cap = Number(rule.bonus_cap || rule.points || 0)
  return Number(rule.bonus_per_unit || 0) > 0
    ? `${rule.action} ${rule.points} 起，超量按量加成（单次封顶 ${cap}）`
    : `${rule.action} 固定 ${rule.points} 能量`
}

/* ==================== 勋章元数据 ==================== */
const BADGE_META: Record<string, { icon: string; name: string }> = {
  badge:   { icon: '🏅', name: '生态勋章' },
  voucher: { icon: '🎫', name: '骑行券' },
}
const badgeLabel = (type: string) => BADGE_META[type] || { icon: '🎖️', name: type }

/* ==================== 状态定义 ==================== */
const loading = ref(false)
const issuing = ref(false)
const addingTree = ref(false)
const exchangingTree = ref<number | null>(null)
const exchangingBadge = ref<string>('')

const roles = ref<any[]>([])
const currentRole = ref<any>(null)
const contractStatus = ref<any>({})

/* 钱包地址 → 联盟角色 key 的映射已收敛到 useWalletStore.roleKeyByAddress
   （数据源 = 后端 /api/eco/roles 的真实 address），不再在本页硬编码 0x 别名表。*/
const energyBalance = ref(0)
/** 余额是否读到了可信数值。接口失败时绝不能把「读不到」当成「真的是 0」：
 *  那样每个兑换 / 购买按钮都会变成「需 N 能量」，把一次查询故障伪装成用户能量不够。*/
const energyKnown = ref(true)
/** 链上待同步差额（账本 > 链上）：正常恒为 0，非 0 说明本地链刚重置过，
 *  兑换时后端会自动补齐，此处只作可见的诊断信息。*/
const energySyncGap = ref(0)
/** 余额足够否的唯一口径：未知余额不拦人（链上扣款前后端会硬校验并给可诊断报错）*/
const energyShort = (cost: number): boolean =>
  energyKnown.value && energyBalance.value < Number(cost || 0)
const energyRecords = ref<any[]>([])
/** 能量台账累计（后端 SQL 聚合，不受列表 limit 截断）与笔数 */
const energyTotalPoints = ref(0)
const energyTotalCount = ref(0)
/** 能量流水（eco_energy_flows）与流水净额 */
const energyFlows = ref<any[]>([])
const flowBalance = ref(0)
const trees = ref<any[]>([])
const certificates = ref<any[]>([])
const badges = ref<any[]>([])

const treeForm = reactive({ name: '', required_energy: 1000, supply: 100, image_url: '', description: '' })

/* ==================== 四维度职能（能力位 = 后端唯一口径，前端只渲染不判定） ==================== */
/* 常量名与后端 app/learning/alliance_roles.py 的 CAP_* 一一对应（字符串协议，不可随意改） */
const CAP = {
  energyIssue: 'energy.issue', energyReceive: 'energy.receive',
  issueCert: 'asset.issue.certificate', issueBadge: 'asset.issue.badge', issueVoucher: 'asset.issue.voucher',
  exchange: 'asset.exchange', market: 'market.trade',
  catalog: 'govern.catalog', treasury: 'govern.treasury', deploy: 'govern.deploy',
}
/** 无权限时的提示文案（与后端 CAP_DENY_REASON 同口径，告知应该怎么切） */
const CAP_HINT: Record<string, string> = {
  [CAP.exchange]: '绿色资产兑换是需求方（居民）的职能，发行方不能购买自己发行的资产',
  [CAP.market]: '挂牌 / 购买属居民之间的二级市场流转，联盟节点不以机构身份参与交易',
  [CAP.energyIssue]: '能量由业务联盟节点按低碳行为发行',
  [CAP.energyReceive]: '发行方 / 国库账户不作为能量接收方',
  [CAP.catalog]: '树种与发行额度目录属联盟治理，仅管理员可维护',
  [CAP.treasury]: '能量国库与销毁属联盟治理，仅管理员可执行',
  [CAP.deploy]: '联盟内置合约部署属治理动作，仅管理员可执行',
}
const duties = ref<any>(null)
const dutiesLoading = ref(false)

/** 当前身份的能力位（后端 /roles/duties 与 /role/current 同源，取先到的那个） */
const caps = computed<string[]>(() =>
  duties.value?.identity?.capabilities || currentRole.value?.capabilities || [CAP.energyReceive, CAP.exchange, CAP.market])
const hasCap = (c: string) => caps.value.includes(c)
const denyTip = (c: string) => CAP_HINT[c] || '当前身份不具备该职能'
/** 当前身份的职能开关（驱动业务项显隐，不再看本地角色名单） */
const canExchange = computed(() => hasCap(CAP.exchange))
const canTrade = computed(() => hasCap(CAP.market))
const canIssueEnergy = computed(() => hasCap(CAP.energyIssue))
const canReceiveEnergy = computed(() => hasCap(CAP.energyReceive))
const canManageCatalog = computed(() => hasCap(CAP.catalog))
const canTreasuryOps = computed(() => hasCap(CAP.treasury))
const canDeployContract = computed(() => hasCap(CAP.deploy))
/** 当前身份可发行的资产形态（ERC721 / ERC1155 按协议分治） */
const myAssetForms = computed<any[]>(() => duties.value?.identity?.dimensions?.issue_asset?.forms || [])
const dutyRows = computed<any[]>(() => duties.value?.matrix || [])
const dutyCols = computed<any[]>(() => duties.value?.dimensions || [])

/* ==================== 能量国库（回收 / 销毁 / 通胀审计） ==================== */
const treasury = ref<any>(null)
const burning = ref(false)
const burnForm = reactive({ amount: 0, note: '' })

/* ==================== 能量发放业务凭证 ==================== */
const proofDlg = ref(false)
const proofFormRef = ref<any>(null)
/** 本次发放目标角色 key：普通用户在行为卡片选定 > 当前联盟角色（角色扮演发放） */
const issuingRoleKey = ref('')
/** 本次发放目标角色定义（优先后端权威 ROLES 数据，含 energy_rule 凭证字段） */
const activeIssueRole = computed<any>(() => {
  const key = issuingRoleKey.value || currentRole.value?.role_key || ''
  if (!key) return null
  return (
    roles.value.find((r: any) => r.key === key)
    || (currentRole.value?.role_key === key ? currentRole.value?.role : null)
    || null
  )
})
/** 具备能量发放规则的业务角色 = 普通用户（居民）的 5 种低碳行为获取能量方式 */
const energyWayRoles = computed(() => roles.value.filter((r: any) => r.energy_rule))
/** 本次发放目标角色的 energy_rule（含 proof_fields 等） */
const currentRuleObj = computed(() => activeIssueRole.value?.energy_rule || null)
/** 阈值提示（如 distance_km ≥ 10 km） */
const currentThresholdHint = computed(() => {
  const r = currentRuleObj.value
  if (!r) return ''
  if (r.proof_field === 'no_cutlery') return 'no_cutlery = true（必须选择无需餐具）'
  return `${r.proof_field} ≥ ${r.min} ${r.unit}`
})
const PROOF_NO_LABELS: Record<string, string> = {
  trip_no: '业务单号（乘车号）', order_id: '业务单号（订单号）',
  order_no: '业务单号（回收单号）', platform_order: '业务单号（平台订单）',
}
const currentProofNoLabel = computed(() =>
  PROOF_NO_LABELS[currentRuleObj.value?.proof_no_field] || '业务单号',
)

/** 打开业务凭证表单（roleKey：普通用户在行为卡片选定；缺省取当前联盟角色） */
const openProofDlg = (roleKey?: string) => {
  const key = roleKey || currentRole.value?.role_key
  if (!key) {
    ElMessage.warning('请先选择角色')
    return
  }
  const def = roles.value.find((r: any) => r.key === key)
    || (currentRole.value?.role_key === key ? currentRole.value?.role : null)
  if (!def?.energy_rule) {
    ElMessage.warning('该角色没有能量发放规则')
    return
  }
  issuingRoleKey.value = key
  proofDlg.value = true
}

/** 提交业务凭证 → 后端校验 → 联盟节点发放能量（居民申请 / 角色扮演两种模式） */
const submitProof = async (proof: Record<string, any>) => {
  const rk = activeIssueRole.value?.key || currentRole.value?.role_key
  if (!rk) return
  issuing.value = true
  try {
    const r: any = await ecoApi.issueEnergy(wallet.value, rk, proof)
    const pfNo = currentRuleObj.value?.proof_no_field
    const pts = r?.points ?? currentEnergyAction.value.amount
    const prefix = r?.mode === 'resident_apply' ? '业务凭证审核通过' : '能量发放成功'
    ElMessage.success(`${prefix}，【${roleMeta(rk)?.name}】已发放：+${pts}，业务单号 ${pfNo && proof[pfNo] ? proof[pfNo] : '-'}`)
    logEco(
      'energy', 'issue_energy', 'success',
      `${roleMeta(rk)?.name} · ${currentEnergyAction.value.label} +${pts}点（${r?.mode || 'role_play'}），单号 ${pfNo && proof[pfNo] ? proof[pfNo] : '-'}`,
    )
    proofDlg.value = false
    await Promise.all([loadEnergyBalance(), loadEnergyRecords(), loadEnergyFlows(), loadWorkbench(), loadTreasury()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '能量发放失败'
    ElMessage.error(msg)
    logEco('energy', 'issue_energy', 'error', msg, safeErrDetail(e))
  } finally {
    issuing.value = false
    proofFormRef.value?.setSubmitting(false)
  }
}

/* ==================== 勋章类型 / 铸造入口 ==================== */
const badgeTypes = ref<any[]>([])
const badgeTypeForm = reactive({
  badge_type: 'badge' as 'badge' | 'voucher',
  name: '', icon: '', image_url: '', cost_energy: 10, supply: 100, desc: '',
})
const addingBadgeType = ref(false)
const mintTypeId = ref<number | null>(null)
/** 接收方钱包：默认本人（居民）地址；不再预填 0xresident —— 后端解不到这个别名
 *  会按需建号，结果是铸到一个谁都不持有的幽灵地址 */
const mintToWallet = ref('')
const mintQty = ref(1)
const mintingBadge = ref(false)

/** 发行方职能：能否铸造发放资产（能力位口径，与后端 /badges/mint 守卫一致） */
const canIssueBadgeCap = computed(() => hasCap(CAP.issueBadge))
const canIssueVoucherCap = computed(() => hasCap(CAP.issueVoucher))
const canMintBadge = computed(() => canIssueBadgeCap.value || canIssueVoucherCap.value)

/** 当前角色为共享单车公司（骑行券唯一维护方 / 兑付义务人） */
const isBike = computed(() => currentRole.value?.role_key === 'bike')

/** 是否可新增勋章 / 骑行券类型：必须由具备对应发行职能的业务节点维护（谁发行、谁铸造、谁兜付） */
const canAddBadgeTypes = computed(() => canMintBadge.value)

/* ---- 卡片级可见性：严格按后端能力位，与该身份无关的业务块直接不出现 ---- */
/** 植树证书：目录治理（治理方）或能量兑换（居民）才成立；只发能量的节点不涉证书业务 */
const showTreeCard = computed(() => canManageCatalog.value || canExchange.value)
/** 勋章与骑行券：居民兑换，或节点持有勋章 / 骑行券发行职能 */
const showBadgeCard = computed(() => canExchange.value || canMintBadge.value)
/** 能量国库与通胀审计：联盟治理职能专属（节点与居民不涉国库，公开总量在监管页） */
const canViewTreasury = computed(() =>
  canTreasuryOps.value || (!!auth.isTeacher && !walletRoleKey.value))

/** 类型目录里当前身份可维护的资产子集（骑行券仅 bike 节点） */
const issuableForms = computed<string[]>(() => {
  const set: string[] = []
  if (canIssueBadgeCap.value) set.push('勋章 (ERC1155)')
  if (canIssueVoucherCap.value) set.push('骑行券 (ERC1155)')
  return set
})

/** ERC1155 同类可多份：逐类型的待兑份数（成本 = 单价 × 份数） */
const badgeQty = reactive<Record<string, number>>({})
const qtyOf = (bt: any): number => {
  const k = String(bt.id)
  if (!(k in badgeQty)) badgeQty[k] = 1
  return badgeQty[k]
}
/** 单次可兑上限：剩余额度 与 当前能量可负担份数 取小 */
const badgeMaxQty = (bt: any): number => {
  const remain = Math.max(0, Number(bt.supply ?? 0) - Number(bt.minted ?? 0))
  const afford = energyKnown.value && Number(bt.cost_energy) > 0
    ? Math.floor(energyBalance.value / Number(bt.cost_energy)) : Infinity
  return Math.max(1, Math.min(remain || 1, (Number.isFinite(afford) ? afford : remain) || 1))
}
const badgeBtnText = (bt: any): string => {
  if (!canExchange.value) return '仅需求方（居民）可兑换'
  if (Number(bt.minted) >= Number(bt.supply)) return '发行额度已用尽'
  if (energyShort(bt.cost_energy * qtyOf(bt))) return `需 ${bt.cost_energy * qtyOf(bt)} 能量`
  return `兑换 ${qtyOf(bt)} 份`
}

/** 当前角色可铸造的类型：issuer_role 为空（全体）或等于当前角色 */
const mintableTypes = computed(() => {
  const rk = currentRole.value?.role_key
  return badgeTypes.value.filter(
    (bt) => !bt.issuer_role || bt.issuer_role === rk,
  )
})

const loadBadgeTypes = async () => {
  try {
    const r: any = await ecoApi.badgeTypes()
    badgeTypes.value = r?.items || r || []
    // 默认选中第一个可铸造类型
    if (!mintTypeId.value && mintableTypes.value.length) {
      mintTypeId.value = mintableTypes.value[0].id
    }
  } catch {
    badgeTypes.value = []
  }
}

/** 兑换勋章 / 骑行券（按类型 ID + 份数，能量回收闭环） */
const exchangeBadgeType = async (bt: any) => {
  const qty = qtyOf(bt)
  exchangingBadge.value = String(bt.id)
  try {
    await ecoApi.exchangeBadge(wallet.value, bt.badge_type, bt.id, qty)
    ElMessage.success(`${bt.name} 兑换成功 ${qty} 份 ${bt.icon || '🎖️'}`)
    logEco('badge', 'exchange_badge', 'success',
      `兑换${bt.name} ${qty} 份（type_id=${bt.id}，消耗 ${bt.cost_energy * qty} 能量）`)
    await Promise.all([loadEnergyBalance(), loadBadges(), loadBadgeTypes(), loadTreasury(), loadEnergyFlows()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '勋章兑换失败'
    ElMessage.error(msg)
    logEco('badge', 'exchange_badge', 'error',
      `${msg} (type_id=${bt.id}, qty=${qty})`, safeErrDetail(e))
  } finally {
    exchangingBadge.value = ''
  }
}

/** 联盟角色新增勋章 / 骑行券类型 */
const addBadgeType = async () => {
  if (!badgeTypeForm.name.trim()) {
    ElMessage.warning(badgeTypeForm.badge_type === 'voucher' ? '请填写骑行券名称' : '请填写勋章名称')
    return
  }
  if (badgeTypeForm.cost_energy < 1) {
    ElMessage.warning('消耗能量必须大于 0')
    return
  }
  if (badgeTypeForm.supply < 1) {
    ElMessage.warning('发行上限必须大于 0')
    return
  }
  if (badgeTypeForm.badge_type === 'voucher' && !canIssueVoucherCap.value) {
    ElMessage.warning('骑行券仅共享单车公司（bike）可维护，请先切换角色')
    return
  }
  addingBadgeType.value = true
  try {
    const r: any = await ecoApi.addBadgeType({
      wallet: wallet.value,
      badge_type: badgeTypeForm.badge_type,
      name: badgeTypeForm.name.trim(),
      icon: badgeTypeForm.icon.trim() || (badgeTypeForm.badge_type === 'voucher' ? '🎫' : '🏅'),
      image_url: badgeTypeForm.image_url.trim(),
      cost_energy: badgeTypeForm.cost_energy,
      supply: badgeTypeForm.supply,
      desc: badgeTypeForm.desc,
    })
    const label = badgeTypeForm.badge_type === 'voucher' ? '骑行券' : '勋章类型'
    ElMessage.success(r?.updated
      ? `骑行券「${badgeTypeForm.name}」已更新（骑行券仅维护一份，token_id=${r?.token_id}）`
      : `${label}「${badgeTypeForm.name}」已上架（token_id=${r?.token_id}）`)
    logEco('badge', 'badge_type_add', 'success',
      `新增${label}：${badgeTypeForm.name}，成本 ${badgeTypeForm.cost_energy}，上限 ${badgeTypeForm.supply}`)
    badgeTypeForm.name = ''
    badgeTypeForm.icon = ''
    badgeTypeForm.image_url = ''
    badgeTypeForm.cost_energy = 10
    badgeTypeForm.supply = 100
    badgeTypeForm.desc = ''
    await loadBadgeTypes()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '新增勋章类型失败'
    ElMessage.error(msg)
    logEco('badge', 'badge_type_add', 'error', msg, safeErrDetail(e))
  } finally {
    addingBadgeType.value = false
  }
}

/** 联盟角色铸造发放勋章 / 骑行券给居民 */
const mintBadgeTo = async () => {
  if (!mintTypeId.value) {
    ElMessage.warning('请选择要铸造的资产类型')
    return
  }
  const to = normAddr(String(mintToWallet.value || '').trim())
  if (!isChainAddress(to)) {
    ElMessage.warning('接收钱包必须是居民的真实链上地址（0x + 40 位）；联盟机构钱包不能接收绿色资产')
    return
  }
  mintToWallet.value = to
  const bt = badgeTypes.value.find((x) => x.id === mintTypeId.value)
  try {
    await ElMessageBox.confirm(
      `确认以「${roleMeta(currentRole.value.role_key)?.name}」身份铸造 ${mintQty.value} 个「${bt?.name}」发放给 ${mintToWallet.value}？`,
      '联盟角色铸造',
      { confirmButtonText: '确认铸造', cancelButtonText: '取消', type: 'info' },
    )
  } catch { return }
  mintingBadge.value = true
  try {
    await ecoApi.mintBadge({
      wallet: wallet.value,
      role_key: currentRole.value.role_key,
      type_id: mintTypeId.value,
      to_wallet: to,
      quantity: mintQty.value,
    })
    ElMessage.success(`铸造成功：${bt?.name} x${mintQty.value} → ${mintToWallet.value}`)
    logEco('badge', 'badge_mint', 'success',
      `${roleMeta(currentRole.value.role_key)?.name} 铸造 ${bt?.name} x${mintQty.value} 给 ${mintToWallet.value}`)
    await Promise.all([loadBadgeTypes(), loadBadges()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '铸造失败'
    ElMessage.error(msg)
    logEco('badge', 'badge_mint', 'error', msg, safeErrDetail(e))
  } finally {
    mintingBadge.value = false
  }
}

/* ==================== 一键编译 + 部署内置合约 ==================== */
const deployingKey = ref<string>('')   // 当前正在部署的合约 key

/** 一键编译 + 部署 GreenEnergy / PlantCertificate / EcoBadge */
const deployContract = async (name: string) => {
  try {
    await ElMessageBox.confirm(
      `确认一键编译并部署「${name}」合约到链上？\n将使用默认构造参数部署：${
        { GreenEnergy: '初始供应量 10亿', PlantCertificate: 'name=PlantCertificate, symbol=PCERT', EcoBadge: '无构造参数' }[name] || ''
      }`,
      '一键部署合约',
      { confirmButtonText: '确认部署', cancelButtonText: '取消', type: 'info' },
    )
  } catch { return }
  deployingKey.value = name
  try {
    const r: any = await ecoApi.deployContract(name, wallet.value)
    ElMessage.success(`部署成功：${name} → ${short(r.address)}`)
    logEco('contract', 'deploy_contract', 'success',
      `一键部署 ${name} (${r.standard})，地址：${r.address}，tx：${r.tx_hash}`)
    await loadContractStatus()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '部署失败'
    ElMessage.error(msg)
    logEco('contract', 'deploy_contract', 'error', `部署 ${name} 失败：${msg}`, safeErrDetail(e))
  } finally {
    deployingKey.value = ''
  }
}

/* ==================== 资产市场（挂牌 / 购买 / 下架） ==================== */
const listDlg = ref(false)
const listing = ref(false)
const listingId = ref<string>('')   // 用于按钮 loading 状态
const listPrice = ref(50)
/** 本次挂牌份数（ERC1155 可拆挂；ERC721 恒为 1） */
const listQty = ref(1)
const curAsset = ref<{ type: string; id: number; name: string; held: number } | null>(null)
/** 全部在售绿色资产（市场全局视图，买家可购买、卖家可下架） */
const marketList = ref<any[]>([])
/** 当前钱包的挂牌记录（由市场列表派生，保持与全局一致） */
const myListings = computed(() =>
  marketList.value.filter((m) => String(m.seller).toLowerCase() === String(wallet.value).toLowerCase()),
)
/** 购买中loading：market listing id */
const buyingMarketId = ref<number | null>(null)

const assetTypeLabel = (t: string) =>
  ({ certificate: '植树证书(ERC721)', badge: '生态勋章(ERC1155)', voucher: '骑行券(ERC1155)' }[t] || t)
const assetTypeShort = (t: string) =>
  ({ certificate: '植树证书', badge: '生态勋章', voucher: '骑行券' }[t] || t)
const greenAssetIcon = (t: string) =>
  ({ certificate: '🌱', badge: '🏅', voucher: '🎫' }[t] || '🌿')

/** 判断某资产是否已在售（避免重复挂牌 + 钱包资产标记在售状态） */
const isListed = (asset_type: string, asset_id: number) =>
  marketList.value.some(
    (m) => m.asset_type === asset_type && Number(m.asset_id) === Number(asset_id) && m.status === 'active',
  )

/** 本行资产当前在售的挂牌记录（提供「下架」退出通道用） */
const activeListing = (asset_type: string, asset_id: number) =>
  marketList.value.find(
    (m) => m.asset_type === asset_type && Number(m.asset_id) === Number(asset_id) && m.status === 'active',
  ) || null

/** 打开挂牌对话框（held = 本行持有份数，>1 时可选拆挂数量） */
const openListDlg = (asset_type: string, asset_id: number, name: string, held = 1) => {
  if (!canTrade.value) {
    ElMessage.warning(denyTip(CAP.market))
    return
  }
  curAsset.value = { type: asset_type, id: asset_id, name, held: Math.max(1, Number(held) || 1) }
  listQty.value = curAsset.value.held
  // 建议价格：证书 500，勋章 50，骑行券 100（按份数折算总价）
  const unit = asset_type === 'certificate' ? 500 : asset_type === 'voucher' ? 100 : 50
  listPrice.value = unit * curAsset.value.held
  listDlg.value = true
}

/** 购买按钮文案：先按职能判定，再按余额判定，避免让发行方看到可点的购买按钮 */
const marketBuyText = (row: any): string => {
  if (!canTrade.value) return '仅居民可交易'
  if (energyShort(row.price_energy)) return `需 ${row.price_energy} 能量`
  return (row.quantity || 1) > 1 ? `购买 ${row.quantity} 份` : '购买'
}

/** 确认挂牌 */
const doList = async () => {
  if (!curAsset.value) return
  if (listPrice.value <= 0) {
    ElMessage.warning('价格必须大于 0')
    return
  }
  if (!canTrade.value) {
    ElMessage.warning(denyTip(CAP.market))
    return
  }
  const qty = curAsset.value.held > 1 ? Math.max(1, Math.min(listQty.value, curAsset.value.held)) : 1
  listing.value = true
  // 显式区分三种资产前缀，避免 id 冲突时 loading 状态串台
  const prefix =
    curAsset.value.type === 'certificate' ? 'cert' :
    curAsset.value.type === 'voucher' ? 'voucher' : 'badge'
  listingId.value = `${prefix}_${curAsset.value.id}`
  try {
    await ecoApi.marketList({
      seller: wallet.value,
      asset_type: curAsset.value.type,
      asset_id: curAsset.value.id,
      price_energy: listPrice.value,
      quantity: qty,
    })
    ElMessage.success(`已挂牌：${curAsset.value.name} · ${qty} 份 · ${listPrice.value} 能量`)
    logEco('other', 'list_asset', 'success',
      `挂牌 ${curAsset.value.name} ${qty} 份，总价 ${listPrice.value} 能量`)
    listDlg.value = false
    await loadMarket()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '挂牌失败'
    ElMessage.error(msg)
    logEco('other', 'list_asset', 'error', msg, safeErrDetail(e))
  } finally {
    listing.value = false
    listingId.value = ''
  }
}

/** 取消挂牌（下架）：居民的退出通道，不做能力硬拦 */
const cancelListing = async (id?: number | null) => {
  if (!id) {
    ElMessage.warning('未找到对应的在售挂牌，请先刷新市场列表')
    return
  }
  try {
    await ElMessageBox.confirm('确认下架该资产？下架后可重新挂牌或继续持有。', '下架资产', { type: 'warning' })
  } catch { return }
  try {
    await ecoApi.marketCancel(id, wallet.value)
    ElMessage.success('已下架')
    logEco('other', 'cancel_listing', 'success', `下架 listing_id=${id}`)
    await loadMarket()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '下架失败'
    ElMessage.error(msg)
  }
}

/** 购买绿色资产（别人挂牌的）：GreenEnergy 支付 + NFT 转移 */
const buyMarket = async (g: any) => {
  if (!canTrade.value) {
    ElMessage.warning(denyTip(CAP.market))
    return
  }
  if (energyShort(g.price_energy)) {
    ElMessage.warning(`绿色能量不足：需要 ${g.price_energy}，当前 ${energyBalance.value}`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认购买「${g.asset_name}」？\n将支付 ${g.price_energy} 绿色能量给 ${short(g.seller)}`,
      '购买绿色资产',
      { confirmButtonText: '确认购买', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  buyingMarketId.value = g.id
  try {
    const r: any = await ecoApi.marketBuy(wallet.value, g.id)
    ElMessage.success(`购买成功：${g.asset_name}`)
    logEco('other', 'buy_asset', 'success',
      `购买 ${g.asset_name} ${(g.quantity || 1)} 份，支付 ${g.price_energy} 能量，tx=${r?.nft_tx || '-'}`)
    // 购买会改变能量余额、资产归属、市场列表 → 全量刷新
    await loadAll()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '购买失败'
    ElMessage.error(msg)
    logEco('other', 'buy_asset', 'error', msg, safeErrDetail(e))
  } finally {
    buyingMarketId.value = null
  }
}

/** 加载市场全部在售绿色资产（同时驱动「我的挂牌」派生数据） */
const loadMarket = async () => {
  try {
    const r: any = await ecoApi.marketItems()
    marketList.value = r?.items || []
  } catch {
    marketList.value = []
  }
}

/* ==================== 计算属性 ==================== */
/** 合约状态卡片列表（兼容后端返回的数组或对象） */
const contractList = computed(() => {
  const base = [
    { key: 'GreenEnergy',      statusKey: 'green_energy',      name: 'GreenEnergy',      standard: 'ERC20',   tagClass: 'info' },
    { key: 'PlantCertificate', statusKey: 'plant_certificate', name: 'PlantCertificate', standard: 'ERC721',  tagClass: 'accent' },
    { key: 'EcoBadge',         statusKey: 'eco_badge',         name: 'EcoBadge',         standard: 'ERC1155', tagClass: 'warn' },
  ]
  const src = contractStatus.value || {}
  // 兼容数组形式
  const arr = Array.isArray(src) ? src : []
  const findByKey = (k: string, sk: string) =>
    arr.find((x: any) => x.name === k || x.key === k || x.contract === k) ||
    (Array.isArray(src) ? null : (src[sk] || src[k]))
  return base.map((b) => {
    const r = findByKey(b.key, b.statusKey) || {}
    return {
      ...b,
      deployed: !!r.deployed,
      address: r.address || r.contract_address || '',
    }
  })
})

const deployedCount = computed(() => contractList.value.filter((c) => c.deployed).length)
const allDeployed = computed(() => deployedCount.value === 3)

/** 当前发放目标角色的能量发放动作 */
const currentEnergyAction = computed(() => {
  const m = roleMeta(activeIssueRole.value?.key || currentRole.value?.role_key)
  return {
    label: m?.action ? `${m.icon} ${m.action}` : '发放能量',
    amount: m?.amount || 0,
  }
})

/** 能量计价提示（真实商业：达成门槛给基础分，超量按量加成，单次封顶）
 *  公式单一来源 = @/utils/energy（与后端 calc_energy_points 对齐），本页不重写一份 */
const pointsHint = (rule: any): string => energyRuleHint(rule)

/** 本节点发行授信（工作台聚合：防「发行量无上限 = 能量无限通胀」） */
const energyQuota = computed<any>(() => workbench.value?.activity?.energy || null)
const energyQuotaText = computed(() => {
  const q = energyQuota.value
  if (!q || Number(q.quota || 0) <= 0) return ''
  return `发行授信 ${q.quota_used}/${q.quota}，剩余 ${q.quota_remaining}`
})
const quotaExhausted = computed(() => {
  const q = energyQuota.value
  return !!q && Number(q.quota || 0) > 0 && Number(q.quota_remaining || 0) <= 0
})

/** 钱包持有的绿色资产统一视图（证书 ERC721 + 勋章/骑行券 ERC1155，仅当前钱包持有项）。
 * 数据复用已加载的 certificates / badges（不再按 ERC 标准分块，也不重复请求 /wallet 聚合接口），
 * owner 比较统一小写口径，与页面其余归属判断一致 */
const walletAssets = computed(() => {
  const w = (wallet.value || '').toLowerCase()
  const owned = (owner: any) => String(owner || '').toLowerCase() === w
  const certs = certificates.value.filter((c) => owned(c.owner)).map((c: any) => ({
    key: `cert_${c.id}`,
    icon: '🌱',
    name: c.species_name || c.name || '植树证书',
    standard: 'ERC721',
    idText: `ID: ${c.token_id}`,
    listed: isListed('certificate', Number(c.id)),
  }))
  const bdg = badges.value.filter((b: any) => owned(b.owner)).map((b: any) => {
    const t = b.badge_type === 'voucher' ? 'voucher' : 'badge'
    return {
      key: `${t}_${b.id}`,
      icon: badgeLabel(b.badge_type).icon,
      name: b.name || badgeLabel(b.badge_type).name,
      standard: 'ERC1155',
      idText: `ID: ${b.token_id}`,
      listed: isListed(t, Number(b.id)),
    }
  })
  return [...certs, ...bdg]
})

/* ==================== 工具函数 ==================== */
const short = (h: string) => (h ? (h.length > 16 ? h.slice(0, 10) + '...' + h.slice(-4) : h) : '-')

const copyAddr = async (addr: string) => {
  if (!addr) return
  try {
    await navigator.clipboard.writeText(addr)
    ElMessage.success('地址已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

/* ==================== 数据加载 ==================== */
const loadRoles = async () => {
  try {
    const r: any = await ecoApi.roles()
    roles.value = r?.items || r || []
    // 同一份后端数据同时喂给钱包 store：顶栏钱包选项 / 地址↔角色映射与本页共用一张表
    wallets.setRoles(roles.value)
  } catch {
    roles.value = []
  }
}

const loadCurrentRole = async () => {
  try {
    // 地址↔角色映射是身份联动的前提：未就绪时先拉一次（loadRoles 已喂过则直接返回）
    await wallets.ensureRoles()
    let r: any = await ecoApi.currentRole(wallet.value)
    // 后端未记录角色，但当前钱包是某机构地址 → 身份按机构角色收敛（组织钱包恒为其自身角色）
    const autoRole = wallets.roleKeyOf(wallet.value)
    if (!r?.role_key && autoRole) {
      await ecoApi.selectRole(wallet.value, autoRole)
      r = await ecoApi.currentRole(wallet.value)
    }
    currentRole.value = r
    app.setCurrentRole(r)
  } catch {
    currentRole.value = null
    app.setCurrentRole(null)
  }
}

const loadContractStatus = async () => {
  try {
    contractStatus.value = await ecoApi.contractStatus()
  } catch {
    contractStatus.value = {}
  }
}

/** 职能矩阵与本人能力位（业务项显隐的唯一数据源；角色卡的职能摘要也取自这里） */
const loadDuties = async () => {
  dutiesLoading.value = true
  try {
    duties.value = await ecoApi.rolesDuties(wallet.value)
  } catch {
    duties.value = null
  } finally {
    dutiesLoading.value = false
  }
}

/** 能量国库视图：仅治理职能请求（其余身份不拉总量台账，页面上也不出现这张卡） */
const loadTreasury = async () => {
  if (!canViewTreasury.value) {
    treasury.value = null
    return
  }
  try {
    const r: any = await ecoApi.treasuryOverview(wallet.value)
    treasury.value = r
    // 默认销毁量 = 可销毁上限（不超出，避免提交后才报错）
    burnForm.amount = Number(r?.pending_burn_cap ?? 0)
  } catch {
    treasury.value = null
  }
}

/** 治理：账本 → 链上能量一键对账（幂等；后端启动时已自动跑一次）*/
const reconciling = ref(false)
const reconcileNote = ref('')
const reconcileChainEnergy = async () => {
  reconciling.value = true
  try {
    const r: any = await ecoApi.reconcileEnergyChain()
    const items: any[] = r?.items || []
    const bad = items.filter((x) => !x.ok)
    if (r?.total === 0) {
      reconcileNote.value = '台账里没有任何能量余额，无需对账'
    } else if (bad.length) {
      reconcileNote.value = `${items.length} 个钱包中有 ${bad.length} 个补齐失败`
      ElMessage.error(`能量对账失败 ${bad.length} 个：${bad[0]?.detail || '请查看联盟链服务日志'}`)
    } else {
      reconcileNote.value = `已核对 ${items.length} 个钱包，补齐 ${r?.aligned ?? 0} 个 / ${r?.minted_total ?? 0} 点`
      ElMessage.success(`能量对账完成：补齐 ${r?.aligned ?? 0} 个钱包共 ${r?.minted_total ?? 0} 点`)
    }
    await Promise.all([loadEnergyBalance(), loadTreasury(), loadEnergyFlows()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '能量对账失败')
  } finally {
    reconciling.value = false
  }
}

/** 国库销毁（不可逆：能量退出流通、总供应下降）*/
const submitBurn = async () => {
  const cap = Number(treasury.value?.pending_burn_cap ?? 0)
  if (!burnForm.amount || burnForm.amount <= 0) {
    ElMessage.warning('请输入销毁数量')
    return
  }
  if (burnForm.amount > cap) {
    ElMessage.warning(`本次可销毁上限 ${cap}（只能销毁已回收未销毁的能量）`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `销毁 ${burnForm.amount} 点能量后将从链上总供应量中扣除，不可撤销。是否继续？`,
      '国库能量销毁', { type: 'warning', confirmButtonText: '确认销毁', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  burning.value = true
  try {
    const r: any = await ecoApi.treasuryBurn({ wallet: wallet.value, amount: burnForm.amount, note: burnForm.note })
    ElMessage.success(`已销毁 ${r?.amount ?? burnForm.amount} 点能量，净发行量降至 ${r?.net_issuance ?? '-'}`)
    logEco('energy', 'treasury_burn', 'success',
      `国库销毁 ${burnForm.amount} 点，累计已销毁 ${r?.total_burned ?? '-'}，销毁率 ${r?.burn_rate ?? '-'}%`)
    burnForm.note = ''
    await Promise.all([loadTreasury(), loadEnergyBalance(), loadEnergyFlows()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '国库销毁失败'
    ElMessage.error(msg)
    logEco('energy', 'treasury_burn', 'error', msg, safeErrDetail(e))
  } finally {
    burning.value = false
  }
}

const loadEnergyBalance = async () => {
  try {
    // 后端统一口径：balance = 能量账本净额（钱包页 / 联盟页 / 兑换前置校验同一个数），
    // 并随附 chain_balance / needs_sync / sync_gap 供展示差异
    const r: any = await ecoApi.energyBalance(wallet.value)
    energyBalance.value = Number(r?.balance ?? r ?? 0)
    energyKnown.value = true
    energySyncGap.value = r?.needs_sync ? Number(r?.sync_gap ?? 0) : 0
  } catch (e: any) {
    energyBalance.value = 0
    energyKnown.value = false
    energySyncGap.value = 0
    ElMessage.error(`绿色能量余额获取失败：${e?.response?.data?.detail || e?.message || '请稍后重试'}`)
  }
}

const loadEnergyRecords = async () => {
  // 视角按当前身份的职能决定；发行台账按发行方组织钱包查（本人钱包扮演时也是机构在发）
  const by = recordsView.value
  const target = by === 'issuer' ? (identityOrgWallet.value || wallet.value) : wallet.value
  try {
    // 节点台账要尽量覆盖全量发行明细，取 100 条；居民自己的获取记录默认 50 条已足
    const r: any = await ecoApi.energyRecords(target, by, by === 'issuer' ? 100 : undefined)
    energyRecords.value = r?.items || (Array.isArray(r) ? r : [])
    energyTotalPoints.value = Number(r?.total_points || 0)
    energyTotalCount.value = Number(r?.total_count || 0)
  } catch {
    energyRecords.value = []
    energyTotalPoints.value = 0
    energyTotalCount.value = 0
  }
}

/** 能量流水账（有符号变动）：余额的唯一事实源，可看到发行 / 回收 / 市场转让 / 销毁 */
const loadEnergyFlows = async () => {
  try {
    const r: any = await ecoApi.energyFlows(wallet.value, 30)
    energyFlows.value = r?.items || []
    flowBalance.value = Number(r?.balance ?? 0)
  } catch {
    energyFlows.value = []
    flowBalance.value = 0
  }
}

const loadTrees = async () => {
  try {
    const r: any = await ecoApi.trees()
    trees.value = r?.items || r || []
  } catch {
    trees.value = []
  }
}

const loadCertificates = async () => {
  try {
    const r: any = await ecoApi.certificates(wallet.value)
    certificates.value = r?.items || r || []
  } catch {
    certificates.value = []
  }
}

const loadBadges = async () => {
  // 发行方视角同样按机构钱包（issued_by）查，持有视角按当前钱包（owner）查
  const by = badgesView.value
  const target = by === 'issued' ? (identityOrgWallet.value || wallet.value) : wallet.value
  try {
    const r: any = await ecoApi.badges(target, by)
    badges.value = r?.items || (Array.isArray(r) ? r : [])
  } catch {
    badges.value = []
  }
}

/* ==================== 角色工作台（职责 / 权限位 / 活动统计 / 待办） ==================== */
const wbActive = ref<string[]>(['wb'])
const workbench = ref<any>(null)
const wbLoading = ref(false)

/** 加载当前角色的工作台聚合数据（角色未选时不请求） */
const loadWorkbench = async () => {
  const rk = currentRole.value?.role_key
  if (!rk) {
    workbench.value = null
    return
  }
  wbLoading.value = true
  try {
    workbench.value = await ecoApi.roleWorkbench(rk, wallet.value)
  } catch {
    workbench.value = null
  } finally {
    wbLoading.value = false
  }
}

/** 进页先收敛钱包：旧 localStorage 里可能是 0xlearner / stu:xxx / user_id（都不再
 *  是合法钱包）→ 能解成机构地址就解，否则回落本人地址；解不动就保持原值，
 *  由顶栏的联动校验再收一次（不能在这里把人抢回默认钱包）。*/
const convergeWallet = async () => {
  await wallets.ensureRoles()
  const cur = normAddr(wallet.value)
  if (cur && isChainAddress(cur)) return
  const resolved = wallets.normalize(cur) || wallets.myAddress
  if (resolved && resolved !== cur) app.setWallet(resolved)
}

const _loadAllOnce = async () => {
  loading.value = true
  try {
    // 角色表先行：地址↔角色映射是钱包收敛与身份联动的前提
    await loadRoles()
    await convergeWallet()
    // 身份先行：能力位（卡片显隐）、台账视角、国库是否该请求都依赖它，需早于业务请求就绪
    await Promise.all([loadCurrentRole(), loadDuties()])
    await Promise.all([
      loadContractStatus(),
      loadEnergyBalance(),
      loadEnergyRecords(),
      loadEnergyFlows(),
      loadTrees(),
      loadCertificates(),
      loadBadges(),
      loadBadgeTypes(),
      loadMarket(),
      loadTreasury(),
    ])
    // 工作台依赖 currentRole，需在角色加载完成后请求
    await loadWorkbench()
  } finally {
    loading.value = false
  }
}

/* 钱包切换走 store watcher、选角色又显式 loadAll，两者会重叠发一轮 12 个请求；
   这里做“运行中只记一次脏、跑完补跑一轮”的合并，避免旧钱包的请求覆盖新结果。*/
let _loadAllRunning = false
let _loadAllDirty = false
const loadAll = async () => {
  if (_loadAllRunning) {
    _loadAllDirty = true
    return
  }
  _loadAllRunning = true
  try {
    do {
      _loadAllDirty = false
      await _loadAllOnce()
    } while (_loadAllDirty)
  } finally {
    _loadAllRunning = false
  }
}

/* ==================== 事件处理 ==================== */
/** 记录操作审计日志（成功/失败/警告）。失败时静默忽略，不阻塞主流程 */
const logEco = async (
  module_: 'role' | 'energy' | 'tree' | 'certificate' | 'badge' | 'contract' | 'other',
  action: string,
  level: 'success' | 'warn' | 'error' | 'info',
  message: string,
  detail = '',
) => {
  try {
    await ecoApi.recordLog({
      // 不再写 'unknown' 这类脏占位：空钱包由后端按 JWT 本人地址归一
      wallet: wallet.value,
      module: module_,
      action,
      level,
      message,
      detail,
    })
  } catch {
    /* 日志写入失败不影响主流程 */
  }
}

/** 钱包联动身份：当前操作地址对应的联盟角色 key（空 = 本人钱包 / 未登记地址） */
const walletRoleKey = computed<string>(() => wallets.roleKeyOf(wallet.value))
/** 该地址是否就是当前操作钱包（角色卡的「操作中」高亮） */
const isOperatingWith = (address: string) =>
  !!address && normAddr(address) === normAddr(wallet.value)
/** 当前钱包已记录的角色（eco_role_selections） */
const isRoleActive = (key: string) => currentRole.value?.role_key === key

/** 当前身份对应的后端角色定义（机构钱包操作 = 该机构；本人钱包扮演 = 已选角色）：
 *  直接取 /api/eco/roles 的角色对象，energy_rule / issues_assets 就是职能口径 */
const identityRoleDef = computed<any>(() => {
  const rk = walletRoleKey.value || currentRole.value?.role_key || ''
  if (!rk) return null
  return roles.value.find((x: any) => (ROLE_KEY_ALIAS[x.key] || x.key) === rk) || null
})
/** 本身份的发行方组织钱包（发行台账按发行方记账，本人钱包扮演时也要查机构地址） */
const identityOrgWallet = computed<string>(() => {
  const addr = normAddr(String(identityRoleDef.value?.address || ''))
  return isChainAddress(addr) ? addr : ''
})
/** 能量台账视角：身份有能量发行职能 → 看本节点发行列表；否则（居民）→ 看我的获取列表。
 *  库里两侧地址分属 issuer_wallet / wallet，用接收方口径查节点永远为空表。*/
const recordsView = computed<'receiver' | 'issuer'>(() =>
  (identityRoleDef.value?.energy_rule ? 'issuer' : 'receiver'))
/** 勋章 / 骑行券台账视角：对应资产的发行节点 → 看本节点发行·发放清单；居民 → 看我持有 */
const badgesView = computed<'owner' | 'issued'>(() => {
  const assets: string[] = identityRoleDef.value?.issues_assets || []
  return assets.includes('badge') || assets.includes('voucher') ? 'issued' : 'owner'
})

/** 综合钱包的可查钱包 = 与顶栏选择器同一张候选表（本人 + 联盟机构地址）；
 *  手输任意地址已无意义：后端 _ensure_viewable_wallet 只放行本人候选集与演示钱包。*/
const walletOptions = computed(() => {
  const opts: { addr: string; label: string }[] = []
  const mine = wallets.myAddress
  if (mine) opts.push({ addr: mine, label: '💼 我的钱包（普通用户）' })
  for (const a of wallets.alliance) {
    if (a.address === mine) continue   // 本人就是该机构账号：不重复列一项
    opts.push({
      addr: a.address,
      label: `${a.icon} ${a.name} · 组织钱包${a.alias ? `（${a.alias}）` : ''}`,
    })
  }
  const cur = normAddr(wallet.value)
  if (cur && !opts.some((w) => w.addr === cur)) {
    opts.push({ addr: cur, label: '未登记钱包（按地址访问）' })
  }
  return opts
})
/** 钱包下拉读写：写侧统一走 setWallet，保证顶栏与本页联动刷新不被绕过 */
const walletModel = computed<string>({
  get: () => wallet.value,
  set: (v: string) => setWallet(v),
})
/** 当前查的是不是本人钱包（决定综合钱包说「我的」还是「组织钱包」） */
const isMyWallet = computed(() =>
  !!wallets.myAddress && normAddr(wallet.value) === normAddr(wallets.myAddress))

/** 当前查看的钱包若属于某发行节点：它的可用能量不是链上余额
 *  （发行方钱包不收能量、只向外发行，balanceOf 恒为 0），
 *  而是联盟授予的**发行授信余量** = energy_quota - energy_issued。 */
const creditInfo = computed(() => {
  const addr = normAddr(wallet.value)
  if (!addr) return null
  const api: any = roles.value.find((r: any) => normAddr(r.address || '') === addr) || null
  if (!api) return null
  const quota = Number(api.energy_quota || 0)
  const issued = Number(api.energy_issued || 0)
  return {
    name: String(api.name || ''),
    quota,
    issued,
    remaining: Math.max(0, quota - issued),
  }
})

/** 能量余额格：发行节点组织钱包看授信余量，其余（居民 / 管理员国库钱包）看真实持仓。
 *  管理员钱包不发行能量但确实是能量国库的持有方，不能拿「—」把真实余额藏掉。 */
const energyTile = computed(() => {
  const c = creditInfo.value
  if (!isMyWallet.value && c && c.quota > 0) {
    return {
      label: '授信能量余额',
      num: c.remaining,
      sub: `${c.name}发行授信 ${c.issued} / ${c.quota}（发行方钱包不接收能量，可用额度即授信余量）`,
    }
  }
  return {
    label: '绿色能量余额',
    num: energyKnown.value ? energyBalance.value : '—',
    sub: !energyKnown.value
      ? '余额查询失败，请刷新重试（不拦兑换，提交后会给出真实失败原因）'
      : (isMyWallet.value ? 'GreenEnergy (ERC20) · 能量台账净额' : 'GreenEnergy (ERC20) · 能量台账净额（管理员钱包即能量国库回收量）')
      + (energySyncGap.value > 0 ? ` · 链上待同步 ${energySyncGap.value} 点（兑换时自动补齐）` : ''),
  }
})

/** 本节点维护的 ERC1155 类型（发行方视角的台账，issuer_role 由后端写入） */
const myIssuedTypes = computed<any[]>(() => {
  const rk = identityRoleDef.value?.key
  if (!rk) return []
  return badgeTypes.value.filter((bt: any) => (bt.issuer_role || '') === rk)
})
/** 治理视角：本机构累计签发的植树证书数（Σ 各种已签发，与「一证一树」同口径） */
const certIssuedTotal = computed<number>(() =>
  trees.value.reduce((s: number, t: any) => s + (Number(t.issued) || 0), 0))
/** 铸造发放的接收方候选：绿色资产只能发给居民钱包（后端硬拦机构地址），
 *  故只预置本人钱包，其余靠 allow-create 粘贴真实地址，不再预填 0xresident 这种解不到的别名 */
const mintTargetOptions = computed(() => {
  const opts: { addr: string; label: string }[] = []
  const mine = wallets.myAddress
  if (mine) opts.push({ addr: mine, label: '👨‍🎓 我的钱包（本人 · 居民身份）' })
  const cur = normAddr(mintToWallet.value)
  if (isChainAddress(cur) && !opts.some((w) => w.addr === cur)) {
    opts.push({ addr: cur, label: '已填写的居民钱包' })
  }
  return opts
})
// 本人地址是登录后才下发的：首次拿到时把它作为铸造接收方的默认值
watch(() => wallets.myAddress, (v) => {
  if (v && !mintToWallet.value) mintToWallet.value = v
}, { immediate: true })

/** 身份摘要（顶栏钱包 / 角色卡两处的身份标签共用同一个口径） */
const identityKey = computed(() => currentRole.value?.role_key || walletRoleKey.value || '')
const identityName = computed(() =>
  roleMeta(identityKey.value)?.name || duties.value?.identity?.role_name || '普通用户')
const identityIcon = computed(() => roleMeta(identityKey.value)?.icon || '👨‍🎓')
const identityProfile = computed(() => duties.value?.identity?.profile
  || (identityKey.value === 'admin' ? 'admin' : (identityKey.value ? 'node' : 'resident')))
/** 角色卡的发行授信进度（无授信上限返回 null，不画进度条） */
function quotaOf(r: any) {
  const quota = Number(r?.quota || 0)
  if (quota <= 0) return null
  const used = Number(r?.issued || 0)
  return {
    used, quota,
    pct: Math.min(100, Math.round((used / quota) * 100)),
    exhausted: used >= quota,
  }
}

/** 选角色（默认同时把操作钱包切到该机构的真实地址，保证钱包=角色=身份一致）
 *  keepMyWallet=true：只在本人钱包上「角色扮演」（后端允许，但会另外留操作人痕迹） */
const selectRole = async (role_key: string, keepMyWallet = false) => {
  const r: any = roleList.value.find((x: any) => x.key === role_key)
  const orgAddr = String(r?.address || '')
  const target = (!keepMyWallet && isChainAddress(orgAddr)) ? orgAddr : normAddr(wallet.value)
  if (!target) {
    ElMessage.warning('未获取到可用钱包地址，请重新登录后再试')
    return
  }
  const switching = target !== normAddr(wallet.value)
  const title = `${r?.icon || ''} ${r?.name || role_key}`
  try {
    await ElMessageBox.confirm(
      keepMyWallet
        ? `以「我的钱包」扮演「${title}」？\n实训演示：发放与铸造仍会使用该角色的组织钱包，但操作记录会留存你的本人钱包作为操作人。`
        : (switching
            ? `切换为「${title}」并以该机构组织钱包 ${shortAddr(target)} 操作？\n顶栏「当前操作钱包」会同步跟随，业务项按该身份职能刷新。`
            : `确认以「${title}」的组织钱包操作？`),
      '角色切换',
      { confirmButtonText: '确认切换', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消
  }
  try {
    // 先切钱包（顶栏选项 / 高亮立即跟随），再绑角色；watcher 触发的重复 loadAll 已做合并
    if (switching) app.setWallet(target)
    await ecoApi.selectRole(target, role_key)
    ElMessage.success(switching ? `已以「${r?.name}」组织钱包操作：${shortAddr(target)}` : `已选择角色：${r?.name}`)
    logEco('role', 'select_role', 'success',
      `选择角色：${r?.name} (${role_key}) @ ${target}`)
    // 切角色后全量刷新：角色、余额、记录、钱包、合约状态都需联动
    await loadAll()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '角色切换失败'
    ElMessage.error(msg)
    logEco('role', 'select_role', 'error', msg, safeErrDetail(e))
    // 钱包已切但角色绑定失败：回一次全量加载，避免页面停在半切换状态
    if (switching) await loadAll()
  }
}

/* ==================== 普通用户（低碳居民）角色卡片 ==================== */
/** 「我的钱包」= 登录账号本人的真实链上地址（一人一钱包）；
 *  旧会话缓存里的 stu:xxx / user_id 不再被当成钱包（返回空→卡片提示重新登录） */
const myWalletAddr = computed(() => wallets.myAddress)
/** 当前钱包是否为联盟角色钱包（组织钱包恒为其自身角色，不靠本地别名表） */
const isAllianceRoleWallet = computed(() => !!walletRoleKey.value)
/** 普通用户 = 当前钱包未选择任何联盟角色（联盟角色钱包会自动联动角色，排除在外） */
const residentActive = computed(() => !currentRole.value?.role_key && !isAllianceRoleWallet.value)
/** 居民卡的「操作中」：本身就是以本人钱包操作，与联盟卡的组织钱包高亮同一口径 */
const residentOperating = computed(() => residentActive.value && isOperatingWith(myWalletAddr.value))

/** 选择普通用户：回到本人钱包并清除联盟角色选择 */
const selectResident = async () => {
  const mine = myWalletAddr.value
  if (!mine) {
    ElMessage.warning('未获取到本人链上地址，请重新登录后再试')
    return
  }
  if (residentActive.value && normAddr(wallet.value) === mine) return
  const toMyWallet = normAddr(wallet.value) !== mine
  try {
    await ElMessageBox.confirm(
      toMyWallet
        ? `切换为「普通用户」身份？当前处于联盟角色钱包，将切换到「我的钱包」${shortAddr(mine)} 并清除已选的联盟角色。`
        : `切换为「普通用户」身份？将清除当前钱包（${shortAddr(mine)}）已选的联盟角色。`,
      '普通用户',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消
  }
  try {
    if (toMyWallet) app.setWallet(mine)
    await ecoApi.clearRole(mine)
    ElMessage.success('已切换为普通用户（我的钱包）')
    logEco('role', 'select_resident', 'success', `切换为普通用户（我的钱包 ${mine}）`)
    await loadAll()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '切换普通用户失败'
    ElMessage.error(msg)
    logEco('role', 'select_resident', 'error', msg, safeErrDetail(e))
  }
}

/** 上架树种（具备目录治理职能的身份） */
const addTree = async () => {
  if (!treeForm.name) {
    ElMessage.warning('请填写树种名称')
    logEco('tree', 'add_tree', 'warn', '新增树种未填写名称')
    return
  }
  if (treeForm.required_energy < 1000) {
    ElMessage.warning('所需能量不能低于 1000')
    logEco('tree', 'add_tree', 'warn', `树种所需能量 ${treeForm.required_energy} < 1000`)
    return
  }
  if (treeForm.supply < 0) {
    ElMessage.warning('发行额度不能为负')
    logEco('tree', 'add_tree', 'warn', `树种发行额度 ${treeForm.supply} < 0`)
    return
  }
  addingTree.value = true
  try {
    await ecoApi.addTree({ ...treeForm, wallet: wallet.value })
    ElMessage.success('树种添加成功')
    logEco('tree', 'add_tree', 'success',
      `治理上架树种：${treeForm.name}，需 ${treeForm.required_energy} 能量，发行额度 ${treeForm.supply || '不限'}`)
    treeForm.name = ''
    treeForm.required_energy = 1000
    treeForm.supply = 100
    treeForm.image_url = ''
    treeForm.description = ''
    await Promise.all([loadTrees(), loadTreasury()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '树种添加失败'
    ElMessage.error(msg)
    logEco('tree', 'add_tree', 'error', msg, safeErrDetail(e))
  } finally {
    addingTree.value = false
  }
}

/** 兑换按钮文案：按职能与额度给出可执行的下一步，而不是统一报「余额不足」 */
const treeBtnText = (t: any): string => {
  if (!canExchange.value) return '仅需求方（居民）可兑换'
  if (t.status === 'off') return '已下架'
  if (t.sold_out) return '发行额度已用尽'
  if (energyShort(t.required_energy)) return `需 ${t.required_energy} 能量`
  return '兑换植树证书'
}

/** 治理：上调树种发行额度（ERC721 一证一树，额度只增不减） */
const raiseTreeSupply = async (t: any) => {
  let value: number
  try {
    const r: any = await ElMessageBox.prompt(
      `已签发 ${t.issued ?? 0} 份。新额度不得低于已签发量（发行额度只可上调）。`,
      `上调「${t.name}」发行额度`,
      { inputValue: String((t.remaining < 0 ? t.issued : t.supply) + 50), inputPattern: /^\d+$/, inputErrorMessage: '请输入非负整数' },
    )
    value = Number(r?.value)
  } catch {
    return
  }
  try {
    await ecoApi.updateTree({ species_id: t.id, wallet: wallet.value, supply: value })
    ElMessage.success(`「${t.name}」发行额度已上调至 ${value}`)
    logEco('tree', 'update_tree', 'success', `上调 ${t.name} 发行额度至 ${value}`)
    await Promise.all([loadTrees(), loadTreasury()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '额度调整失败'
    ElMessage.error(msg)
    logEco('tree', 'update_tree', 'error', msg, safeErrDetail(e))
  }
}

/** 治理：下架 / 重新上架树种（只影响后续可兑性，已发证书不可变） */
const toggleTreeStatus = async (t: any) => {
  const next = t.status === 'off' ? 'active' : 'off'
  try {
    await ElMessageBox.confirm(
      next === 'off'
        ? `下架「${t.name}」后居民不可再兑换该树种，已签发的 ${t.issued ?? 0} 份证书不受影响。`
        : `重新上架「${t.name}」，居民可在剩余额度内继续兑换。`,
      next === 'off' ? '下架树种' : '上架树种', { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await ecoApi.updateTree({ species_id: t.id, wallet: wallet.value, status: next })
    ElMessage.success(next === 'off' ? '已下架' : '已重新上架')
    logEco('tree', 'update_tree', 'success', `${next === 'off' ? '下架' : '上架'}树种 ${t.name}`)
    await loadTrees()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '状态调整失败'
    ElMessage.error(msg)
    logEco('tree', 'update_tree', 'error', msg, safeErrDetail(e))
  }
}

/** 按树种名称匹配证书图片（树种配置的 image_url） */
const treeImageOf = (speciesName?: string) => {
  if (!speciesName) return ''
  const t = trees.value.find((x) => x.name === speciesName)
  return t?.image_url || ''
}

/** 兑换植树证书 */
const exchangeCertificate = async (species_id: number) => {
  if (!canExchange.value) {
    ElMessage.warning(denyTip(CAP.exchange))
    return
  }
  exchangingTree.value = species_id
  try {
    const species = trees.value.find(t => t.id === species_id)
    await ecoApi.exchangeCertificate(wallet.value, species_id)
    ElMessage.success('植树证书兑换成功 🌱')
    logEco('certificate', 'exchange_cert', 'success',
      `兑换：${species?.name ?? '未知树种'}（species_id=${species_id}）`)
    await Promise.all([loadEnergyBalance(), loadCertificates(), loadTrees(), loadTreasury(), loadEnergyFlows()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '证书兑换失败'
    ElMessage.error(msg)
    logEco('certificate', 'exchange_cert', 'error',
      `${msg} (species_id=${species_id})`, safeErrDetail(e))
  } finally {
    exchangingTree.value = null
  }
}

/* ==================== 生命周期 ==================== */
/* 首次进入触发 onMounted，KeepAlive 缓存后再次进入触发 onActivated，两者都执行加载 */
onMounted(loadAll)
onActivated(loadAll)
</script>

<style scoped lang="scss">
.eco {
  /* 通用间距 */
}

/* ---- 顶部学习引导（通用） ---- */
.guide-card { margin-bottom: 14px; }
.guide-head { margin-bottom: 14px; }
.guide-title {
  display: inline-flex; align-items: center; gap: 10px;
  font-size: 16px; font-weight: 700; color: var(--dq-text);
}
.g-icon { font-size: 20px; }
.guide-desc {
  margin-top: 10px; font-size: 13px; color: var(--dq-text-dim);
  line-height: 1.7; max-width: 920px;
  b { color: var(--dq-primary); font-weight: 600; }
}
.dq-tag-lg { font-size: 11px; padding: 3px 10px; border-radius: 4px; }

/* ---- 商业流程总览（5步闭环） ---- */
.biz-flow {
  display: grid;
  grid-template-columns: 1fr 24px 1fr 24px 1fr 24px 1fr 24px 1fr;
  gap: 4px;
  align-items: stretch;
  margin-top: 14px;
  .biz-step {
    padding: 12px 12px;
    background: linear-gradient(135deg, rgba(0,230,195,0.05), rgba(0,230,195,0.01));
    border: 1px solid var(--dq-border);
    border-radius: 8px;
    display: flex; gap: 10px; align-items: flex-start;
    transition: all .2s;
    &:hover { border-color: rgba(0,230,195,0.4); transform: translateY(-1px); }
  }
  .bs-no {
    flex-shrink: 0;
    width: 30px; height: 30px; border-radius: 7px;
    background: var(--dq-grad-primary); color: #062b25;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: var(--dq-mono); font-weight: 700; font-size: 12px;
    box-shadow: 0 0 10px var(--dq-primary-glow);
  }
  .bs-info { flex: 1; min-width: 0; }
  .bs-title { font-weight: 600; color: var(--dq-text); font-size: 13px; margin-bottom: 4px; }
  .bs-desc {
    font-size: 11px; color: var(--dq-text-dim); line-height: 1.55;
  }
  .biz-arrow {
    display: flex; align-items: center; justify-content: center;
    color: var(--dq-primary); font-size: 16px; font-weight: 700;
    opacity: 0.6;
  }
}
@media (max-width: 1180px) {
  .biz-flow {
    grid-template-columns: 1fr;
    .biz-arrow { transform: rotate(90deg); height: 16px; }
  }
}

/* ---- 旧的 flow 样式（保留以兼容其他卡片） ---- */
.flow {
  display: grid; grid-template-columns: 1fr 32px 1fr 32px 1fr; gap: 6px;
  align-items: stretch;
  .flow-step {
    padding: 14px 16px;
    background: linear-gradient(135deg, rgba(0,230,195,0.05), rgba(0,230,195,0.01));
    border: 1px solid var(--dq-border);
    border-radius: 8px;
    display: flex; gap: 12px; align-items: flex-start;
    transition: all .2s;
    &:hover { border-color: var(--dq-border-2); transform: translateY(-1px); }
  }
  .fs-no {
    flex-shrink: 0;
    width: 36px; height: 36px; border-radius: 8px;
    background: var(--dq-grad-primary); color: #062b25;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: var(--dq-mono); font-weight: 700; font-size: 14px;
    box-shadow: 0 0 10px var(--dq-primary-glow);
  }
  .fs-info { flex: 1; min-width: 0; }
  .fs-title { font-weight: 600; color: var(--dq-text); font-size: 14px; margin-bottom: 4px; }
  .fs-desc {
    font-size: 12px; color: var(--dq-text-dim); line-height: 1.6; margin-bottom: 6px;
    b { color: var(--dq-primary); font-weight: 500; }
  }
  .fs-tags { display: flex; gap: 4px; flex-wrap: wrap; }
  .fs-kw {
    font-family: var(--dq-mono);
    font-size: 10px; color: var(--dq-primary);
    background: rgba(0,230,195,0.1);
    padding: 1px 6px; border-radius: 3px;
    border: 1px solid rgba(0,230,195,0.22);
    &.accent { color: var(--dq-accent); background: rgba(245,55,155,0.08); border-color: rgba(245,55,155,0.22); }
    &.muted  { color: var(--dq-text-dim); background: rgba(123,138,171,0.1); border-color: rgba(123,138,171,0.2); }
  }
  .flow-arrow {
    display: flex; align-items: center; justify-content: center;
    color: var(--dq-border-strong); font-size: 18px; font-weight: 700;
  }
}
@media (max-width: 1180px) {
  .flow { grid-template-columns: 1fr;
    .flow-arrow { transform: rotate(90deg); height: 20px; }
  }
}

/* ---- 角色工作台 ---- */
.wb-collapse {
  border: none;
  :deep(.el-collapse-item__header) {
    font-size: 13px;
    color: var(--dq-text-dim);
    background: transparent;
    border-bottom: 1px solid var(--dq-border);
  }
  :deep(.el-collapse-item__wrap) {
    background: transparent;
    border-bottom: none;
  }
  :deep(.el-collapse-item__content) { padding-bottom: 6px; }
}
.wb-title { font-size: 13px; }
.wb-head { margin-bottom: 12px; }
.wb-desc {
  font-size: 13px; color: var(--dq-text-dim); line-height: 1.7; margin-bottom: 8px;
}
.wb-perms { display: flex; gap: 8px; flex-wrap: wrap; }
.wb-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
  margin-bottom: 14px;
}
.wb-stat {
  padding: 12px 14px;
  .ws-label { font-size: 12px; color: var(--dq-text-dim); }
  .ws-num {
    font-size: 24px; font-weight: 700; color: var(--dq-primary);
    font-family: var(--dq-mono); margin-top: 4px;
    em { font-style: normal; font-size: 12px; font-weight: 400; }
  }
  .ws-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 4px; }
}
@media (max-width: 900px) {
  .wb-stats { grid-template-columns: 1fr; }
}
.wb-todos { margin-top: 4px; }
.wb-todo {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 12px; margin-bottom: 8px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  transition: border-color .2s;
  &:hover { border-color: rgba(0, 230, 195, 0.4); }
  .wt-dot {
    flex-shrink: 0;
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--dq-primary); margin-top: 6px;
    box-shadow: 0 0 6px var(--dq-primary-glow);
  }
  .wt-body { flex: 1; min-width: 0; }
  .wt-title { font-size: 13px; font-weight: 600; color: var(--dq-text); }
  .wt-desc {
    font-size: 12px; color: var(--dq-text-dim); margin-top: 2px; line-height: 1.6;
  }
}

/* ---- 区块卡片 ---- */
.section-card { margin-bottom: 14px; }
.sub-title {
  font-size: 13px; margin-bottom: 10px; margin-top: 4px;
}
/* 台账小标题：标题 + 口径 + 笔数 + 累计排一行，不必再在标题下挂一段说明 */
.rec-head {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  font-weight: 600;
}
.dim { color: var(--dq-text-dim); }
.empty-tip {
  color: var(--dq-text-dim); font-size: 13px; text-align: center;
  padding: 24px 12px; line-height: 1.7;
  &.small { padding: 14px 8px; }
}

/* ---- 合约状态卡片 ---- */
.contract-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
}
.contract-card {
  padding: 14px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  transition: all .2s;
  &.deployed {
    border-color: rgba(45,212,191,0.35);
    background: linear-gradient(135deg, rgba(45,212,191,0.06), rgba(45,212,191,0.01));
  }
  &.locked {
    border-color: var(--dq-border);
    opacity: 0.92;
  }
  .cc-head {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px;
  }
  .cc-name {
    display: flex; align-items: center; gap: 6px;
    font-weight: 600; color: var(--dq-text); font-size: 14px;
    .cc-icon { font-size: 16px; }
  }
  .cc-body { font-size: 12px; }
  .cc-addr-label { color: var(--dq-text-dim); margin-bottom: 4px; }
  .cc-addr {
    color: var(--dq-primary); cursor: pointer; word-break: break-all;
    &:hover { text-decoration: underline; }
  }
  .cc-hint {
    color: var(--dq-text-dim); margin-bottom: 8px; line-height: 1.6;
  }
}
.eco-active {
  margin-top: 12px;
  border-color: rgba(45,212,191,0.4) !important;
  .dt-label { color: var(--dq-success); }
}
@media (max-width: 760px) {
  .contract-grid { grid-template-columns: 1fr; }
}

/* ---- 角色选择：7 个身份一排（6 个联盟节点 + 普通用户），逐槽定高保证匀称 ---- */
.role-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
  align-items: stretch;
}
.role-card {
  display: flex; flex-direction: column; gap: 7px;
  min-width: 0;
  padding: 12px 11px 11px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
  transition: transform .2s, border-color .2s, box-shadow .2s, background .2s;
  position: relative;
  &:hover {
    border-color: var(--dq-border-2);
    transform: translateY(-2px);
    box-shadow: var(--dq-shadow);
  }
  /* active = 该地址已记录为当前角色；operating = 顶栏正在以该钱包操作（更强提示） */
  &.active {
    border-color: var(--dq-primary);
    background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(0,230,195,0.02));
  }
  &.operating {
    border-color: var(--dq-primary);
    box-shadow: 0 0 0 1px var(--dq-primary), 0 0 16px var(--dq-primary-glow);
  }
  /* 窄卡靠“每槽定高 + 超出省略”对齐：文案长短不再影响7 张卡之间的基线 */
  .rc-head { display: flex; align-items: center; gap: 8px; height: 32px; }
  .rc-icon {
    width: 30px; height: 30px; flex: none; border-radius: 9px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 17px; border: 1px solid var(--dq-border);
  }
  .rc-id { flex: 1; min-width: 0; }
  .rc-name {
    font-weight: 600; color: var(--dq-text); font-size: 13px; line-height: 1.3;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .rc-profile {
    font-size: 10px; color: var(--dq-text-dim); margin-top: 1px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  /* 徽章行定高：未选中的卡也给“未选用”，7 张卡在这一行的留白才一致 */
  .rc-state {
    display: flex; align-items: center; justify-content: space-between; gap: 4px; height: 20px;
    .dq-tag { flex: none; }
  }
  .rc-play { font-size: 11px; height: 20px; min-height: 20px; padding: 0; flex: none; }
  .rc-desc {
    font-size: 11.5px; color: var(--dq-text-dim); line-height: 1.5; box-sizing: border-box;
    height: 52px;   /* 固定 3 行，完整文案在 title Tooltip */
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
    overflow: hidden;
  }
  .rc-wallet {
    font-size: 11px; line-height: 1.6;
    .rw-line {
      display: flex; align-items: center; justify-content: space-between; gap: 6px; height: 18px;
    }
    .rw-k { color: var(--dq-text-dim); flex: none; }
    .rw-alias {
      color: var(--dq-text-dim); opacity: .7; font-size: 10px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .rw-v {
      display: block; width: 100%; box-sizing: border-box; text-align: center;
      color: var(--dq-primary); padding: 1px 4px; border-radius: 4px;
      background: rgba(0,230,195,0.07); border: 1px solid rgba(0,230,195,0.16);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      &.link { cursor: pointer; &:hover { border-color: var(--dq-primary); } }
    }
  }
  .rc-dims {
    font-size: 11px; color: var(--dq-text-dim); line-height: 1.5; box-sizing: border-box;
    height: 33px;   /* 固定 2 行职能摘要 */
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
    overflow: hidden;
  }
  .rc-rule {
    font-size: 11px; color: var(--dq-primary); line-height: 1.5; box-sizing: border-box;
    background: rgba(0,230,195,0.08);
    padding: 3px 6px; border-radius: 4px;
    border: 1px solid rgba(0,230,195,0.2);
    height: 39px;   /* 固定 2 行发行规则 */
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
    overflow: hidden;
  }
  .rc-quota {
    height: 28px;   /* 无授信的卡也给等高占位（显示“不适用”） */
    .rq-line {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 11px; color: var(--dq-text-dim); margin-bottom: 4px;
      b { color: var(--dq-text); font-weight: 600; &.danger { color: var(--dq-error); } }
      &.dim b { color: var(--dq-text-dim); font-weight: 500; }
    }
    .dq-progress__bar.danger { background: linear-gradient(90deg, var(--dq-error), #ff8aa0); box-shadow: none; }
  }
  .rc-foot {
    margin-top: auto; padding-top: 9px;
    border-top: 1px dashed var(--dq-border);
    .el-button { width: 100%; }
  }
}
/* 普通用户（第 7 张）：槽位与联盟卡完全同构，仅用底色区分「本人钱包」身份 */
.role-resident {
  background: linear-gradient(135deg, rgba(143,214,148,0.07), var(--dq-bg-2) 60%);
  .rr-icon {
    background: rgba(143,214,148,0.16); border-color: rgba(143,214,148,0.45); color: #8fd694;
  }
}
/* 视口收窄时按 4 / 2 / 1 列回落，卡内槽位高度不变，不会再出现错落 */
@media (max-width: 1400px) {
  .role-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 1000px) {
  .role-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 620px) {
  .role-grid { grid-template-columns: 1fr; }
}

/* ---- 能量发放 ---- */
.energy-ops {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 10px;
  padding: 12px 14px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  margin-bottom: 14px;
  .energy-info { font-size: 13px; color: var(--dq-text); b { color: var(--dq-primary); } }
}
.energy-val {
  color: var(--dq-success); font-weight: 700;
}

/* ---- 普通用户（居民）5 种低碳行为获取能量 ---- */
.resident-energy { margin-bottom: 14px; }
.energy-ways {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px; margin-top: 12px;
}
.energy-way-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 14px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  transition: border-color 0.2s;
  &:hover { border-color: var(--dq-primary); }
  .ew-head { display: flex; align-items: center; gap: 8px; }
  .ew-icon { font-size: 20px; }
  .ew-name { font-weight: 600; font-size: 13px; color: var(--dq-text); }
  .ew-points { margin-left: auto; color: var(--dq-success); font-weight: 700; }
  .ew-desc { font-size: 12px; color: var(--dq-text-dim); line-height: 1.5; flex: 1; }
}

/* ---- 角色分工说明 ---- */
.role-sub {
  font-size: 12px; font-weight: normal; color: var(--dq-text-dim); margin-left: 8px;
}

/* ---- 植树证书 ---- */
.tree-layout {
  display: grid; grid-template-columns: 360px 1fr; gap: 14px;
}
.tree-admin { padding: 14px; }
.tree-list { padding: 14px; }
.tree-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px;
}
.tree-item {
  padding: 12px;
  .ti-img {
    width: 100%; height: 96px; object-fit: cover;
    border-radius: 8px; margin-bottom: 8px; background: var(--dq-bg-2);
  }
  .ti-emoji { font-size: 40px; text-align: center; margin-bottom: 8px; }
  .ti-name { font-weight: 600; color: var(--dq-text); font-size: 14px; margin-bottom: 6px; }
  .ti-desc { font-size: 12px; color: var(--dq-text-dim); line-height: 1.5; margin-bottom: 6px; min-height: 32px; }
  .ti-cost { font-size: 12px; color: var(--dq-text); .dq-mono { color: var(--dq-primary); font-weight: 700; } }
}
.cert-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;
}
.cert-item {
  padding: 14px; text-align: center;
  .ci-img {
    width: 100%; height: 110px; object-fit: cover;
    border-radius: 8px; margin-bottom: 8px; background: var(--dq-bg-2);
  }
  .ci-badge { font-size: 36px; margin-bottom: 8px; }
  .ci-name { font-weight: 600; color: var(--dq-text); margin-bottom: 8px; }
  .ci-meta {
    font-size: 11px; color: var(--dq-text-dim); line-height: 1.7; margin-bottom: 8px;
    .owner { margin-top: 2px; }
  }
  .ci-ops {
    margin-top: 8px;
    display: flex; justify-content: center; gap: 6px;
  }
}

/* ---- 挂牌对话框 ---- */
.list-info {
  padding: 12px 14px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  .li-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 0;
    font-size: 13px;
    span:first-child { color: var(--dq-text-dim); }
    b { color: var(--dq-text); font-weight: 600; }
  }
}
@media (max-width: 900px) {
  .tree-layout { grid-template-columns: 1fr; }
}

/* ---- 勋章 / 骑行券 ---- */
.badge-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.badge-card {
  padding: 18px; text-align: center;
  .bc-img {
    width: 72px; height: 72px; object-fit: cover;
    border-radius: 12px; margin: 0 auto 8px; display: block; background: var(--dq-bg-2);
  }
  .bc-icon { font-size: 40px; margin-bottom: 8px; }
  .bc-name { font-weight: 600; color: var(--dq-text); font-size: 15px; margin-bottom: 4px; }
  .bc-desc { font-size: 12px; color: var(--dq-text-dim); margin-bottom: 8px; min-height: 32px; line-height: 1.5; }
  .bc-cost { font-size: 13px; color: var(--dq-text); margin-bottom: 12px; .dq-mono { color: var(--dq-primary); font-weight: 700; } }
  .bc-meta {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; color: var(--dq-text-dim); margin-bottom: 12px;
    .dq-mono { color: var(--dq-primary); font-weight: 700; }
  }
}
.badge-admin, .mint-admin {
  margin-top: 12px;
  padding: 14px;
  background: var(--dq-bg-2);
  border: 1px dashed var(--dq-border-2);
  border-radius: 8px;
}
@media (max-width: 1100px) {
  .badge-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .badge-grid { grid-template-columns: 1fr; }
}

/* ---- 综合钱包 ---- */
.wallet-grid {
  display: grid; grid-template-columns: 280px 1fr; gap: 14px;
  align-items: stretch;
}
.energy-balance {
  padding: 18px; text-align: center;
  display: flex; flex-direction: column; justify-content: center;
  .eb-label { font-size: 13px; color: var(--dq-text-dim); margin-bottom: 8px; }
  .eb-num {
    font-family: var(--dq-mono); font-size: 42px; font-weight: 800;
    background: var(--dq-grad-primary);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.1;
    text-shadow: 0 0 24px var(--dq-primary-glow);
  }
  .eb-sub { font-size: 11px; color: var(--dq-text-dim); margin-top: 8px; }
}
.wallet-block { padding: 12px 14px; }
.asset-list { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.asset-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 12px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 6px;
  transition: all .15s;
  &:hover { border-color: var(--dq-border-2); }
  .ai-name { color: var(--dq-text); font-size: 13px; font-weight: 500; }
  .ai-tags { display: inline-flex; align-items: center; gap: 6px; }
}
@media (max-width: 1000px) {
  .wallet-grid { grid-template-columns: 1fr; }
}

/* ===================================================================
 *  能量国库审计与职能驱动的业务项
 * =================================================================== */
.dq-tag.tiny { font-size: 10px; padding: 1px 6px; line-height: 1.5; }

/* 身份类型标签（角色卡 / 顶栏身份共用口径） */
.dq-tag.p-admin { background: rgba(77, 141, 255, 0.1); color: var(--dq-info); border-color: rgba(77,141,255,0.28); }
.dq-tag.p-node { background: rgba(0, 230, 195, 0.1); color: var(--dq-primary); }
.dq-tag.p-resident { background: rgba(245, 55, 155, 0.1); color: var(--dq-accent); border-color: rgba(245,55,155,0.28); }

/* 治理身份说明块 */
.dq-note {
  background: linear-gradient(135deg, rgba(77, 141, 255, 0.08), rgba(77, 141, 255, 0.02));
  border: 1px solid rgba(77, 141, 255, 0.25); border-left: 3px solid var(--dq-info);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 14px;
  font-size: 13px; line-height: 1.8; color: var(--dq-text);
  b { color: var(--dq-info); }
  .dn-label {
    display: inline-flex; margin-right: 8px; padding: 1px 8px; border-radius: 4px;
    background: rgba(77, 141, 255, 0.16); color: var(--dq-info); font-size: 11px; font-weight: 700;
  }
}

/* 能量区：发行门槛行 / 行为卡阈值 */
.energy-way-card .ew-threshold {
  font-size: 11px; color: var(--dq-text-dim);
  background: var(--dq-bg-2); border-radius: 4px; padding: 3px 8px; width: fit-content;
}

/* 树种卡：ERC721 发行额度 + 治理按钮行 */
.tree-item {
  .ti-quota { font-size: 11px; color: var(--dq-text-dim); margin: 6px 0; line-height: 1.6; }
  .ti-gov { display: flex; justify-content: space-between; gap: 4px; margin-top: 2px; }
}

/* 勋章卡：发行方 + 份数选择 */
.badge-card {
  .bc-issuer { font-size: 11px; color: var(--dq-text-dim); margin: 4px 0 8px; }
  .bc-qty {
    display: flex; align-items: center; gap: 8px; justify-content: center;
    margin-bottom: 10px; font-size: 12px;
    .bq-label { color: var(--dq-text-dim); }
    .bq-cost { color: var(--dq-primary); font-weight: 600; }
  }
}

/* 能量国库与通胀审计 */
.tr-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px;
}
.tr-cell {
  padding: 12px 14px; background: var(--dq-bg-2);
  border: 1px solid var(--dq-border); border-radius: 8px;
  .tr-label { font-size: 11px; color: var(--dq-text-dim); margin-bottom: 6px; }
  .tr-num { font-size: 20px; font-weight: 700; color: var(--dq-primary); line-height: 1.2; }
  .tr-num.warn { color: var(--dq-warn); }
  .tr-sub { font-size: 10px; color: var(--dq-text-dim); margin-top: 4px; }
}
.quota-list { display: flex; flex-direction: column; gap: 8px; }
.quota-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: var(--dq-bg-2);
  border: 1px solid var(--dq-border); border-radius: 6px; font-size: 12px;
  .qr-name { color: var(--dq-text); font-weight: 600; white-space: nowrap; }
  .qr-wallet { font-size: 11px; }
  .qr-bar { flex: 1; min-width: 120px; }
  .qr-num { color: var(--dq-primary); font-weight: 700; white-space: nowrap; margin-left: auto; }
}
.burn-box {
  margin-top: 14px; padding: 12px 14px;
  background: rgba(255, 84, 112, 0.04); border: 1px solid rgba(255, 84, 112, 0.22); border-radius: 8px;
}
.burn-val { color: var(--dq-error); font-weight: 700; }

@media (max-width: 700px) {
  .quota-row { flex-wrap: wrap; }
}
</style>
