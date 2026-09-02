/**
 * 学生使用手册 PPT 生成脚本（docs/generate-student-ppt.js）
 * 输出：docs/output/学生使用手册.pptx（25 页）
 * 设计体系复用 docs/ppt_theme.js（与 generate-manual-ppt.js 同一套 Design Tokens）
 * 文案口径：docs/教学指南.md + backend/app/routers/grades.py + 原手册 STEPS 命令文案
 */

const path = require('path');
const T = require('./ppt_theme');
const { C, F, S } = T;

const FOOTER = 'FISCO 联盟链实训平台 · 学生使用手册 v1.0';
const TOTAL = 25;

// ============================================================================
// 1. 封面
// ============================================================================
function slide01_Cover(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  const cx = 5, cy = 2.0;
  slide.addShape('hexagon', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1.5 } });
  slide.addText('FISCO', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  slide.addText('区块链教学实训平台', { x: 1, y: 2.9, w: 8, h: 0.6, fontSize: S['4xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('学生使用手册 · Student Handbook', { x: 1, y: 3.55, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.primary, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.2, w: 2.4, h: 0.02, fill: { color: C.primary }, line: { width: 0 } });
  slide.addText('搭一条绿色低碳联盟链 · 6 角色业务闭环 · 链上真实行为评分', { x: 1, y: 4.45, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  ['10步搭链教程', '6角色业务闭环', '4维自动评分'].forEach((t, i) => T.drawTag(slide, 2.2 + i * 2.3, 5.3, t, [C.primary, C.info, C.accent][i]));
  slide.addText('v1.0 · 2026年8月 · 天择教育', { x: 1, y: 6.2, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawFooter(slide, FOOTER);
}

// ============================================================================
// 2. 目录（5 章）
// ============================================================================
function slide02_TOC(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '目录', 'Table of Contents', 2, TOTAL);
  T.drawFooter(slide, FOOTER);
  const chapters = [
    { num: '01', title: '快速上手', desc: '登录绑定 · 功能地图 · 总览看板 · L5 微任务', color: C.primary, pages: 'P03-06' },
    { num: '02', title: '搭链实训', desc: '搭链云桌面 · 10 步流程图 · 关键步骤精讲', color: C.info, pages: 'P07-10' },
    { num: '03', title: '合约开发', desc: '合约 IDE · 安全审计打分 · 接口调试', color: C.success, pages: 'P11-13' },
    { num: '04', title: '联盟业务与资产', desc: '生态实践 · 能量规则 · 钱包 · 资产市场 · 链上验证', color: C.accent, pages: 'P14-19' },
    { num: '05', title: '成绩与报告', desc: '成就中心 · 我的成绩 · 成绩体系 · 实训报告 · FAQ', color: C.warn, pages: 'P20-25' },
  ];
  chapters.forEach((ch, i) => {
    const y = 1.05 + i * 1.12;
    T.addToken(slide, ch.num, { x: 0.7, y: y + 0.1, w: 0.8, h: 0.6, fontSize: S['2xl'], fontFace: F.mono, color: ch.color, bold: true, align: 'center' });
    slide.addShape('rect', { x: 1.55, y: y + 0.38, w: 0.35, h: 0.02, fill: { color: ch.color, transparency: 50 }, line: { width: 0 } });
    slide.addText(ch.title, { x: 2.05, y: y + 0.08, w: 5, h: 0.32, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(ch.desc, { x: 2.05, y: y + 0.42, w: 6, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDim, valign: 'top' });
    T.drawTag(slide, 7.8, y + 0.15, ch.pages, ch.color);
  });
}

// ============================================================================
// 3. 平台功能地图（设计化）
// ============================================================================
function slide03_Modules(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '平台功能地图', 'Feature Modules', 3, TOTAL);
  T.drawFooter(slide, FOOTER);
  const groups = [
    { name: '快速上手', color: C.primary, modules: [{ t: '登录', d: 'SSO 单点 · 自动绑钱包' }, { t: '总览', d: '看板 + 学习路径' }, { t: '今日任务', d: 'L5 微任务自动验收' }] },
    { name: '合约开发', color: C.info, modules: [{ t: '合约 IDE', d: '内置工程 · solc 编译' }, { t: '合约管理', d: '部署 + 安全审计' }, { t: '接口调试', d: 'ABI 自动生成' }] },
    { name: '联盟业务与资产', color: C.success, modules: [{ t: '绿色低碳链', d: '6 角色发能量' }, { t: 'ERC20 钱包', d: '余额 · 转账 · 资产' }, { t: 'NFT 市场', d: '铸造 · 挂牌 · 购买' }] },
    { name: '链上验证与成绩', color: C.accent, modules: [{ t: '调用监听器', d: '调用统计' }, { t: '区块链浏览器', d: '交易追溯' }, { t: '成就中心', d: '15 成就 3 挑战' }, { t: '我的成绩', d: '4 维雷达' }, { t: '实训报告', d: '一键生成' }] },
  ];
  groups.forEach((g, gi) => {
    const colX = 0.5 + gi * 2.35;
    slide.addShape('roundRect', { x: colX, y: 1.0, w: 2.15, h: 0.32, fill: { color: g.color, transparency: 80 }, line: { color: g.color, width: 0.75 }, rectRadius: 0.05 });
    slide.addText(g.name, { x: colX, y: 1.0, w: 2.15, h: 0.32, fontSize: S.sm, fontFace: F.sans, color: g.color, bold: true, align: 'center', valign: 'middle' });
    g.modules.forEach((m, i) => {
      const y = 1.5 + i * 1.0;
      T.drawCard(slide, colX, y, 2.15, 0.85, { border: g.color, borderWidth: 0.5 });
      slide.addShape('roundRect', { x: colX + 0.1, y: y + 0.08, w: 0.3, h: 0.03, fill: { color: g.color }, line: { width: 0 }, rectRadius: 0.02 });
      slide.addText(m.t, { x: colX + 0.1, y: y + 0.14, w: 1.95, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
      slide.addText(m.d, { x: colX + 0.1, y: y + 0.46, w: 1.95, h: 0.35, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
    });
  });
  slide.addText('学习主线：搭链 → 合约 → 联盟运营 → 链上验证，全部行为数据按钱包自动计入实训成绩', { x: 0.5, y: 6.6, w: 9, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.primary, align: 'center' });
}

// ============================================================================
// 4. 登录指引（shot-login）
// ============================================================================
function slide04_Login(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '平台入口 · 登录', 'Platform Entry', 4, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawCard(slide, 0.5, 1.0, 4.0, 5.5);
  T.drawCardTitle(slide, 0.65, 1.1, 3.7, '登录方式', { tag: '账号密码', tagColor: C.primary });
  const items = [
    { t: '账号密码登录', d: '输入学号与密码，经 RSA 加密转发 SSO 完成认证', c: C.primary },
    { t: '单点登录会话', d: '平台自签 JWT（24h 有效），刷新页面自动恢复登录态', c: C.info },
    { t: '角色自动识别', d: 'roleId: 3=教师 4=学生，登录后自动进入对应视角', c: C.success },
    { t: '首次登录绑定钱包', d: '学生首次登录自动绑定默认链上钱包，实训行为按钱包统计', c: C.warn },
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.1;
    slide.addShape('ellipse', { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fill: { color: it.c }, line: { width: 0 } });
    T.addToken(slide, String(i + 1), { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fontSize: 6, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(it.t, { x: 1.0, y: y, w: 3.3, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 1.0, y: y + 0.3, w: 3.3, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  T.drawScreenshot(slide, 4.8, 1.0, 4.7, 5.5, T.shot('shot-login'), { url: 'localhost:5173/#/login', border: C.primary });
  slide.addText('登录页：区块节点星球动画 + 链网状态面板 + 底部区块浏览器滚动条', { x: 4.8, y: 6.55, w: 4.7, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// ============================================================================
// 5. 总览看板（shot-dashboard）
// ============================================================================
function slide05_Dashboard(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '总览看板与学习路径', 'Dashboard Overview', 5, TOTAL);
  T.drawFooter(slide, FOOTER);
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.42, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('登录后首页即总览：聚合链状态、块高、TPS 等核心指标，同时展示 4 阶段学习路径与今日任务', { x: 0.65, y: 0.95, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.info, valign: 'middle' });
  T.drawScreenshot(slide, 0.5, 1.5, 6.6, 5.4, T.shot('shot-dashboard'), { url: 'localhost:5173/#/dashboard', border: C.primary });
  T.drawCard(slide, 7.3, 1.5, 2.2, 5.4);
  T.drawCardTitle(slide, 7.45, 1.6, 1.9, '看板要点', { tag: '6项', tagColor: C.primary });
  const points = [
    { t: '链模式', d: 'FISCO / EVM / 沙盒', c: C.primary },
    { t: '块高 TPS', d: '实时链指标', c: C.info },
    { t: '节点数', d: '4 共识节点', c: C.success },
    { t: '搭链进度', d: '10 步完成率', c: C.warn },
    { t: '学习路径', d: '4 阶段 10 节点', c: C.accent },
    { t: '今日任务', d: '微任务自动验收', c: C.primary2 },
  ];
  points.forEach((p, i) => {
    const y = 2.05 + i * 0.78;
    slide.addShape('ellipse', { x: 7.5, y: y + 0.05, w: 0.1, h: 0.1, fill: { color: p.c }, line: { width: 0 } });
    slide.addText(p.t, { x: 7.7, y, w: 1.7, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: p.c, bold: true, valign: 'middle' });
    slide.addText(p.d, { x: 7.7, y: y + 0.24, w: 1.7, h: 0.2, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  });
}

// ============================================================================
// 6. L5 联盟运营微任务（设计化）
// ============================================================================
function slide06_L5Missions(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, 'L5 联盟运营微任务', 'Missions After Tutorial', 6, TOTAL);
  T.drawFooter(slide, FOOTER);
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.5, fill: { color: C.primary, transparency: 90 }, line: { color: C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('搭链 10/10 完成后，「今日任务」自动切换为 10 个联盟运营微任务，由服务端按钱包真实业务数据自动验收', { x: 0.65, y: 0.95, w: 8.7, h: 0.5, fontSize: S.sm, fontFace: F.sans, color: C.primary, valign: 'middle' });
  const phases = [
    { name: 'Phase 1 · 系统激活', range: 'T1-T2', color: C.primary, items: ['管理员激活 3 份系统合约', '依次体验 6 大联盟角色'] },
    { name: 'Phase 2 · 能量发放', range: 'T3-T7', color: C.info, items: ['依次切换地铁 / 公交 / 单车', '外卖 / 回收 5 种角色发放能量'] },
    { name: 'Phase 3 · 资产兑换', range: 'T8-T10', color: C.accent, items: ['兑换 ≥2 种树种植树证书', '勋章 + 骑行券 · 生成实训报告'] },
  ];
  phases.forEach((p, i) => {
    const x = 0.5 + i * 3.1;
    T.drawCard(slide, x, 1.75, 2.9, 2.5, { border: p.color, borderWidth: 0.75 });
    T.drawCardTitle(slide, x + 0.15, 1.9, 2.6, p.name, { tag: p.range, tagColor: p.color });
    p.items.forEach((it, j) => {
      const y = 2.45 + j * 0.85;
      slide.addShape('ellipse', { x: x + 0.2, y: y + 0.06, w: 0.08, h: 0.08, fill: { color: p.color }, line: { width: 0 } });
      slide.addText(it, { x: x + 0.38, y, w: 2.4, h: 0.75, fontSize: S.sm, fontFace: F.sans, color: C.text, valign: 'top' });
    });
    if (i < 2) T.drawArrowH(slide, x + 2.92, 2.9, 0.16);
  });
  // 验收机制说明
  T.drawCard(slide, 0.5, 4.6, 9, 1.9);
  T.drawCardTitle(slide, 0.65, 4.72, 8.7, '验收机制', { tag: '服务端核验', tagColor: C.success });
  const rows = [
    { k: '数据来源', v: '服务端按钱包核对平台真实业务数据（GET /api/missions/curriculum），无法伪造' },
    { k: '来源标注', v: '每个任务标注「服务端验收」或「本地打卡」，未达标时本地打卡仅作降级记录' },
    { k: '课堂用途', v: 'L5 微任务可作为第 3 课时的课堂实操与抽查依据，完成状态实时同步' },
  ];
  rows.forEach((r, i) => {
    const y = 5.15 + i * 0.42;
    slide.addShape('rect', { x: 0.8, y: y + 0.08, w: 0.04, h: 0.22, fill: { color: C.success }, line: { width: 0 } });
    slide.addText(r.k, { x: 0.95, y, w: 1.2, h: 0.38, fontSize: S.sm, fontFace: F.sans, color: C.success, bold: true, valign: 'middle' });
    slide.addText(r.v, { x: 2.25, y, w: 7.1, h: 0.38, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
  slide.addText('建议节奏：P1→P4 学习主线约 2 课时，L5 微任务作第 3 课时实操', { x: 0.5, y: 6.68, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.info, align: 'center' });
}

// ============================================================================
// 7. 搭链云桌面总览（shot-cloud）
// ============================================================================
function slide07_Cloud(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '搭链云桌面', 'Cloud Desktop · Tutorial', 7, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.0, 5.5, T.shot('shot-cloud'), { url: 'localhost:5173/#/cloud', border: C.primary });
  slide.addText('搭链云桌面：左侧 10 步导航 + 总进度环，右侧终端实时输出', { x: 0.5, y: 6.55, w: 5.0, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 5.7, 1.0, 3.8, 5.5);
  T.drawCardTitle(slide, 5.85, 1.1, 3.5, '四阶段流程', { tag: '严格顺序', tagColor: C.warn });
  const stages = [
    { name: '链底层搭建', range: 'Step 1-4', color: C.primary, items: '生成联盟链 · 证书核验 · 出块检查 · 接入控制台' },
    { name: '联盟组织接入', range: 'Step 5-8', color: C.info, items: '组织证书核查 · 治理规则 · 组织钱包 · 健康检查' },
    { name: '合约部署', range: 'Step 9', color: C.success, items: '部署 GreenEnergy 绿色能量代币' },
    { name: '链路验证', range: 'Step 10', color: C.accent, items: '5 业务角色发放 → 居民持有 + 交易确认' },
  ];
  stages.forEach((s, i) => {
    const y = 1.6 + i * 1.15;
    T.drawCard(slide, 5.85, y, 3.5, 0.95, { border: s.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: 5.95, y: y + 0.08, w: 0.8, h: 0.03, fill: { color: s.color }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(s.name, { x: 5.95, y: y + 0.15, w: 2.2, h: 0.28, fontSize: S.base, fontFace: F.sans, color: s.color, bold: true, valign: 'middle' });
    T.addToken(slide, s.range, { x: 7.95, y: y + 0.15, w: 1.3, h: 0.28, fontSize: S.sm, fontFace: F.mono, color: C.text, align: 'right' });
    slide.addText(s.items, { x: 5.95, y: y + 0.48, w: 3.3, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
    if (i < 3) T.drawArrowV(slide, 7.6, y + 0.95, 0.2);
  });
  slide.addText('进度实时持久化：每步含命令序列、预期输出与故障排查提示', { x: 5.7, y: 6.55, w: 3.8, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// ============================================================================
// 8. 10 步搭链流程图（设计化）
// ============================================================================
function slide08_TutorialFlow(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '10 步搭链流程图', 'Tutorial Pipeline', 8, TOTAL);
  T.drawFooter(slide, FOOTER);
  const rows = [
    { name: '链底层搭建', range: 'Step 1-4', color: C.primary, steps: ['生成 4 节点联盟链', '节点进程证书核验', '日志出块检查', '接入控制台'] },
    { name: '联盟组织接入', range: 'Step 5-8', color: C.info, steps: ['组织证书核查', '治理规则公示', '注册组织钱包', '上线健康检查'] },
    { name: '合约部署', range: 'Step 9', color: C.success, steps: ['部署 GreenEnergy'], note: 'GreenEnergy 为 ERC20 绿色能量代币，部署者 0xadmin' },
    { name: '链路验证', range: 'Step 10', color: C.accent, steps: ['商业化全链路验证'], note: '5 业务角色发放能量 → 居民持有 + 交易确认' },
  ];
  let stepNo = 0;
  rows.forEach((row, ri) => {
    const y = 1.0 + ri * 1.18;
    slide.addShape('roundRect', { x: 0.5, y, w: 1.5, h: 1.0, fill: { color: row.color, transparency: 82 }, line: { color: row.color, width: 0.75 }, rectRadius: 0.05 });
    slide.addText(row.name, { x: 0.5, y: y + 0.18, w: 1.5, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: row.color, bold: true, align: 'center', valign: 'middle' });
    T.addToken(slide, row.range, { x: 0.5, y: y + 0.55, w: 1.5, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.textDim, align: 'center' });
    row.steps.forEach((st, si) => {
      stepNo += 1;
      const x = 2.2 + si * 1.82;
      T.drawCard(slide, x, y, 1.72, 1.0, { border: row.color, borderWidth: 0.5 });
      T.drawStepCircle(slide, x + 0.12, y + 0.12, stepNo, 0.3, row.color);
      slide.addText(st, { x: x + 0.1, y: y + 0.48, w: 1.52, h: 0.45, fontSize: S.xs, fontFace: F.sans, color: C.text, bold: true, valign: 'top' });
      if (si < row.steps.length - 1) T.drawArrowH(slide, x + 1.55, y + 0.42, 0.25);
    });
    if (row.note) {
      const nx = 2.2 + row.steps.length * 1.82 + 0.1;
      slide.addShape('roundRect', { x: nx, y: y + 0.18, w: 9.5 - nx, h: 0.64, fill: { color: row.color, transparency: 88 }, line: { color: row.color, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
      slide.addText(row.note, { x: nx + 0.1, y: y + 0.18, w: 9.4 - nx, h: 0.64, fontSize: S.xs, fontFace: F.sans, color: row.color, valign: 'middle' });
    }
  });
  slide.addShape('roundRect', { x: 0.5, y: 5.85, w: 9, h: 0.85, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 }, rectRadius: 0.05 });
  slide.addText('组织节点矩阵', { x: 0.65, y: 5.92, w: 1.6, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, valign: 'middle' });
  slide.addText('node0 = 管理员 + 地铁集团      node1 = 公交集团 + 共享单车      node2 = 外卖平台 + 回收公司      node3 = 热备共识', { x: 0.65, y: 6.2, w: 8.7, h: 0.4, fontSize: S.xs, fontFace: F.mono, color: C.primary, valign: 'middle' });
  slide.addText('每步内置命令序列、预期输出与故障排查提示，完成 10 步方可进入后续实训', { x: 0.5, y: 6.85, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// ============================================================================
// 9/10. 关键步骤精讲（复用原手册 STEPS 命令文案）
// ============================================================================
function slideStepDetail(pptx, page, blockA, blockB, tip) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, blockA.header, '搭链关键步骤精讲', page, TOTAL);
  T.drawFooter(slide, FOOTER);
  [blockA, blockB].forEach((b, bi) => {
    const y = 0.95 + bi * 2.85;
    slide.addShape('ellipse', { x: 0.5, y, w: 0.55, h: 0.55, fill: { color: b.color, transparency: 80 }, line: { color: b.color, width: 1.5 } });
    T.addToken(slide, String(b.num), { x: 0.5, y, w: 0.55, h: 0.55, fontSize: S.md, fontFace: F.mono, color: b.color, bold: true, align: 'center' });
    slide.addText(b.title, { x: 1.2, y: y + 0.02, w: 4.5, h: 0.3, fontSize: S.md, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(b.desc, { x: 1.2, y: y + 0.32, w: 8.2, h: 0.24, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
    T.drawCard(slide, 0.5, y + 0.68, 5.4, 1.95);
    T.drawCardTitle(slide, 0.65, y + 0.74, 5.1, '执行命令', { tag: 'bash', tagColor: C.info });
    T.drawCodeBlock(slide, 0.65, y + 1.06, 5.1, 1.5, b.commands, { title: 'bash — cloud-desktop' });
    T.drawCard(slide, 6.1, y + 0.68, 3.4, 1.95);
    T.drawCardTitle(slide, 6.25, y + 0.74, 3.1, '预期输出', { tag: '验证', tagColor: C.success });
    T.drawCodeBlock(slide, 6.25, y + 1.06, 3.1, 1.5, b.output, { title: 'output', accentColor: C.success });
  });
  slide.addShape('roundRect', { x: 0.5, y: 6.6, w: 9, h: 0.42, fill: { color: C.warn, transparency: 88 }, line: { color: C.warn, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText(tip, { x: 0.65, y: 6.6, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.warn, valign: 'middle' });
}

function slide09_StepsA(pptx) {
  slideStepDetail(pptx, 9,
    {
      header: 'Step 1 · 生成 4 节点联盟链', num: 1, color: C.primary,
      title: '下载官方脚本并生成联盟链（证书体系建立）',
      desc: 'FISCO-BCOS 4 节点 PBFT 共识，含组织-节点矩阵',
      commands: ['$ cd /root/fisco', '$ curl -LO https://github.com/FISCO-BCOS/build_chain.sh', '$ chmod +x build_chain.sh', '$ bash build_chain.sh -l "127.0.0.1:4" -p 30300,20200,8545'],
      output: ['[INFO] FISCO-BCOS Path : bin/fisco-bcos', '[INFO] Node Count      : 4', '[INFO] Output Dir      : nodes/127.0.0.1', '[INFO] All completed.'],
    },
    {
      header: 'Step 3 · 检查日志出块', num: 3, color: C.primary,
      title: 'PBFT 共识确认 + 日志分析',
      desc: '确认 4 节点进程运行并持续出块',
      commands: ['$ ps -ef | grep fisco-bcos | wc -l', '$ tail -f node0/log/log_INFO | grep "+++"'],
      output: ['4  (4 个节点进程运行中)', '+++ generating seal on: 1 txs', '# +++ 表示 sealer 开始打包'],
    },
    '要点：4 节点全部启动成功才算通过；证书位于 cert/ 目录；节点配置在 nodes/127.0.0.1'
  );
}

function slide10_StepsB(pptx) {
  slideStepDetail(pptx, 10,
    {
      header: 'Step 9 · 部署 GreenEnergy', num: 9, color: C.success,
      title: '编译并部署绿色能量代币合约',
      desc: 'GreenEnergy 为 ERC20 标准代币，部署者 0xadmin',
      commands: ['$ cd /root/fisco/console && bash start.sh', '[group:1]> deploy GreenEnergy 1000000', '# 记录合约地址，用于后续能量发放'],
      output: ['contract address: 0x1234...5678', 'transaction hash: 0xabcd...1234', 'Gas used: 1500000'],
    },
    {
      header: 'Step 10 · 商业化全链路验证', num: 10, color: C.accent,
      title: '5 业务角色发放 → 居民持有 + 交易确认',
      desc: '完成「低碳行为 → 发放能量」完整链路验证',
      commands: ['$ curl -X POST .../api/eco/energy/issue \\', '    -d \'{"role":"metro","distance":15}\'', '$ curl .../api/wallet/balance/0xlearner'],
      output: ['{ "success": true, "energy": 50,', '  "proof_no": "metro-001" }', 'Balance of 0xlearner: 50'],
    },
    '要点：部署者必须是 0xadmin；同一业务单号 + 角色只发一次能量（幂等返回旧结果）'
  );
}

// ============================================================================
// 11. 合约 IDE（shot-ide）
// ============================================================================
function slide11_IDE(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '合约 IDE', 'Contract IDE', 11, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-ide'), { url: 'localhost:5173/#/ide', border: C.info });
  slide.addText('合约 IDE：Monaco 编辑器 + 工程文件管理 + 在线编译部署', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '核心能力', { tag: '4项', tagColor: C.info });
  const feats = [
    { t: '内置合约工程', d: '内置 6 份合约工程，含 2 份漏洞修复关卡（重入 / tx.origin 鉴权）', c: C.primary },
    { t: '在线编译', d: '真实 solc 编译，编译成功次数计入实训成绩', c: C.info },
    { t: '一键部署', d: '部署到 FISCO 链，已部署合约数计入成绩', c: C.success },
    { t: '学习路径验收', d: '编译 ≥1 次，部署 PlantCertificate 或 EcoBadge', c: C.accent },
  ];
  feats.forEach((f, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('roundRect', { x: 6.35, y, w: 3.0, h: 0.04, fill: { color: f.c }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(f.t, { x: 6.35, y: y + 0.1, w: 3.0, h: 0.28, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, valign: 'middle' });
    slide.addText(f.d, { x: 6.35, y: y + 0.4, w: 3.0, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 12. 合约管理与安全审计（shot-contracts）
// ============================================================================
function slide12_Audit(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '合约管理与安全审计', 'Contracts & Audit', 12, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, T.shot('shot-contracts'), { url: 'localhost:5173/#/contracts', border: C.accent });
  slide.addText('合约管理：部署状态一览 + 一键安全审计 + 问题行号定位', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 审计打分公式
  slide.addShape('roundRect', { x: 5.9, y: 1.0, w: 3.6, h: 0.85, fill: { color: C.accent, transparency: 88 }, line: { color: C.accent, width: 1 }, rectRadius: 0.08 });
  slide.addText('审计打分公式', { x: 6.05, y: 1.08, w: 3.3, h: 0.24, fontSize: S.xs, fontFace: F.sans, color: C.accent, bold: true, valign: 'middle' });
  slide.addText('score = 100 − 高危×20 − 中危×10 − 低危×5', { x: 6.05, y: 1.36, w: 3.3, h: 0.3, fontSize: S.sm, fontFace: F.mono, color: C.text, bold: true, valign: 'middle' });
  // 审计维度 2x2
  T.drawCard(slide, 5.9, 2.05, 3.6, 2.2);
  T.drawCardTitle(slide, 6.05, 2.15, 3.3, '静态检查维度', { tag: '4维', tagColor: C.info });
  const dims = [
    { t: '重入攻击', c: C.error }, { t: '缺事件', c: C.warn },
    { t: '缺访问控制', c: C.info }, { t: 'Gas 优化', c: C.success },
  ];
  dims.forEach((d, i) => {
    const x = 6.05 + (i % 2) * 1.7;
    const y = 2.6 + Math.floor(i / 2) * 0.75;
    T.drawCard(slide, x, y, 1.55, 0.6, { border: d.c, borderWidth: 0.5 });
    slide.addText(d.t, { x, y, w: 1.55, h: 0.6, fontSize: S.sm, fontFace: F.sans, color: d.c, bold: true, align: 'center', valign: 'middle' });
  });
  // 漏洞修复闭环
  T.drawCard(slide, 5.9, 4.45, 3.6, 2.05);
  T.drawCardTitle(slide, 6.05, 4.55, 3.3, '漏洞修复关卡', { tag: 'CTF', tagColor: C.warn });
  const flow = [
    { n: '1', t: '审计检出漏洞（行号+修复建议）', c: C.error },
    { n: '2', t: '修改源码修复漏洞', c: C.info },
    { n: '3', t: '重新审计至高危清零 = 通过 1 次', c: C.success },
  ];
  flow.forEach((f, i) => {
    const y = 4.95 + i * 0.5;
    T.drawStepCircle(slide, 6.15, y, f.n, 0.26, f.c);
    slide.addText(f.t, { x: 6.5, y: y - 0.03, w: 2.95, h: 0.32, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
  slide.addText('通过 2 次解锁成就「编程关卡通关」；累计 5 次审计解锁「安全审计员」', { x: 6.0, y: 6.52, w: 3.5, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
}

// ============================================================================
// 13. 接口调试（shot-interfaces）
// ============================================================================
function slide13_Interfaces(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '接口调试', 'ABI Debugger', 13, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-interfaces'), { url: 'localhost:5173/#/interfaces', border: C.success });
  slide.addText('接口调试：选择已部署合约 → 自动生成 ABI 接口 → 填参调用', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '调用类型', { tag: '读+写', tagColor: C.success });
  const items = [
    { t: 'ABI 自动生成', d: '按已部署合约地址自动生成接口列表，无需手写', c: C.primary },
    { t: 'view 读方法', d: '链下只读查询，不产生交易、不消耗 Gas', c: C.info },
    { t: '写方法上链', d: '产生链上交易并返回 tx_hash，计入链上验证', c: C.accent },
    { t: '路径验收', d: '成功调用 ≥1 个 view + ≥1 个写方法', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 14. 绿色低碳联盟链（shot-eco）
// ============================================================================
function slide14_Eco(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '绿色低碳联盟链', 'Eco Practice', 14, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, T.shot('shot-eco'), { url: 'localhost:5173/#/eco', border: C.success });
  slide.addText('生态实践：6 角色卡片切换 + 能量发放凭证表单 + 资产兑换区', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 5.9, 1.0, 3.6, 5.5);
  T.drawCardTitle(slide, 6.05, 1.1, 3.3, '业务主线', { tag: '发能量→兑换', tagColor: C.success });
  const items = [
    { t: '6 联盟角色切换', d: '发放前必须切换到对应角色，否则接口返回 403', c: C.primary },
    { t: '凭证发放能量', d: '填写符合阈值的业务凭证，链上 mint 绿色能量', c: C.info },
    { t: '资产兑换', d: '树种植树证书 / 生态勋章 / 骑行券（仅 bike 可发）', c: C.accent },
    { t: '操作留痕', d: '每笔操作写入日志，教师端可审计对账', c: C.warn },
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.15;
    slide.addShape('ellipse', { x: 6.1, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.3, y, w: 3.1, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.3, y: y + 0.3, w: 3.05, h: 0.7, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 15. 6 角色能量规则（设计化映射表）
// ============================================================================
function slide15_EnergyRules(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '6 联盟角色与能量规则', 'Energy Rules', 15, TOTAL);
  T.drawFooter(slide, FOOTER);
  const rules = [
    { role: '管理员', wallet: '0xadmin', proof: '—（治理角色不发能量）', energy: '0', signer: 'owner', color: C.primary },
    { role: '地铁集团', wallet: '0xmetro', proof: '乘坐地铁 ≥ 10km', energy: '+50', signer: '0xmetro', color: C.info },
    { role: '公交集团', wallet: '0xbus', proof: '乘坐公交 ≥ 5min', energy: '+20', signer: '0xbus', color: C.success },
    { role: '共享单车', wallet: '0xbike', proof: '骑行 ≥ 2km', energy: '+15', signer: '0xbike', color: C.warn },
    { role: '外卖平台', wallet: '0xtakeout', proof: '绿色外卖（无需餐具）', energy: '+10', signer: '0xtakeout', color: C.accent },
    { role: '回收公司', wallet: '0xrecycle', proof: '回收 ≥ 1kg', energy: '+100', signer: '0xrecycle', color: C.primary2 },
  ];
  slide.addShape('rect', { x: 0.65, y: 1.15, w: 8.7, h: 0.32, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  const widths = [1.4, 1.7, 2.9, 1.1, 1.6];
  ['角色', '钱包地址', '业务凭证阈值', '能量', '签名者'].forEach((h, i) => {
    let x = 0.65;
    for (let j = 0; j < i; j++) x += widths[j];
    slide.addText(h, { x, y: 1.15, w: widths[i], h: 0.32, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, align: 'center', valign: 'middle' });
  });
  rules.forEach((r, i) => {
    const y = 1.47 + i * 0.4;
    slide.addShape('rect', { x: 0.65, y, w: 8.7, h: 0.4, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
    slide.addShape('rect', { x: 0.65, y, w: 0.04, h: 0.4, fill: { color: r.color }, line: { width: 0 } });
    const cells = [{ t: r.role, c: r.color, b: true, f: F.sans }, { t: r.wallet, c: C.text, b: false, f: F.mono }, { t: r.proof, c: C.text, b: false, f: F.sans }, { t: r.energy, c: C.success, b: true, f: F.mono }, { t: r.signer, c: C.textDim, b: false, f: F.mono }];
    let x = 0.65;
    cells.forEach((cell, j) => {
      slide.addText(cell.t, { x, y, w: widths[j], h: 0.4, fontSize: S.xs, fontFace: cell.f, color: cell.c, bold: cell.b, align: 'center', valign: 'middle' });
      x += widths[j];
    });
  });
  // 防刷与闭环
  T.drawCard(slide, 0.5, 4.05, 4.35, 2.5);
  T.drawCardTitle(slide, 0.65, 4.15, 4.05, '业务单号防刷', { tag: 'UNIQUE', tagColor: C.error });
  const anti = [
    { k: '单号字段', v: '地铁/公交 trip_no · 单车/外卖 order_id · 回收 order_no' },
    { k: '防重复', v: '同一业务单号 + 同一角色只发一次（数据库 UNIQUE 索引兜底）' },
    { k: '幂等返回', v: '重复提交返回旧结果并提示「该业务单号已发放过能量」' },
  ];
  anti.forEach((a, i) => {
    const y = 4.6 + i * 0.62;
    slide.addText(a.k, { x: 0.8, y, w: 1.0, h: 0.55, fontSize: S.sm, fontFace: F.sans, color: C.error, bold: true, valign: 'top' });
    slide.addText(a.v, { x: 1.85, y, w: 2.85, h: 0.62, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  T.drawCard(slide, 5.15, 4.05, 4.35, 2.5);
  T.drawCardTitle(slide, 5.3, 4.15, 4.05, '能量流转闭环', { tag: '5步', tagColor: C.success });
  const flow = ['切换联盟角色', '填写业务凭证', '阈值校验', '链上 mint 铸造', '兑换时能量回笼国库'];
  flow.forEach((f, i) => {
    const y = 4.62 + i * 0.38;
    T.drawStepCircle(slide, 5.45, y, i + 1, 0.24, C.success);
    slide.addText(f, { x: 5.8, y: y - 0.02, w: 3.6, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
  slide.addText('内置三合约：GreenEnergy（ERC20 能量）· PlantCertificate（ERC721 证书）· EcoBadge（ERC1155 勋章/骑行券）', { x: 0.5, y: 6.72, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.info, align: 'center' });
}

// ============================================================================
// 16. 能量钱包（shot-wallet）
// ============================================================================
function slide16_Wallet(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '能量钱包', 'ERC20 Wallet', 16, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-wallet'), { url: 'localhost:5173/#/wallet', border: C.info });
  slide.addText('钱包页：代币余额 + 转账 + NFT 资产展示 + 能量发放记录', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '钱包功能', { tag: '4项', tagColor: C.info });
  const items = [
    { t: '能量余额', d: 'GreenEnergy（ERC20）余额与发放记录查询', c: C.primary },
    { t: '能量转账', d: '向其他钱包转账，计入联盟治理成绩', c: C.info },
    { t: 'NFT 资产', d: '植树证书（ERC721）/ 勋章与骑行券（ERC1155）', c: C.accent },
    { t: '综合查询', d: '一个接口看全：角色 / 能量 / 证书 / 勋章 / 骑行券', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 17. 绿色资产市场（shot-nft）
// ============================================================================
function slide17_Market(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '绿色资产市场', 'NFT Market', 17, TOTAL);
  T.drawFooter(slide, FOOTER);
  // 顶部交易流程
  T.drawCard(slide, 0.5, 1.0, 9, 1.35);
  T.drawCardTitle(slide, 0.65, 1.08, 8.7, '交易闭环', { tag: '铸造→挂牌→购买→取消', tagColor: C.primary });
  const flow = [{ n: '1', t: '铸造', d: '能量兑换资产', c: C.primary }, { n: '2', t: '挂牌', d: '设定价格上架', c: C.info }, { n: '3', t: '购买', d: '余额完成交易', c: C.success }, { n: '4', t: '取消', d: '下架返回钱包', c: C.accent }];
  flow.forEach((f, i) => {
    const x = 1.0 + i * 2.2;
    T.drawStepCircle(slide, x, 1.5, f.n, 0.28, f.c);
    slide.addText(f.t, { x: x - 0.2, y: 1.84, w: 0.7, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: f.c, bold: true, align: 'center', valign: 'middle' });
    slide.addText(f.d, { x: x - 0.45, y: 2.06, w: 1.2, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center', valign: 'middle' });
    if (i < 3) T.drawArrowH(slide, x + 0.3, 1.6, 1.9);
  });
  T.drawScreenshot(slide, 0.5, 2.55, 5.5, 3.95, T.shot('shot-nft'), { url: 'localhost:5173/#/nft', border: C.accent });
  T.drawCard(slide, 6.2, 2.55, 3.3, 3.95);
  T.drawCardTitle(slide, 6.35, 2.65, 3.0, '市场规则', { tag: '5条', tagColor: C.warn });
  const rules = [
    '已上架资产显示 On Sale 标签，隐藏上架按钮防重复',
    '购买 / 取消后同步刷新市场列表和钱包余额',
    '取消上架后资产返回钱包，可重新上架',
    '交易写入链上，成交计入联盟治理成绩',
    '价格由卖家设定，用 GreenEnergy 能量计价',
  ];
  rules.forEach((r, i) => {
    slide.addShape('ellipse', { x: 6.45, y: 3.12 + i * 0.63 + 0.05, w: 0.06, h: 0.06, fill: { color: C.warn }, line: { width: 0 } });
    slide.addText(r, { x: 6.6, y: 3.07 + i * 0.63, w: 2.8, h: 0.58, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 18. 调用监听器（shot-monitor）
// ============================================================================
function slide18_Monitor(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '链上验证 · 调用监听器', 'Call Monitor', 18, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-monitor'), { url: 'localhost:5173/#/monitor', border: C.info });
  slide.addText('调用监听器：合约调用统计 + 方法分布 + 实时状态跟踪', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '验证要点', { tag: '4项', tagColor: C.info });
  const items = [
    { t: '调用统计', d: '按合约 / 方法维度聚合全班调用分布', c: C.primary },
    { t: '定位自己的调用', d: '找到自己的 mint / transfer 调用记录', c: C.info },
    { t: 'status 含义', d: 'status=1 交易成功，status=0 交易失败', c: C.accent },
    { t: '与浏览器互证', d: '监听器看分布，浏览器按 tx_hash 看明细', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 19. 区块链浏览器（shot-explorer）
// ============================================================================
function slide19_Explorer(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '链上验证 · 区块链浏览器', 'Chain Explorer', 19, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-explorer'), { url: 'localhost:5173/#/explorer', border: C.primary });
  slide.addText('区块链浏览器：区块列表 / 交易详情 / 地址余额追溯', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '浏览器能力', { tag: '4维', tagColor: C.primary });
  const feats = [
    { t: '区块查询', d: '块高 / 哈希 / 时间 / 交易数', c: C.primary },
    { t: '交易追溯', d: '按 tx_hash 查询 from / to / input', c: C.info },
    { t: '事件解码', d: '解码 Transfer 事件，核对能量流向', c: C.success },
    { t: '地址余额', d: 'GreenEnergy 余额链上实查', c: C.accent },
  ];
  feats.forEach((f, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('roundRect', { x: 6.35, y, w: 3.0, h: 0.04, fill: { color: f.c }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(f.t, { x: 6.35, y: y + 0.1, w: 3.0, h: 0.28, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, valign: 'middle' });
    slide.addText(f.d, { x: 6.35, y: y + 0.4, w: 3.0, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 20. 成就中心（shot-achievements）
// ============================================================================
function slide20_Achievements(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '成就中心', 'Achievements', 20, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-achievements'), { url: 'localhost:5173/#/achievements', border: C.warn });
  slide.addText('成就中心：成就徽章墙 + 挑战任务 + 解锁进度实时核算', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '激励体系', { tag: '15+3', tagColor: C.warn });
  const items = [
    { t: '15 个成就', d: '初次编译 · 部署专家 · 安全审计员 · 联盟全能角色 · 审计初体验 · 编程关卡通关 等', c: C.primary },
    { t: '3 个挑战任务', d: '每日编译 · Gas 挑战 · 生态链挑战', c: C.info },
    { t: '真实行为核验', d: '进度由服务端按真实链上行为核算，学生无法伪造', c: C.accent },
    { t: '课堂积分参考', d: '可作课堂积分制参考，完成状态实时同步', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 21. 我的成绩（shot-my-grades）
// ============================================================================
function slide21_MyGrades(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '我的成绩', 'My Grades', 21, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-my-grades'), { url: 'localhost:5173/#/my-grades', border: C.accent });
  slide.addText('我的成绩：4 维评分雷达 + 实训得分 + 教师评价 + 班级排名', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '查看要点', { tag: '4项', tagColor: C.accent });
  const items = [
    { t: '按钱包实时计算', d: '登录身份与钱包绑定，仅能查看本人成绩', c: C.primary },
    { t: '4 维明细', d: '链搭建 / 合约开发 / 链上验证 / 联盟治理逐项可见', c: C.info },
    { t: '三项成绩', d: '实训成绩 + 教师评分 + 综合成绩同时展示', c: C.accent },
    { t: '实时预览', d: '暂无成绩记录时返回实时计算预览（不入库）', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 22. 成绩体系（设计化）
// ============================================================================
function slide22_GradeSystem(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '成绩体系', 'Grade System', 22, TOTAL);
  T.drawFooter(slide, FOOTER);
  // 三段式
  const segs = [
    { t: '实训成绩', d: '平台按钱包真实行为自动计算', c: C.primary },
    { t: '教师评分', d: '教师录入（实训报告 / 课堂表现 0-100）', c: C.info },
    { t: '综合成绩', d: '系统自动合成', c: C.accent },
  ];
  segs.forEach((s, i) => {
    const x = 0.5 + i * 3.1;
    T.drawCard(slide, x, 1.0, 2.9, 1.0, { border: s.c, borderWidth: 0.75 });
    slide.addText(s.t, { x: x + 0.15, y: 1.1, w: 2.6, h: 0.3, fontSize: S.base, fontFace: F.sans, color: s.c, bold: true, valign: 'middle' });
    slide.addText(s.d, { x: x + 0.15, y: 1.42, w: 2.6, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
    if (i < 2) T.drawArrowH(slide, x + 2.92, 1.4, 0.16);
  });
  // 4 维权重卡
  const dims = [
    { name: '链搭建', w: '20%', items: 'IDE 打开工程 · 保存工程 · 教程完成步数', color: C.primary },
    { name: '合约开发', w: '30%', items: '编译成功次数 · 已部署合约数', color: C.info },
    { name: '链上验证', w: '25%', items: '接口调用 · 合约调用 · 链上交易笔数', color: C.success },
    { name: '联盟治理', w: '25%', items: '角色切换 · 能量发放 · NFT 铸造/交易 · 转账 · 报告查看', color: C.accent },
  ];
  dims.forEach((d, i) => {
    const x = 0.5 + (i % 2) * 4.65;
    const y = 2.3 + Math.floor(i / 2) * 1.6;
    T.drawCard(slide, x, y, 4.35, 1.4, { border: d.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: x + 0.15, y: y + 0.12, w: 3.0, h: 0.04, fill: { color: d.color }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(d.name, { x: x + 0.15, y: y + 0.22, w: 2.6, h: 0.32, fontSize: S.md, fontFace: F.sans, color: d.color, bold: true, valign: 'middle' });
    T.addToken(slide, d.w, { x: x + 3.2, y: y + 0.2, w: 1.0, h: 0.36, fontSize: S.xl, fontFace: F.mono, color: C.warn, bold: true, align: 'right' });
    slide.addText(d.items, { x: x + 0.15, y: y + 0.62, w: 4.05, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  // 公式 + 规则
  slide.addShape('roundRect', { x: 0.5, y: 5.65, w: 9, h: 0.6, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1 }, rectRadius: 0.08 });
  slide.addText('综合成绩 = 实训成绩 × 0.6 + 教师评分 × 0.4', { x: 0.6, y: 5.65, w: 8.8, h: 0.6, fontSize: S.lg, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  slide.addShape('roundRect', { x: 0.5, y: 6.4, w: 9, h: 0.5, fill: { color: C.warn, transparency: 90 }, line: { color: C.warn, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('实训成绩由平台行为数据自动计算，无法人为修改；每项计分指标均有封顶', { x: 0.65, y: 6.4, w: 8.7, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.warn, valign: 'middle' });
}

// ============================================================================
// 23. 实训报告（shot-report）
// ============================================================================
function slide23_Report(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '实训报告', 'Training Report', 23, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, T.shot('shot-report'), { url: 'localhost:5173/#/report', border: C.success });
  slide.addText('实训报告：成绩构成 + 各维度明细 + 改进建议', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 5.9, 1.0, 3.6, 5.5);
  T.drawCardTitle(slide, 6.05, 1.1, 3.3, '一键生成', { tag: '触发成绩草稿', tagColor: C.success });
  const items = [
    { t: '一键生成报告', d: '汇总搭链 / 合约 / 联盟运营全流程数据', c: C.primary },
    { t: '自动创建草稿', d: '完成 10 步搭链后自动创建「区块链实训」成绩草稿', c: C.info },
    { t: '教师补录评分', d: '草稿教师评分默认 0，待教师在「学生成绩」页补录', c: C.accent },
    { t: '报告查看计分', d: '查看报告行为计入联盟治理维度', c: C.warn },
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.02;
    slide.addShape('ellipse', { x: 6.1, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.3, y, w: 3.1, h: 0.26, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.3, y: y + 0.28, w: 3.05, h: 0.62, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  // 闭环流程
  const flow = [{ t: '生成报告', c: C.primary }, { t: '自动建草稿', c: C.info }, { t: '教师补录', c: C.accent }, { t: '定稿', c: C.success }];
  flow.forEach((f, i) => {
    const x = 6.1 + i * 0.88;
    slide.addShape('roundRect', { x, y: 5.85, w: 0.78, h: 0.42, fill: { color: f.c, transparency: 80 }, line: { color: f.c, width: 0.5 }, rectRadius: 0.05 });
    slide.addText(f.t, { x, y: 5.85, w: 0.78, h: 0.42, fontSize: 8, fontFace: F.sans, color: f.c, bold: true, align: 'center', valign: 'middle' });
    if (i < 3) T.drawArrowH(slide, x + 0.78, 5.97, 0.1);
  });
}

// ============================================================================
// 24. 常见问题 FAQ
// ============================================================================
function slide24_FAQ(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '常见问题', 'FAQ', 24, TOTAL);
  T.drawFooter(slide, FOOTER);
  const faqs = [
    { q: '教程步骤可以跳过吗？', a: '不可以，10 步严格按顺序执行，每步完成才能进入下一步。' },
    { q: '能量发放失败怎么办？', a: '检查业务凭证是否满足阈值，并确认已切换到对应联盟角色（未切角色返回 403）。' },
    { q: '同一业务单号能重复发能量吗？', a: '不能，同一业务单号 + 角色只发一次，重复提交幂等返回旧结果。' },
    { q: '成绩如何计算？', a: '综合成绩 = 实训成绩 × 60% + 教师评分 × 40%，实训分由平台行为数据自动计算。' },
    { q: '实训成绩和预期不符？', a: '实训分按钱包真实行为统计，可在「我的成绩」查看 4 维明细，教师一键刷新后更新。' },
    { q: '成就可以伪造吗？', a: '不能，成就由服务端按真实链上行为核验，本地打卡未达标时仅作降级记录。' },
  ];
  faqs.forEach((faq, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7;
    const y = 1.0 + row * 1.85;
    T.drawCard(slide, x, y, 4.4, 1.65, { border: C.info, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.12, w: 0.25, h: 0.25, fill: { color: C.info }, line: { width: 0 }, rectRadius: 0.04 });
    T.addToken(slide, 'Q', { x: x + 0.1, y: y + 0.12, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.q, { x: x + 0.45, y: y + 0.1, w: 3.85, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.info, bold: true, valign: 'middle' });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.04 });
    T.addToken(slide, 'A', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.a, { x: x + 0.45, y: y + 0.57, w: 3.85, h: 1.0, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 25. 结束页
// ============================================================================
function slide25_End(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  slide.addShape('hexagon', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1.5 } });
  slide.addText('FISCO', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  slide.addText('感谢使用', { x: 1, y: 3.3, w: 8, h: 0.5, fontSize: S['2xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('区块链教学实训平台 · 学生使用手册', { x: 1, y: 3.85, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.primary, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.45, w: 2.4, h: 0.02, fill: { color: C.primary }, line: { width: 0 } });
  slide.addText('技术支持', { x: 1, y: 4.75, w: 8, h: 0.25, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  slide.addText('platform@fisco-chain.edu', { x: 1, y: 5.1, w: 8, h: 0.3, fontSize: S.md, fontFace: F.mono, color: C.primary, align: 'center' });
  slide.addText('v1.0 · 2026年8月 · 天择教育', { x: 1, y: 5.6, w: 8, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDimmer, align: 'center' });
  T.drawFooter(slide, FOOTER);
}

// ============================================================================
// 主函数
// ============================================================================
async function main() {
  console.log('开始生成「学生使用手册」PPT...');
  // 启动预校验：所有用到的截图必须真实存在
  T.requireShots([
    'shot-login', 'shot-dashboard', 'shot-cloud', 'shot-ide', 'shot-contracts',
    'shot-interfaces', 'shot-eco', 'shot-wallet', 'shot-nft', 'shot-monitor',
    'shot-explorer', 'shot-achievements', 'shot-my-grades', 'shot-report',
  ]);
  console.log('截图预校验通过（14 张）');

  const pptx = T.createPptx({ subject: '学生使用手册', title: '区块链教学实训平台 · 学生使用手册' });

  slide01_Cover(pptx);
  slide02_TOC(pptx);
  slide03_Modules(pptx);
  slide04_Login(pptx);
  slide05_Dashboard(pptx);
  slide06_L5Missions(pptx);
  slide07_Cloud(pptx);
  slide08_TutorialFlow(pptx);
  slide09_StepsA(pptx);
  slide10_StepsB(pptx);
  slide11_IDE(pptx);
  slide12_Audit(pptx);
  slide13_Interfaces(pptx);
  slide14_Eco(pptx);
  slide15_EnergyRules(pptx);
  slide16_Wallet(pptx);
  slide17_Market(pptx);
  slide18_Monitor(pptx);
  slide19_Explorer(pptx);
  slide20_Achievements(pptx);
  slide21_MyGrades(pptx);
  slide22_GradeSystem(pptx);
  slide23_Report(pptx);
  slide24_FAQ(pptx);
  slide25_End(pptx);

  const outDir = T.ensureOutputDir();
  const outputPath = path.join(outDir, '学生使用手册.pptx');
  // Windows 下目标文件可能正被 WPS/Office 打开（EBUSY），等待重试后仍失败则降级输出
  let written = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await pptx.writeFile({ fileName: outputPath });
      written = outputPath;
      break;
    } catch (err) {
      if (err && err.code === 'EBUSY' && attempt < 3) {
        console.log(`目标文件被占用（可能正在 WPS/Office 中打开），${attempt}/3 次重试前等待 2 秒...`);
        await new Promise((r) => setTimeout(r, 2000));
      } else if (err && err.code === 'EBUSY') {
        const fallbackPath = path.join(outDir, '学生使用手册.pending.pptx');
        await pptx.writeFile({ fileName: fallbackPath });
        console.warn(`目标文件仍被占用，已降级输出到: ${fallbackPath}`);
        console.warn('请关闭 WPS/Office 中打开的「学生使用手册.pptx」后重新运行本脚本以获得正式文件。');
        written = fallbackPath;
        break;
      } else {
        throw err;
      }
    }
  }
  console.log(`生成成功: ${written}（共 ${TOTAL} 页，嵌入 14 张高清截图）`);
}

main().catch((err) => {
  console.error('生成失败:', err);
  process.exit(1);
});
