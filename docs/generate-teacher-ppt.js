/**
 * 教师使用手册 PPT 生成脚本（docs/generate-teacher-ppt.js）
 * 输出：docs/output/教师使用手册.pptx（14 页）
 * 设计体系复用 docs/ppt_theme.js（与 generate-manual-ppt.js 同一套 Design Tokens）
 * 文案口径：docs/教学指南.md + backend/app/routers/grades.py
 */

const path = require('path');
const T = require('./ppt_theme');
const { C, F, S } = T;

const FOOTER = 'FISCO 联盟链实训平台 · 教师使用手册 v1.0';
const TOTAL = 14;

// ============================================================================
// 1. 封面
// ============================================================================
function slide01_Cover(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  const cx = 5, cy = 2.0;
  slide.addShape('hexagon', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 1.5 } });
  slide.addText('FISCO', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.info, bold: true, align: 'center', valign: 'middle' });
  slide.addText('区块链教学实训平台', { x: 1, y: 2.9, w: 8, h: 0.6, fontSize: S['4xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('教师使用手册 · Teacher Handbook', { x: 1, y: 3.55, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.info, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.2, w: 2.4, h: 0.02, fill: { color: C.info }, line: { width: 0 } });
  slide.addText('班级实训进度看板 · 成绩闭环管理 · 联盟业务监管', { x: 1, y: 4.45, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  ['班级进度看板', '成绩闭环管理', '生态监管审计'].forEach((t, i) => T.drawTag(slide, 2.2 + i * 2.3, 5.3, t, [C.info, C.primary, C.accent][i]));
  slide.addText('v1.0 · 2026年8月 · 天择教育', { x: 1, y: 6.2, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawFooter(slide, FOOTER);
}

// ============================================================================
// 2. 目录（4 章）
// ============================================================================
function slide02_TOC(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '目录', 'Table of Contents', 2, TOTAL);
  T.drawFooter(slide, FOOTER);
  const chapters = [
    { num: '01', title: '课堂总览', desc: '教师角色权限 · 班级实训进度看板 · 学生学习路径', color: C.primary, pages: 'P03-05' },
    { num: '02', title: '成绩管理', desc: '成绩体系 · 录分操作 · 一键刷新 · 搭链卡点分析', color: C.info, pages: 'P06-09' },
    { num: '03', title: '教学监管', desc: '联盟业务监管 · 成绩草稿闭环 · 课堂运营剧本', color: C.accent, pages: 'P10-12' },
    { num: '04', title: '常见问题', desc: '教师视角 FAQ', color: C.warn, pages: 'P13' },
  ];
  chapters.forEach((ch, i) => {
    const y = 1.25 + i * 1.4;
    T.addToken(slide, ch.num, { x: 0.7, y: y + 0.1, w: 0.8, h: 0.6, fontSize: S['2xl'], fontFace: F.mono, color: ch.color, bold: true, align: 'center' });
    slide.addShape('rect', { x: 1.55, y: y + 0.38, w: 0.35, h: 0.02, fill: { color: ch.color, transparency: 50 }, line: { width: 0 } });
    slide.addText(ch.title, { x: 2.05, y: y + 0.08, w: 5, h: 0.32, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(ch.desc, { x: 2.05, y: y + 0.42, w: 6, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDim, valign: 'top' });
    T.drawTag(slide, 7.8, y + 0.15, ch.pages, ch.color);
  });
}

// ============================================================================
// 3. 教师登录与角色权限（shot-login）
// ============================================================================
function slide03_Login(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '教师登录与角色权限', 'Teacher Entry & Roles', 3, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawCard(slide, 0.5, 1.0, 4.0, 5.5);
  T.drawCardTitle(slide, 0.65, 1.1, 3.7, '角色说明', { tag: 'roleId=3', tagColor: C.info });
  const items = [
    { t: '账号密码登录', d: '输入工号与密码，经 RSA 加密转发 SSO 完成认证', c: C.primary },
    { t: '教师专属菜单', d: '登录后多出「学生成绩」菜单（/grades）；非教师访问自动跳回总览', c: C.info },
    { t: '成绩接口权限', d: '仅教师（roleId=3）与管理员（roleId=1）可访问成绩模块', c: C.accent },
    { t: '班级数据隔离', d: '教师查询成绩默认只返回自己班级的数据，不越权', c: C.warn },
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.1;
    slide.addShape('ellipse', { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fill: { color: it.c }, line: { width: 0 } });
    T.addToken(slide, String(i + 1), { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fontSize: 6, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(it.t, { x: 1.0, y: y, w: 3.3, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 1.0, y: y + 0.3, w: 3.3, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  T.drawScreenshot(slide, 4.8, 1.0, 4.7, 5.5, T.shot('shot-login'), { url: 'localhost:5173/#/login', border: C.info });
  slide.addText('登录后进入总览，教师视角自动切换为班级实训进度看板', { x: 4.8, y: 6.55, w: 4.7, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// ============================================================================
// 4. 教师总览 · 班级实训进度看板（shot-teacher-dashboard）
// ============================================================================
function slide04_ClassDashboard(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '班级实训进度看板', 'Class Progress Board', 4, TOTAL);
  T.drawFooter(slide, FOOTER);
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.42, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('教师登录总览自动展示「班级实训进度看板」，数据来自 GET /api/auth/platform-progress', { x: 0.65, y: 0.95, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.info, valign: 'middle' });
  T.drawScreenshot(slide, 0.5, 1.5, 6.6, 5.4, T.shot('shot-teacher-dashboard'), { url: 'localhost:5173/#/dashboard', border: C.info });
  T.drawCard(slide, 7.3, 1.5, 2.2, 5.4);
  T.drawCardTitle(slide, 7.45, 1.6, 1.9, '看板指标', { tag: '5项', tagColor: C.info });
  const points = [
    { t: '班级人数', d: '在读学生统计', c: C.primary },
    { t: '平均步数', d: '搭链完成 x/10', c: C.info },
    { t: '平均成绩', d: '实训分均值', c: C.success },
    { t: '每步完成率', d: '柱状条对比', c: C.warn },
    { t: '学生明细', d: '姓名/学号/进度/成绩', c: C.accent },
  ];
  points.forEach((p, i) => {
    const y = 2.1 + i * 0.95;
    slide.addShape('ellipse', { x: 7.5, y: y + 0.05, w: 0.1, h: 0.1, fill: { color: p.c }, line: { width: 0 } });
    slide.addText(p.t, { x: 7.7, y, w: 1.7, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: p.c, bold: true, valign: 'middle' });
    slide.addText(p.d, { x: 7.7, y: y + 0.24, w: 1.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
  });
}

// ============================================================================
// 5. 学生学习路径速览（设计化）
// ============================================================================
function slide05_LearningPath(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '学生学习路径速览', 'Learning Path', 5, TOTAL);
  T.drawFooter(slide, FOOTER);
  const rows = [
    { stage: 'P1 链底层', color: C.primary, nodes: [{ t: '总览 /dashboard', d: '5min' }, { t: '搭链云桌面 /cloud', d: '30min' }], check: '10/10 步完成 · 部署 GreenEnergy · 6 角色发能量验证' },
    { stage: 'P2 合约开发', color: C.info, nodes: [{ t: '合约 IDE /ide', d: '15min' }, { t: '合约管理 /contracts', d: '5min' }, { t: '接口调试 /interfaces', d: '10min' }], check: '编译 ≥1 次 · 3/3 合约部署 · view+写方法各 ≥1 次' },
    { stage: 'P3 联盟运营', color: C.success, nodes: [{ t: '绿色低碳链 /eco', d: '40min' }, { t: 'ERC20 钱包 /wallet', d: '5min' }, { t: 'NFT 市场 /nft', d: '10min' }], check: '6/6 角色体验 · ≥3 种角色发能量 · 兑换 ≥2 类资产' },
    { stage: 'P4 链上验证', color: C.accent, nodes: [{ t: '调用监听器 /monitor', d: '5min' }, { t: '区块链浏览器 /explorer', d: '5min' }], check: '定位自己的调用 · 按 tx_hash 解码 Transfer 事件' },
  ];
  rows.forEach((r, ri) => {
    const y = 1.0 + ri * 1.25;
    slide.addShape('roundRect', { x: 0.5, y, w: 1.45, h: 1.05, fill: { color: r.color, transparency: 82 }, line: { color: r.color, width: 0.75 }, rectRadius: 0.05 });
    slide.addText(r.stage, { x: 0.5, y: y + 0.32, w: 1.45, h: 0.4, fontSize: S.sm, fontFace: F.sans, color: r.color, bold: true, align: 'center', valign: 'middle' });
    r.nodes.forEach((n, ni) => {
      const x = 2.15 + ni * 1.75;
      T.drawCard(slide, x, y + 0.08, 1.65, 0.88, { border: r.color, borderWidth: 0.5 });
      slide.addText(n.t, { x: x + 0.08, y: y + 0.18, w: 1.5, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
      T.addToken(slide, n.d, { x: x + 0.08, y: y + 0.62, w: 1.5, h: 0.22, fontSize: S.xs, fontFace: F.mono, color: r.color, align: 'left' });
    });
    slide.addShape('roundRect', { x: 2.15 + r.nodes.length * 1.75 + 0.08, y: y + 0.18, w: 9.5 - (2.15 + r.nodes.length * 1.75 + 0.08), h: 0.68, fill: { color: r.color, transparency: 88 }, line: { color: r.color, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
    slide.addText(r.check, { x: 2.23 + r.nodes.length * 1.75, y: y + 0.18, w: 9.42 - (2.15 + r.nodes.length * 1.75), h: 0.68, fontSize: S.xs, fontFace: F.sans, color: r.color, valign: 'middle' });
  });
  slide.addShape('roundRect', { x: 0.5, y: 6.15, w: 9, h: 0.7, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 }, rectRadius: 0.05 });
  slide.addText('主线约 2 课时；L5 微任务（搭链 10/10 后自动开启）可作第 3 课时课堂实操与抽查依据，完成状态由服务端自动验收', { x: 0.65, y: 6.15, w: 8.7, h: 0.7, fontSize: S.xs, fontFace: F.sans, color: C.primary, valign: 'middle' });
}

// ============================================================================
// 6. 成绩体系（设计化）
// ============================================================================
function slide06_GradeSystem(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '成绩体系', 'Grade System', 6, TOTAL);
  T.drawFooter(slide, FOOTER);
  // 三段式
  const segs = [
    { t: '实训成绩', d: '平台按钱包真实行为自动计算', c: C.primary },
    { t: '教师评分', d: '教师手动录入（0-100）', c: C.info },
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
    { name: '链搭建', w: '20%', items: 'IDE 打开内置工程 · 保存工程 · 教程完成步数', color: C.primary },
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
  slide.addShape('roundRect', { x: 0.5, y: 6.4, w: 9, h: 0.5, fill: { color: C.error, transparency: 90 }, line: { color: C.error, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('权限边界：教师只能录入教师评分与一键刷新实训分，不可直接修改实训成绩（平台自动计算）', { x: 0.65, y: 6.4, w: 8.7, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.error, bold: true, valign: 'middle' });
}

// ============================================================================
// 7. 学生成绩管理 · 录分（shot-teacher-grades）
// ============================================================================
function slide07_Upsert(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '学生成绩管理 · 录分', 'Grade Upsert', 7, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, T.shot('shot-teacher-grades'), { url: 'localhost:5173/#/grades', border: C.info });
  slide.addText('学生成绩页（教师专属）：录分表单 + 成绩列表 + 一键刷新入口', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  T.drawCardTitle(slide, 6.35, 1.1, 3.0, '录分规则', { tag: 'upsert', tagColor: C.info });
  const items = [
    { t: '唯一键：学号+课程', d: '按学号 + 课程唯一提交，已存在则自动更新', c: C.primary },
    { t: '必须填钱包地址', d: '提交时务必填写学生链上钱包，否则实训分计 0', c: C.error },
    { t: '自动算分', d: '填钱包后系统自动计算并写入实训分与综合分', c: C.success },
    { t: '实时预览明细', d: 'compute-training 按钱包实时算分（只算不入库）', c: C.info },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.4, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.6, y, w: 2.8, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.6, y: y + 0.3, w: 2.75, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 8. 一键刷新与成绩统计（设计化）
// ============================================================================
function slide08_RefreshStats(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '一键刷新与成绩统计', 'Refresh & Stats', 8, TOTAL);
  T.drawFooter(slide, FOOTER);
  // 左：一键刷新
  T.drawCard(slide, 0.5, 1.0, 4.35, 3.3);
  T.drawCardTitle(slide, 0.65, 1.1, 4.05, '一键刷新全班实训分', { tag: 'refresh', tagColor: C.primary });
  T.drawCodeBlock(slide, 0.65, 1.5, 4.05, 1.35, ['$ POST /api/grades/refresh-training', '# 批量重算所有已绑定钱包记录的', '# 实训成绩 + 综合成绩'], { title: 'api — grades' });
  const notes = [
    '学生活动数据持续累积后执行',
    '只重算实训分与综合分，教师评分不变',
    '未绑定钱包的记录不会被刷新',
  ];
  notes.forEach((n, i) => {
    const y = 3.05 + i * 0.4;
    slide.addShape('ellipse', { x: 0.8, y: y + 0.08, w: 0.07, h: 0.07, fill: { color: C.primary }, line: { width: 0 } });
    slide.addText(n, { x: 0.97, y, w: 3.75, h: 0.34, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
  // 右：成绩列表与统计
  T.drawCard(slide, 5.15, 1.0, 4.35, 3.3);
  T.drawCardTitle(slide, 5.3, 1.1, 4.05, '成绩列表与统计', { tag: 'list/stats', tagColor: C.info });
  const rows = [
    { k: '成绩列表', v: 'GET /api/grades/list：实训 / 教师 / 综合 3 项 + 实训明细 JSON' },
    { k: '课程统计', v: 'GET /api/grades/stats：按课程聚合三均分 + 人数' },
    { k: '班级名单', v: 'GET /api/auth/class-students：学生与进度概要' },
    { k: '数据范围', v: '教师默认只看自己班级，管理员可看全部' },
  ];
  rows.forEach((r, i) => {
    const y = 1.55 + i * 0.68;
    slide.addText(r.k, { x: 5.45, y, w: 1.1, h: 0.6, fontSize: S.sm, fontFace: F.sans, color: C.info, bold: true, valign: 'top' });
    slide.addText(r.v, { x: 6.6, y, w: 2.8, h: 0.68, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  // 底部：成绩列表操作
  T.drawCard(slide, 0.5, 4.55, 9, 2.0);
  T.drawCardTitle(slide, 0.65, 4.65, 8.7, '成绩列表操作', { tag: '4项', tagColor: C.accent });
  const ops = [
    { t: '按学号 / 姓名 / 课程筛选', c: C.primary },
    { t: '编辑：更新教师评分（自动重算综合分）', c: C.info },
    { t: '删除单条成绩记录', c: C.error },
    { t: '查看学生实训 4 维明细', c: C.success },
  ];
  ops.forEach((o, i) => {
    const x = 0.8 + i * 2.2;
    T.drawCard(slide, x, 5.15, 2.05, 1.0, { border: o.c, borderWidth: 0.5 });
    slide.addText(o.t, { x: x + 0.1, y: 5.25, w: 1.85, h: 0.8, fontSize: S.xs, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
  });
  slide.addText('教师评分更新后系统自动重算综合成绩，无需手动刷新', { x: 0.5, y: 6.35, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.textDim, align: 'center' });
}

// ============================================================================
// 9. 班级搭链进度与卡点分析（设计化）
// ============================================================================
function slide09_BlockAnalysis(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '搭链进度与卡点分析', 'Bottleneck Analysis', 9, TOTAL);
  T.drawFooter(slide, FOOTER);
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.42, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('「学生成绩」页提供班级搭链进度看板：GET /api/chain/tutorial/progress/class（仅教师 / 管理员可见）', { x: 0.65, y: 0.95, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.info, valign: 'middle' });
  // 三大分析维度
  const dims = [
    { t: '完成步数 x/10', d: '每位学生搭链完成步数进度条，一眼看全班推进度', c: C.primary, tag: '进度' },
    { t: '卡点步骤', d: '首个未完成步骤即卡点，定位共性阻塞环节', c: C.error, tag: '卡点' },
    { t: '平均步骤耗时', d: '逐步骤平均耗时，发现耗时异常步骤', c: C.warn, tag: '耗时' },
  ];
  dims.forEach((d, i) => {
    const x = 0.5 + i * 3.1;
    T.drawCard(slide, x, 1.6, 2.9, 1.7, { border: d.c, borderWidth: 0.75 });
    T.drawCardTitle(slide, x + 0.15, 1.72, 2.6, d.t, { tag: d.tag, tagColor: d.c });
    slide.addText(d.d, { x: x + 0.15, y: 2.15, w: 2.6, h: 1.0, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  // 示意进度条
  T.drawCard(slide, 0.5, 3.55, 9, 2.4);
  T.drawCardTitle(slide, 0.65, 3.65, 8.7, '看板示意', { tag: '示例数据', tagColor: C.textDim });
  const demo = [
    { name: '学生 A', done: 10, stuck: '已完成', c: C.success },
    { name: '学生 B', done: 7, stuck: '卡点：Step 8 健康检查', c: C.info },
    { name: '学生 C', done: 4, stuck: '卡点：Step 5 证书核查', c: C.warn },
    { name: '学生 D', done: 2, stuck: '卡点：Step 3 日志出块', c: C.error },
  ];
  demo.forEach((d, i) => {
    const y = 4.12 + i * 0.44;
    slide.addText(d.name, { x: 0.8, y, w: 0.9, h: 0.32, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    slide.addShape('roundRect', { x: 1.8, y: y + 0.1, w: 4.6, h: 0.12, fill: { color: C.border }, line: { width: 0 }, rectRadius: 0.05 });
    slide.addShape('roundRect', { x: 1.8, y: y + 0.1, w: 4.6 * d.done / 10, h: 0.12, fill: { color: d.c }, line: { width: 0 }, rectRadius: 0.05 });
    T.addToken(slide, `${d.done}/10`, { x: 6.5, y, w: 0.7, h: 0.32, fontSize: S.xs, fontFace: F.mono, color: d.c, bold: true });
    slide.addText(d.stuck, { x: 7.3, y, w: 2.1, h: 0.32, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  });
  slide.addShape('roundRect', { x: 0.5, y: 6.15, w: 9, h: 0.7, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 }, rectRadius: 0.05 });
  slide.addText('教学建议：课前查看卡点分布，课堂上集中讲解共性卡点步骤；班级学生名单与进度概要用 GET /api/auth/class-students 查询', { x: 0.65, y: 6.15, w: 8.7, h: 0.7, fontSize: S.xs, fontFace: F.sans, color: C.primary, valign: 'middle' });
}

// ============================================================================
// 10. 联盟业务监管（shot-teacher-eco）
// ============================================================================
function slide10_EcoAudit(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '联盟业务监管', 'Eco Audit', 10, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, T.shot('shot-teacher-eco'), { url: 'localhost:5173/#/eco', border: C.accent });
  slide.addText('教师视角生态实践页：业务操作 + 监管审计入口（audit/overview）', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  T.drawCard(slide, 5.9, 1.0, 3.6, 5.5);
  T.drawCardTitle(slide, 6.05, 1.1, 3.3, '审计要点', { tag: '4项', tagColor: C.accent });
  const items = [
    { t: '审计总览', d: 'GET /api/eco/audit/overview 汇总全班能量发放 / 兑换 / 交易', c: C.primary },
    { t: '凭证对账', d: '每笔发放含业务单号 / 凭证原文 / 阈值 / 校验结果', c: C.info },
    { t: '识别 force 绕过', d: 'force=true 跳过凭证校验的发放会标记 proof_validated=0', c: C.error },
    { t: '操作日志', d: 'GET /api/eco/errors/list 汇总全班日志与错误统计', c: C.success },
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.2;
    slide.addShape('ellipse', { x: 6.1, y: y + 0.06, w: 0.1, h: 0.1, fill: { color: it.c }, line: { width: 0 } });
    slide.addText(it.t, { x: 6.3, y, w: 3.1, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 6.3, y: y + 0.3, w: 3.05, h: 0.75, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 11. 成绩草稿闭环（shot-teacher-report）
// ============================================================================
function slide11_DraftLoop(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '成绩草稿闭环', 'Auto Draft Loop', 11, TOTAL);
  T.drawFooter(slide, FOOTER);
  T.drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, T.shot('shot-teacher-report'), { url: 'localhost:5173/#/report', border: C.success });
  slide.addText('实训报告教师视角：查看学生报告构成，作为教师评分依据', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：闭环流程
  T.drawCard(slide, 5.9, 1.0, 3.6, 4.1);
  T.drawCardTitle(slide, 6.05, 1.1, 3.3, '自动化闭环', { tag: '4步', tagColor: C.success });
  const flow = [
    { n: '1', t: '学生生成报告', d: '实训报告页一键生成', c: C.primary },
    { n: '2', t: '自动创建草稿', d: 'auto-draft：完成 10 步搭链后按钱包建草稿', c: C.info },
    { n: '3', t: '教师补录评分', d: '草稿教师评分默认 0，只需补录', c: C.accent },
    { n: '4', t: '综合成绩定稿', d: '系统自动合成 final_score', c: C.success },
  ];
  flow.forEach((f, i) => {
    const y = 1.6 + i * 0.88;
    T.drawStepCircle(slide, 6.2, y, f.n, 0.3, f.c);
    slide.addText(f.t, { x: 6.6, y: y - 0.02, w: 2.8, h: 0.26, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, valign: 'middle' });
    slide.addText(f.d, { x: 6.6, y: y + 0.24, w: 2.8, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
    if (i < 3) T.drawArrowV(slide, 6.35, y + 0.32, 0.55);
  });
  // 底部说明
  T.drawCard(slide, 5.9, 5.3, 3.6, 1.2);
  T.drawCardTitle(slide, 6.05, 5.4, 3.3, '教师收益', { tag: '减负', tagColor: C.warn });
  slide.addText('草稿已含实训分与 4 维明细，教师只需结合报告补录课堂评分，无需手工汇总实训数据', { x: 6.05, y: 5.75, w: 3.3, h: 0.7, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
}

// ============================================================================
// 12. 课堂运营剧本（设计化）
// ============================================================================
function slide12_Playbook(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '课堂运营剧本 · 绿色出行日', 'Class Playbook', 12, TOTAL);
  T.drawFooter(slide, FOOTER);
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.42, fill: { color: C.success, transparency: 88 }, line: { color: C.success, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('约 1 课时：地铁 / 单车联盟成员发放绿色能量，学生兑换奖励，审计方事后对账', { x: 0.65, y: 0.95, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.success, valign: 'middle' });
  const steps = [
    { n: '0', t: '课前检查', who: '教师', r: '三合约已部署（/eco 页可一键部署）', c: C.textDim },
    { n: '1', t: '切换地铁角色', who: '地铁组', r: '角色卡片显示「地铁集团」', c: C.info },
    { n: '2', t: '发放出行能量', who: '地铁组', r: '凭证 trip_no + distance_km=12 → 学生 +50', c: C.info },
    { n: '2b', t: '防刷演示', who: '地铁组', r: '同 trip_no 重复提交 → 幂等返回，余额不变', c: C.error },
    { n: '3', t: '骑行发放+骑行券', who: '单车组', r: '骑行 +15，另发骑行券（ERC1155）', c: C.warn },
    { n: '4', t: '兑换奖励', who: '学生', r: '兑换生态勋章 / 植树证书，能量回笼国库', c: C.primary },
    { n: '5', t: '余额资产核对', who: '学生', r: '/wallet 页账实一致', c: C.success },
    { n: '6', t: '审计对账', who: '教师', r: '逐笔核对 proof_no → 凭证 → 链上交易', c: C.accent },
  ];
  steps.forEach((s, i) => {
    const y = 1.55 + i * 0.56;
    slide.addShape('rect', { x: 0.65, y, w: 8.7, h: 0.5, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
    slide.addShape('rect', { x: 0.65, y, w: 0.04, h: 0.5, fill: { color: s.c }, line: { width: 0 } });
    T.addToken(slide, s.n, { x: 0.75, y, w: 0.45, h: 0.5, fontSize: S.sm, fontFace: F.mono, color: s.c, bold: true, align: 'center' });
    slide.addText(s.t, { x: 1.3, y, w: 1.9, h: 0.5, fontSize: S.sm, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(s.who, { x: 3.25, y, w: 1.0, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: s.c, bold: true, align: 'center', valign: 'middle' });
    slide.addText(s.r, { x: 4.4, y, w: 4.85, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  });
  slide.addShape('roundRect', { x: 0.5, y: 6.35, w: 9, h: 0.55, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 }, rectRadius: 0.05 });
  slide.addText('讲解要点：权限闭环（未切角色返回 403）· force 绕过校验的审计痕迹（proof_validated=0）· 能量回收形成闭环', { x: 0.65, y: 6.35, w: 8.7, h: 0.55, fontSize: S.xs, fontFace: F.mono, color: C.primary, valign: 'middle' });
}

// ============================================================================
// 13. 常见问题 FAQ（教师视角）
// ============================================================================
function slide13_FAQ(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  T.drawHeader(slide, '常见问题', 'FAQ for Teachers', 13, TOTAL);
  T.drawFooter(slide, FOOTER);
  const faqs = [
    { q: '教师可以修改实训成绩吗？', a: '不可以。实训分由平台按钱包真实行为自动计算，教师只能录教师评分与一键刷新实训分。' },
    { q: '刷新实训分影响教师评分吗？', a: '不影响，refresh-training 只重算实训分与综合分，教师评分保持不变。' },
    { q: '录分后实训分是 0？', a: '提交时务必填写学生钱包地址；未填钱包的记录实训分计 0，补填后刷新即可恢复。' },
    { q: '如何看某学生的得分明细？', a: '用 compute-training 按钱包实时计算 4 维明细，只算不入库，便于录分前预览。' },
    { q: '如何发现绕过凭证的发放？', a: '审计记录中 proof_validated=0 的发放即 force 跳过校验的痕迹，可借此课堂讲解。' },
    { q: '成绩草稿何时生成？', a: '学生生成实训报告时自动创建（需完成 10 步搭链），教师评分默认 0 待补录。' },
  ];
  faqs.forEach((faq, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7;
    const y = 1.0 + row * 1.85;
    T.drawCard(slide, x, y, 4.4, 1.65, { border: C.warn, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.12, w: 0.25, h: 0.25, fill: { color: C.warn }, line: { width: 0 }, rectRadius: 0.04 });
    T.addToken(slide, 'Q', { x: x + 0.1, y: y + 0.12, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.q, { x: x + 0.45, y: y + 0.1, w: 3.85, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.warn, bold: true, valign: 'middle' });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.04 });
    T.addToken(slide, 'A', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.a, { x: x + 0.45, y: y + 0.57, w: 3.85, h: 1.0, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 14. 结束页
// ============================================================================
function slide14_End(pptx) {
  const slide = pptx.addSlide();
  T.drawBackground(slide);
  slide.addShape('hexagon', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 1.5 } });
  slide.addText('FISCO', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.info, bold: true, align: 'center', valign: 'middle' });
  slide.addText('感谢使用', { x: 1, y: 3.3, w: 8, h: 0.5, fontSize: S['2xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('区块链教学实训平台 · 教师使用手册', { x: 1, y: 3.85, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.info, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.45, w: 2.4, h: 0.02, fill: { color: C.info }, line: { width: 0 } });
  slide.addText('技术支持', { x: 1, y: 4.75, w: 8, h: 0.25, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  slide.addText('platform@fisco-chain.edu', { x: 1, y: 5.1, w: 8, h: 0.3, fontSize: S.md, fontFace: F.mono, color: C.info, align: 'center' });
  slide.addText('v1.0 · 2026年8月 · 天择教育', { x: 1, y: 5.6, w: 8, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDimmer, align: 'center' });
  T.drawFooter(slide, FOOTER);
}

// ============================================================================
// 主函数
// ============================================================================
async function main() {
  console.log('开始生成「教师使用手册」PPT...');
  // 启动预校验：所有用到的截图必须真实存在
  T.requireShots(['shot-login', 'shot-teacher-dashboard', 'shot-teacher-grades', 'shot-teacher-eco', 'shot-teacher-report']);
  console.log('截图预校验通过（5 张，其中 shot-login 与学生端共用）');

  const pptx = T.createPptx({ subject: '教师使用手册', title: '区块链教学实训平台 · 教师使用手册' });

  slide01_Cover(pptx);
  slide02_TOC(pptx);
  slide03_Login(pptx);
  slide04_ClassDashboard(pptx);
  slide05_LearningPath(pptx);
  slide06_GradeSystem(pptx);
  slide07_Upsert(pptx);
  slide08_RefreshStats(pptx);
  slide09_BlockAnalysis(pptx);
  slide10_EcoAudit(pptx);
  slide11_DraftLoop(pptx);
  slide12_Playbook(pptx);
  slide13_FAQ(pptx);
  slide14_End(pptx);

  const outDir = T.ensureOutputDir();
  const outputPath = path.join(outDir, '教师使用手册.pptx');
  await pptx.writeFile({ fileName: outputPath });
  console.log(`生成成功: ${outputPath}（共 ${TOTAL} 页，嵌入 4 张教师视角高清截图）`);
}

main().catch((err) => {
  console.error('生成失败:', err);
  process.exit(1);
});
