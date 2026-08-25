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

        <!-- 能量经济模型说明 -->
        <div class="eco-model">
          <div class="em-item">
            <div class="em-label">能量发行</div>
            <div class="em-text">业务节点 mint 发放（每次 10~100 点），仅联盟成员有权发行</div>
          </div>
          <div class="em-item">
            <div class="em-label">能量流通</div>
            <div class="em-text">居民间通过市场交易转移能量，购买 NFT 资产时自动 transfer</div>
          </div>
          <div class="em-item">
            <div class="em-label">能量回收</div>
            <div class="em-text">兑换资产时消耗的能量转入管理员国库，定期销毁以防止通胀</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. 合约部署状态区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">📜</span>
        合约部署状态
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
              <div class="cc-hint">🔒 未部署，点击下方按钮一键编译并部署到链上</div>
              <el-button
                size="small"
                type="primary"
                :loading="deployingKey === c.key"
                @click="deployContract(c.key)"
              >
                <span v-if="deployingKey === c.key">编译部署中…</span>
                <span v-else>🚀 一键编译部署</span>
              </el-button>
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
        <span v-if="currentRole" class="dq-tag" style="margin-left: auto">
          当前：{{ roleMeta(currentRole.role_key)?.icon }} {{ roleMeta(currentRole.role_key)?.name }}
        </span>
      </div>
      <div class="role-grid">
        <div
          v-for="r in roleList"
          :key="r.key"
          class="role-card"
          :class="{ active: currentRole?.role_key === r.key }"
          @click="selectRole(r.key)"
        >
          <div class="rc-icon">{{ r.icon }}</div>
          <div class="rc-name">{{ r.name }}</div>
          <div class="rc-desc">{{ r.desc }}</div>
          <div class="rc-rule dq-mono">{{ r.rule }}</div>
        </div>
      </div>
    </div>

    <!-- 4. 绿色能量发放区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">⚡</span>
        绿色能量发放
        <span class="dq-live" style="margin-left: auto"><span class="dot"></span>ERC20 mint</span>
      </div>
      <template v-if="!currentRole">
        <div class="empty-tip">请先在上方选择一个角色</div>
      </template>
      <template v-else-if="currentRole.role_key === 'admin'">
        <div class="dq-note">
          <span class="dn-label">管理员模式</span>
          管理员不发放绿色能量，请前往下方「植树证书管理」添加树种，或切换为其他角色体验能量发放。
        </div>
      </template>
      <template v-else>
        <div class="energy-ops">
          <div class="energy-info">
            当前角色：<b>{{ roleMeta(currentRole.role_key)?.icon }} {{ roleMeta(currentRole.role_key)?.name }}</b>
            <span class="dq-tag accent" style="margin-left: 8px">{{ currentEnergyAction.amount }} 能量 / 次</span>
          </div>
          <el-button type="primary" :loading="issuing" @click="openProofDlg">
            <span class="energy-btn-text">{{ currentEnergyAction.label }}</span>
          </el-button>
        </div>
        <div class="dq-tip" style="margin-bottom: 14px">
          <span class="dt-label">业务凭证:</span>
          点击上方按钮需提交真实业务凭证（如进站口 / 订单号 / 回收重量），链下校验通过后由联盟角色钱包签名 mint 能量。
        </div>
      </template>

      <!-- 最近能量发放记录 -->
      <div class="dq-card-title sub-title">最近能量发放记录</div>
      <el-table :data="energyRecords" border size="small" v-if="energyRecords.length">
        <el-table-column prop="role_key" label="角色" width="120">
          <template #default="{ row }">
            <span>{{ roleMeta(row.role_key)?.icon }} {{ roleMeta(row.role_key)?.name || row.role_key }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="行为" min-width="120">
          <template #default="{ row }">{{ row.action }}</template>
        </el-table-column>
        <el-table-column prop="points" label="能量" width="100">
          <template #default="{ row }"><span class="dq-mono energy-val">+{{ row.points }}</span></template>
        </el-table-column>
        <el-table-column prop="tx_hash" label="交易哈希" min-width="180">
          <template #default="{ row }"><span class="dq-mono dim">{{ row.tx_hash ? short(row.tx_hash) : '-' }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>
      <div v-else class="empty-tip">暂无能量发放记录</div>
    </div>

    <!-- 5. 植树证书管理区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">🌳</span>
        植树证书管理 (ERC721)
      </div>
      <div class="tree-layout">
        <!-- 管理员区域：添加树种 -->
        <div class="dq-card tree-admin" v-if="isAdmin">
          <div class="dq-card-title sub-title">添加树种（管理员）</div>
          <el-form label-width="100px" size="small">
            <el-form-item label="树种名称">
              <el-input v-model="treeForm.name" placeholder="如：银杏树" />
            </el-form-item>
            <el-form-item label="所需能量">
              <el-input-number v-model="treeForm.required_energy" :min="1000" :step="100" />
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
          <div class="dq-tip"><span class="dt-label">说明:</span>所需能量最低 1000，居民可凭足够能量兑换唯一植树证书。</div>
        </div>

        <!-- 树种列表 -->
        <div class="dq-card tree-list">
          <div class="dq-card-title sub-title">可兑换树种</div>
          <div class="tree-grid" v-if="trees.length">
            <div class="dq-card tree-item" v-for="t in trees" :key="t.id">
              <img v-if="t.image_url" class="ti-img" :src="t.image_url" :alt="t.name" @error="t.image_url = ''" />
              <div v-else class="ti-emoji">🌳</div>
              <div class="ti-name">{{ t.name }}</div>
              <div class="ti-desc">{{ t.description || '暂无描述' }}</div>
              <div class="ti-cost">所需能量：<span class="dq-mono">{{ t.required_energy }}</span></div>
              <el-button
                size="small"
                type="primary"
                :disabled="energyBalance < t.required_energy"
                :loading="exchangingTree === t.id"
                @click="exchangeCertificate(t.id)"
                style="margin-top: 8px; width: 100%"
              >
                {{ energyBalance >= t.required_energy ? '兑换证书' : `需 ${t.required_energy} 能量` }}
              </el-button>
            </div>
          </div>
          <div v-else class="empty-tip">暂无树种，{{ isAdmin ? '请在左侧添加' : '请等待管理员添加' }}</div>
        </div>
      </div>

      <!-- 证书列表 -->
      <div class="dq-card-title sub-title" style="margin-top: 16px">
        已兑换植树证书
        <el-button size="small" type="success" plain style="margin-left: 12px" @click="$router.push('/nft?tab=green')">
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
              :loading="listingId === `cert_${c.id}`"
              @click.stop="openListDlg('certificate', Number(c.id), c.species_name || c.name || '植树证书')"
            >
              💰 挂牌出售
            </el-button>
            <span v-else class="dq-tag info">📍 在售中</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-tip">暂无植树证书，兑换后将在此展示</div>
    </div>

    <!-- 6. 勋章与骑行券兑换区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">🎖️</span>
        勋章与骑行券兑换 (ERC1155)
        <span class="dq-tag" style="margin-left: auto">{{ badgeTypes.length }} 种类型</span>
      </div>
      <div class="badge-grid">
        <div class="dq-card badge-card" v-for="bt in badgeTypes" :key="bt.id">
          <img v-if="bt.image_url" class="bc-img" :src="bt.image_url" :alt="bt.name" @error="bt.image_url = ''" />
          <div v-else class="bc-icon">{{ bt.icon || (bt.badge_type === 'voucher' ? '🎫' : '🏅') }}</div>
          <div class="bc-name">{{ bt.name }}</div>
          <div class="bc-desc">{{ bt.desc || '绿色生活荣誉资产' }}</div>
          <div class="bc-meta">
            <span>花费 <span class="dq-mono">{{ bt.cost_energy }}</span> 能量</span>
            <span>已铸 <span class="dq-mono">{{ bt.minted }}</span>/{{ bt.supply }}</span>
          </div>
          <el-button
            type="primary"
            :disabled="energyBalance < bt.cost_energy || bt.minted >= bt.supply"
            :loading="exchangingBadge === String(bt.id)"
            @click="exchangeBadgeType(bt)"
          >
            {{ bt.minted >= bt.supply ? '已售罄' : energyBalance >= bt.cost_energy ? '兑换' : '能量不足' }}
          </el-button>
        </div>
      </div>

      <!-- 联盟角色：新增勋章 / 骑行券类型 -->
      <div class="dq-card badge-admin" v-if="canAddBadgeTypes">
        <div class="dq-card-title sub-title">
          新增勋章类型（联盟角色）
          <span class="dq-tag info" style="margin-left: 8px">{{ currentRole?.role?.icon }} {{ currentRole?.role?.name }}</span>
        </div>
        <el-form :inline="true" size="small">
          <el-form-item v-if="isBike" label="资产类型">
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
          <span class="dt-label">说明:</span>管理员与联盟节点均可新增勋章（需先选定角色）；<b>骑行券仅共享单车公司（bike）</b>可维护。
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
            <el-input v-model="mintToWallet" placeholder="0xresident / 0xlearner" style="width: 180px" />
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

      <!-- 已兑换的勋章/骑行券列表 -->
      <div class="dq-card-title sub-title" style="margin-top: 16px">
        已兑换勋章 / 骑行券
        <el-button size="small" type="success" plain style="margin-left: 12px" @click="$router.push('/nft?tab=green')">
          📈 前往资产市场
        </el-button>
      </div>
      <el-table :data="badges" border size="small" v-if="badges.length">
        <el-table-column prop="badge_type" label="类型" width="140">
          <template #default="{ row }">
            <span>{{ badgeLabel(row.badge_type).icon }} {{ badgeLabel(row.badge_type).name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="token_id" label="Token ID" width="120">
          <template #default="{ row }"><span class="dq-mono">{{ row.token_id }}</span></template>
        </el-table-column>
        <el-table-column label="数量" width="100">
          <template #default><span class="dq-mono">1</span></template>
        </el-table-column>
        <el-table-column prop="owner" label="持有者" min-width="160">
          <template #default="{ row }"><span class="dq-mono dim">{{ short(row.owner) }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="兑换时间" width="170" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <template v-if="String(row.owner).toLowerCase() === String(wallet).toLowerCase()">
              <el-button
                v-if="!isListed(row.badge_type === 'voucher' ? 'voucher' : 'badge', Number(row.id))"
                size="small"
                type="primary"
                plain
                :loading="listingId === `${row.badge_type === 'voucher' ? 'voucher' : 'badge'}_${row.id}`"
                @click.stop="openListDlg(row.badge_type === 'voucher' ? 'voucher' : 'badge', Number(row.id), badgeLabel(row.badge_type).name)"
              >
                挂牌
              </el-button>
              <span v-else class="dq-tag info">📍 在售</span>
            </template>
            <span v-else class="dq-mono dim">-</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-tip">暂无勋章 / 骑行券</div>
    </div>

    <!-- 7. 综合钱包区 -->
    <div class="dq-card section-card">
      <div class="dq-card-title">
        <span class="title-icon">💼</span>
        综合钱包
        <el-button size="small" @click="loadAll" style="margin-left: auto">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
      <el-form label-width="80px" size="small" style="margin-bottom: 12px">
        <el-form-item label="钱包地址">
          <el-input v-model="wallet" @change="setWallet" placeholder="0x..." />
        </el-form-item>
      </el-form>

      <div class="wallet-grid">
        <!-- 绿色能量余额 -->
        <div class="dq-glass energy-balance">
          <div class="eb-label">⚡ 绿色能量余额</div>
          <div class="eb-num">{{ energyBalance }}</div>
          <div class="eb-sub">GreenEnergy (ERC20)</div>
        </div>

        <!-- ERC721 资产列表 -->
        <div class="dq-card wallet-block">
          <div class="dq-card-title sub-title">ERC721 资产（植树证书）</div>
          <div v-if="erc721Assets.length" class="asset-list">
            <div class="asset-item" v-for="a in erc721Assets" :key="a.token_id">
              <span class="ai-name">🌱 {{ a.species_name || a.name || '植树证书' }}</span>
              <span class="dq-tag accent">ID: {{ a.token_id }}</span>
            </div>
          </div>
          <div v-else class="empty-tip small">暂无 ERC721 资产</div>
        </div>

        <!-- ERC1155 资产列表 -->
        <div class="dq-card wallet-block">
          <div class="dq-card-title sub-title">ERC1155 资产（勋章 / 骑行券）</div>
          <div v-if="erc1155Assets.length" class="asset-list">
            <div class="asset-item" v-for="a in erc1155Assets" :key="a.badge_type">
              <span class="ai-name">{{ badgeLabel(a.badge_type).icon }} {{ badgeLabel(a.badge_type).name }}</span>
              <span class="dq-tag warn">x{{ a.amount }}</span>
            </div>
          </div>
          <div v-else class="empty-tip small">暂无 ERC1155 资产</div>
        </div>
      </div>

      <!-- 能量发放记录 -->
      <div class="dq-card-title sub-title" style="margin-top: 16px">能量发放记录</div>
      <el-table :data="energyRecords" border size="small" v-if="energyRecords.length">
        <el-table-column prop="role_key" label="角色" width="120">
          <template #default="{ row }">
            <span>{{ roleMeta(row.role_key)?.icon }} {{ roleMeta(row.role_key)?.name || row.role_key }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="行为" min-width="120">
          <template #default="{ row }">{{ row.action }}</template>
        </el-table-column>
        <el-table-column prop="points" label="能量" width="100">
          <template #default="{ row }"><span class="dq-mono energy-val">+{{ row.points }}</span></template>
        </el-table-column>
        <el-table-column prop="tx_hash" label="交易哈希" min-width="200">
          <template #default="{ row }"><span class="dq-mono dim">{{ row.tx_hash ? short(row.tx_hash) : '-' }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>
      <div v-else class="empty-tip">暂无能量发放记录</div>
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
      </div>
      <el-form label-width="100px" style="margin-top: 12px">
        <el-form-item label="挂牌价格">
          <el-input-number v-model="listPrice" :min="1" :step="10" style="width: 100%" />
          <div class="dq-tip" style="margin-top: 4px">
            <span class="dt-label">说明:</span>以绿色能量（GreenEnergy ERC20）作为计价单位，购买方将从其能量余额支付。
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
      :role-name="currentRole ? roleMeta(currentRole.role_key)?.name : ''"
      :points="currentEnergyAction.amount"
      :rule="currentRuleObj"
      :threshold-hint="currentThresholdHint"
      :proof-no-label="currentProofNoLabel"
      :proof-no-field="currentRuleObj?.proof_no_field"
      @submit="submitProof"
    />

    <!-- 9. 绿色资产市场（买卖 / 下架 闭环） -->
    <div class="dq-card section-card">
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
        <el-table-column prop="price_energy" label="价格(能量)" width="120">
          <template #default="{ row }"><span class="dq-mono energy-val">{{ row.price_energy }}</span></template>
        </el-table-column>
        <el-table-column prop="created_at" label="挂牌时间" width="170" />
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
            <!-- 别人的资产：购买 -->
            <el-button
              v-else
              size="small"
              type="primary"
              :disabled="energyBalance < row.price_energy"
              :loading="buyingMarketId === row.id"
              @click.stop="buyMarket(row)"
            >
              {{ energyBalance >= row.price_energy ? '购买' : `需 ${row.price_energy} 能量` }}
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
import { useAppStore } from '@/stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import EnergyProofForm from '@/components/EnergyProofForm.vue'

/* ==================== 钱包（与 Pinia store 联动） ==================== */
const app = useAppStore()
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
  action?: string
  amount?: number
}
const ROLE_META: Record<string, RoleMeta> = {
  admin:     { icon: '🛡️', name: '管理员',   desc: '平台管理方，部署合约、管理树种、发放植树证书', rule: '不发放能量，管理树种' },
  metro:     { icon: '🚇', name: '地铁集团', desc: '城市地铁运营方', rule: '乘坐地铁 +50 能量',     action: '乘坐地铁',   amount: 50 },
  bus:       { icon: '🚌', name: '公交集团', desc: '城市公交运营方', rule: '乘坐公交 +20 能量',     action: '乘坐公交',   amount: 20 },
  bike:      { icon: '🚲', name: '共享单车', desc: '共享单车运营方，可发放骑行券', rule: '共享单车骑行 +15 能量', action: '共享单车骑行', amount: 15 },
  delivery:  { icon: '📦', name: '外卖平台', desc: '绿色外卖服务平台', rule: '绿色外卖 +10 能量',   action: '绿色外卖',   amount: 10 },
  recycling: { icon: '♻️', name: '回收公司', desc: '旧物回收公司',   rule: '旧物回收 +100 能量',   action: '旧物回收',   amount: 100 },
}
const roleMeta = (key?: string) => (key ? ROLE_META[key] : undefined)

/** 角色列表：合并本地元数据，保证六个角色稳定展示 */
const roleList = computed(() =>
  Object.entries(ROLE_META).map(([key, m]) => ({ key, ...m })),
)

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
const energyBalance = ref(0)
const energyRecords = ref<any[]>([])
const trees = ref<any[]>([])
const certificates = ref<any[]>([])
const badges = ref<any[]>([])
const walletData = ref<any>(null)

const treeForm = reactive({ name: '', required_energy: 1000, image_url: '', description: '' })

/* ==================== 能量发放业务凭证 ==================== */
const proofDlg = ref(false)
const proofFormRef = ref<any>(null)
/** 当前角色的 energy_rule（含 proof_fields 等） */
const currentRuleObj = computed(() => currentRole.value?.role?.energy_rule || null)
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

/** 打开业务凭证表单 */
const openProofDlg = () => {
  if (!currentRole.value) {
    ElMessage.warning('请先选择角色')
    return
  }
  const r = currentRole.value?.role?.energy_rule
  if (!r) {
    ElMessage.warning('当前角色没有能量发放规则')
    return
  }
  proofDlg.value = true
}

/** 提交业务凭证 → 后端校验 → 发放能量 */
const submitProof = async (proof: Record<string, any>) => {
  issuing.value = true
  try {
    const r: any = await ecoApi.issueEnergy(wallet.value, currentRole.value.role_key, proof)
    const pfNo = currentRuleObj.value?.proof_no_field
    ElMessage.success(`能量发放成功：+${r?.points ?? currentEnergyAction.value.amount}，业务单号 ${pfNo && proof[pfNo] ? proof[pfNo] : '-'}`)
    logEco(
      'energy', 'issue_energy', 'success',
      `${roleMeta(currentRole.value.role_key)?.name} · ${currentEnergyAction.value.label} +${r?.points ?? currentEnergyAction.value.amount}点，单号 ${pfNo && proof[pfNo] ? proof[pfNo] : '-'}`,
    )
    proofDlg.value = false
    await Promise.all([loadEnergyBalance(), loadEnergyRecords(), loadWallet()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '能量发放失败'
    ElMessage.error(msg)
    logEco('energy', 'issue_energy', 'error', msg, JSON.stringify(e ?? {}))
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
const mintToWallet = ref('0xresident')
const mintQty = ref(1)
const mintingBadge = ref(false)

/** 当前角色是否有铸造权限（can_issue_badge / can_issue_voucher） */
const canMintBadge = computed(() => {
  const r = currentRole.value?.role
  return !!(r && (r.can_issue_badge || r.can_issue_voucher))
})

/** 当前角色为共享单车公司（骑行券唯一维护方） */
const isBike = computed(() => currentRole.value?.role_key === 'bike')

/** 是否可新增勋章 / 骑行券类型：管理员 + 任意具备发放权限的联盟角色（需先选定角色） */
const canAddBadgeTypes = computed(() => {
  const r = currentRole.value?.role
  if (!r) return false
  if (r.key === 'admin') return true
  return !!(r.can_issue_badge || r.can_issue_voucher)
})

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

/** 兑换勋章 / 骑行券（按类型 ID，能量回收闭环） */
const exchangeBadgeType = async (bt: any) => {
  exchangingBadge.value = String(bt.id)
  try {
    await ecoApi.exchangeBadge(wallet.value, bt.badge_type, bt.id)
    ElMessage.success(`${bt.name} 兑换成功 ${bt.icon || '🎖️'}`)
    logEco('badge', 'exchange_badge', 'success',
      `兑换${bt.name}（type_id=${bt.id}，消耗 ${bt.cost_energy} 能量）`)
    await Promise.all([loadEnergyBalance(), loadBadges(), loadWallet(), loadBadgeTypes()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '勋章兑换失败'
    ElMessage.error(msg)
    logEco('badge', 'exchange_badge', 'error',
      `${msg} (type_id=${bt.id})`, JSON.stringify(e ?? {}))
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
  if (badgeTypeForm.badge_type === 'voucher' && !isBike.value) {
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
    logEco('badge', 'badge_type_add', 'error', msg, JSON.stringify(e ?? {}))
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
  if (!mintToWallet.value.trim()) {
    ElMessage.warning('请填写接收钱包')
    return
  }
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
      to_wallet: mintToWallet.value.trim(),
      quantity: mintQty.value,
    })
    ElMessage.success(`铸造成功：${bt?.name} x${mintQty.value} → ${mintToWallet.value}`)
    logEco('badge', 'badge_mint', 'success',
      `${roleMeta(currentRole.value.role_key)?.name} 铸造 ${bt?.name} x${mintQty.value} 给 ${mintToWallet.value}`)
    await Promise.all([loadBadgeTypes(), loadBadges()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '铸造失败'
    ElMessage.error(msg)
    logEco('badge', 'badge_mint', 'error', msg, JSON.stringify(e ?? {}))
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
    const r: any = await ecoApi.deployContract(name, wallet.value || '0xlearner')
    ElMessage.success(`部署成功：${name} → ${short(r.address)}`)
    logEco('contract', 'deploy_contract', 'success',
      `一键部署 ${name} (${r.standard})，地址：${r.address}，tx：${r.tx_hash}`)
    await loadContractStatus()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '部署失败'
    ElMessage.error(msg)
    logEco('contract', 'deploy_contract', 'error', `部署 ${name} 失败：${msg}`, JSON.stringify(e ?? {}))
  } finally {
    deployingKey.value = ''
  }
}

/* ==================== 资产市场（挂牌 / 购买 / 下架） ==================== */
const listDlg = ref(false)
const listing = ref(false)
const listingId = ref<string>('')   // 用于按钮 loading 状态
const listPrice = ref(50)
const curAsset = ref<{ type: string; id: number; name: string } | null>(null)
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

/** 打开挂牌对话框 */
const openListDlg = (asset_type: string, asset_id: number, name: string) => {
  curAsset.value = { type: asset_type, id: asset_id, name }
  // 建议价格：证书 500，勋章 50，骑行券 100
  listPrice.value = asset_type === 'certificate' ? 500 : asset_type === 'voucher' ? 100 : 50
  listDlg.value = true
}

/** 确认挂牌 */
const doList = async () => {
  if (!curAsset.value) return
  if (listPrice.value <= 0) {
    ElMessage.warning('价格必须大于 0')
    return
  }
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
    })
    ElMessage.success(`已挂牌：${curAsset.value.name} · ${listPrice.value} 能量`)
    logEco('other', 'list_asset', 'success',
      `挂牌 ${curAsset.value.name}，价格 ${listPrice.value} 能量`)
    listDlg.value = false
    await loadMarket()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '挂牌失败'
    ElMessage.error(msg)
    logEco('other', 'list_asset', 'error', msg, JSON.stringify(e ?? {}))
  } finally {
    listing.value = false
    listingId.value = ''
  }
}

/** 取消挂牌（下架） */
const cancelListing = async (id: number) => {
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
  if (energyBalance.value < g.price_energy) {
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
      `购买 ${g.asset_name}，支付 ${g.price_energy} 能量，tx=${r?.nft_tx || '-'}`)
    // 购买会改变能量余额、资产归属、市场列表 → 全量刷新
    await loadAll()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '购买失败'
    ElMessage.error(msg)
    logEco('other', 'buy_asset', 'error', msg, JSON.stringify(e ?? {}))
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

const isAdmin = computed(() => currentRole.value?.role_key === 'admin')

/** 当前角色的能量发放动作 */
const currentEnergyAction = computed(() => {
  const m = roleMeta(currentRole.value?.role_key)
  return {
    label: m?.action ? `${m.icon} ${m.action}` : '发放能量',
    amount: m?.amount || 0,
  }
})

/** 钱包 ERC721 资产 */
const erc721Assets = computed(() => {
  if (walletData.value?.erc721) return walletData.value.erc721
  // 从证书列表中筛选当前钱包持有
  return certificates.value.filter((c) => c.owner === wallet.value)
})

/** 钱包 ERC1155 资产 */
const erc1155Assets = computed(() => {
  if (walletData.value?.erc1155) return walletData.value.erc1155
  // 按类型聚合当前钱包的勋章数量（后端每次兑换 1 个）
  const map: Record<string, number> = {}
  for (const b of badges.value) {
    if (b.owner === wallet.value) {
      map[b.badge_type] = (map[b.badge_type] || 0) + 1
    }
  }
  return Object.entries(map).map(([badge_type, amount]) => ({ badge_type, amount }))
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
  } catch {
    roles.value = []
  }
}

const loadCurrentRole = async () => {
  try {
    currentRole.value = await ecoApi.currentRole(wallet.value)
    app.setCurrentRole(currentRole.value)   // 同步到 Pinia store 供其他页面读取
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

const loadEnergyBalance = async () => {
  try {
    const r: any = await ecoApi.energyBalance(wallet.value)
    energyBalance.value = Number(r?.balance ?? r ?? 0)
  } catch {
    energyBalance.value = 0
  }
}

const loadEnergyRecords = async () => {
  try {
    const r: any = await ecoApi.energyRecords(wallet.value)
    energyRecords.value = r?.items || r || []
  } catch {
    energyRecords.value = []
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
  try {
    const r: any = await ecoApi.badges(wallet.value)
    badges.value = r?.items || r || []
  } catch {
    badges.value = []
  }
}

const loadWallet = async () => {
  try {
    walletData.value = await ecoApi.wallet(wallet.value)
  } catch {
    walletData.value = null
  }
}

const loadAll = async () => {
  loading.value = true
  await Promise.all([
    loadRoles(),
    loadCurrentRole(),
    loadContractStatus(),
    loadEnergyBalance(),
    loadEnergyRecords(),
    loadTrees(),
    loadCertificates(),
    loadBadges(),
    loadBadgeTypes(),
    loadWallet(),
    loadMarket(),
  ])
  loading.value = false
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
      wallet: wallet.value || 'unknown',
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

/** 选择角色 */
const selectRole = async (role_key: string) => {
  try {
    await ElMessageBox.confirm(
      `确认切换为「${roleMeta(role_key)?.icon} ${roleMeta(role_key)?.name}」角色？`,
      '角色切换',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await ecoApi.selectRole(wallet.value, role_key)
    ElMessage.success(`已选择角色：${roleMeta(role_key)?.name}`)
    logEco('role', 'select_role', 'success', `选择角色：${roleMeta(role_key)?.name} (${role_key})`)
    // 切角色后全量刷新：角色、余额、记录、钱包、合约状态都需联动
    await loadAll()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '角色切换失败'
    ElMessage.error(msg)
    logEco('role', 'select_role', 'error', msg, JSON.stringify(e ?? {}))
  }
}

/** 添加树种（管理员） */
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
  addingTree.value = true
  try {
    await ecoApi.addTree({ ...treeForm, wallet: wallet.value })
    ElMessage.success('树种添加成功')
    logEco('tree', 'add_tree', 'success',
      `管理员上架树种：${treeForm.name}，需 ${treeForm.required_energy} 能量`)
    treeForm.name = ''
    treeForm.required_energy = 1000
    treeForm.image_url = ''
    treeForm.description = ''
    await loadTrees()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '树种添加失败'
    ElMessage.error(msg)
    logEco('tree', 'add_tree', 'error', msg, JSON.stringify(e ?? {}))
  } finally {
    addingTree.value = false
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
  exchangingTree.value = species_id
  try {
    const species = trees.value.find(t => t.id === species_id)
    await ecoApi.exchangeCertificate(wallet.value, species_id)
    ElMessage.success('植树证书兑换成功 🌱')
    logEco('certificate', 'exchange_cert', 'success',
      `兑换：${species?.name ?? '未知树种'}（species_id=${species_id}）`)
    await Promise.all([loadEnergyBalance(), loadCertificates(), loadWallet()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '证书兑换失败'
    ElMessage.error(msg)
    logEco('certificate', 'exchange_cert', 'error',
      `${msg} (species_id=${species_id})`, JSON.stringify(e ?? {}))
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

/* ---- 能量经济模型 ---- */
.eco-model {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--dq-border);
  .em-item {
    padding: 10px 12px;
    background: var(--dq-bg-2);
    border: 1px solid var(--dq-border);
    border-radius: 6px;
    .em-label {
      display: inline-block;
      font-size: 11px; font-weight: 600;
      color: var(--dq-primary);
      background: rgba(0,230,195,0.1);
      padding: 2px 8px; border-radius: 3px;
      margin-bottom: 6px;
    }
    .em-text {
      font-size: 12px; color: var(--dq-text-dim);
      line-height: 1.6;
    }
  }
}
@media (max-width: 760px) {
  .eco-model { grid-template-columns: 1fr; }
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

/* ---- 区块卡片 ---- */
.section-card { margin-bottom: 14px; }
.sub-title {
  font-size: 13px; margin-bottom: 10px; margin-top: 4px;
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

/* ---- 角色选择 ---- */
.role-grid {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
}
.role-card {
  padding: 14px 10px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 8px;
  cursor: pointer;
  text-align: center;
  transition: all .2s;
  position: relative;
  &:hover {
    border-color: var(--dq-border-2);
    transform: translateY(-2px);
    box-shadow: var(--dq-shadow);
  }
  &.active {
    border-color: var(--dq-primary);
    background: linear-gradient(135deg, rgba(0,230,195,0.12), rgba(0,230,195,0.02));
    box-shadow: 0 0 0 1px var(--dq-primary), 0 0 16px var(--dq-primary-glow);
  }
  .rc-icon { font-size: 28px; margin-bottom: 6px; }
  .rc-name { font-weight: 600; color: var(--dq-text); font-size: 13px; margin-bottom: 4px; }
  .rc-desc { font-size: 11px; color: var(--dq-text-dim); line-height: 1.5; margin-bottom: 6px; }
  .rc-rule {
    font-size: 10px; color: var(--dq-primary);
    background: rgba(0,230,195,0.08);
    padding: 3px 6px; border-radius: 4px;
    border: 1px solid rgba(0,230,195,0.2);
  }
}
@media (max-width: 1100px) {
  .role-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 600px) {
  .role-grid { grid-template-columns: repeat(2, 1fr); }
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
  .energy-btn-text { font-weight: 600; }
}
.energy-val {
  color: var(--dq-success); font-weight: 700;
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
  display: grid; grid-template-columns: 280px 1fr 1fr; gap: 14px;
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
.asset-list { display: flex; flex-direction: column; gap: 8px; }
.asset-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 12px;
  background: var(--dq-bg-2);
  border: 1px solid var(--dq-border);
  border-radius: 6px;
  transition: all .15s;
  &:hover { border-color: var(--dq-border-2); }
  .ai-name { color: var(--dq-text); font-size: 13px; font-weight: 500; }
}
@media (max-width: 1000px) {
  .wallet-grid { grid-template-columns: 1fr; }
}
</style>
