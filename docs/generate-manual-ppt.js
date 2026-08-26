/**
 * 实训平台操作手册 PPT 生成脚本 v3
 * 核心改进：嵌入平台真实页面截图，实现图文并茂；保持深色设计系统与业务闭环
 */

const PptxGenJS = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

// 截图根目录
const SHOT_DIR = path.join(__dirname, 'assets', 'screenshots');
function shot(name) {
  const p = path.join(SHOT_DIR, name);
  if (!fs.existsSync(p)) throw new Error(`截图缺失: ${p}`);
  return p;
}

// ============================================================================
// 设计系统 - Design Tokens（严格对齐平台深色 UI）
// ============================================================================
const C = {
  bg: '070B16', bg2: '0E1424', panel: '131B2E', panel2: '1A2440',
  border: '1F2A44', border2: '2A3A5E',
  text: 'D6E2FF', textDim: '8E9CBB', textDimmer: '5A6B8A',
  primary: '00E6C3', primary2: '13C2A6',
  accent: 'F5379B', warn: 'FFCF4D', success: '2DD4BF', error: 'FF5470', info: '4D8DFF',
};
const F = { sans: 'Microsoft YaHei', mono: 'Consolas' };
const S = { xs: 9, sm: 10, base: 11, md: 12, lg: 14, xl: 18, '2xl': 24, '3xl': 32, '4xl': 40 };
const PAGE_W = 10, PAGE_H = 7.5;

// ============================================================================
// 基础组件
// ============================================================================
function drawBackground(slide) {
  slide.background = { color: C.bg };
  slide.addShape('rect', { x: 0, y: 0, w: '100%', h: 2.5, fill: { type: 'gradient', color: C.primary, transparency: 94, angle: 135 }, line: { width: 0 } });
  slide.addShape('ellipse', { x: 7.5, y: -0.8, w: 3.5, h: 3.5, fill: { color: C.accent, transparency: 92 }, line: { width: 0 } });
}

function drawHeader(slide, title, subtitle, page, total) {
  slide.addShape('rect', { x: 0, y: 0, w: '100%', h: 0.72, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  slide.addShape('rect', { x: 0.5, y: 0.18, w: 0.05, h: 0.36, fill: { color: C.primary }, line: { width: 0 } });
  slide.addText(title, { x: 0.65, y: 0.12, w: 6.5, h: 0.3, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
  if (subtitle) slide.addText(subtitle, { x: 0.65, y: 0.42, w: 6.5, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  slide.addText(`${page} / ${total}`, { x: 9.0, y: 0.25, w: 0.8, h: 0.22, fontSize: S.xs, fontFace: F.mono, color: C.textDimmer, align: 'right', valign: 'middle' });
}

function drawFooter(slide) {
  slide.addShape('rect', { x: 0, y: 7.18, w: '100%', h: 0.32, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  slide.addText('FISCO 联盟链实训平台 · 操作手册 v3.0', { x: 0.5, y: 7.2, w: 5, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: C.textDimmer, valign: 'middle' });
}

function drawCard(slide, x, y, w, h, opts = {}) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: opts.fill || C.panel }, line: { color: opts.border || C.border, width: opts.borderWidth || 0.75 }, rectRadius: 0.08, shadow: opts.shadow ? { type: 'outer', blur: 6, offset: 2, color: '000000', opacity: 0.3 } : undefined });
}

function drawCardTitle(slide, x, y, w, title, opts = {}) {
  slide.addShape('roundRect', { x, y: y + 0.02, w: 0.04, h: 0.2, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.02 });
  slide.addText(title, { x: x + 0.12, y, w: w - 0.2, h: 0.28, fontSize: S.md, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
  if (opts.tag) {
    const tagW = opts.tag.length * 0.09 + 0.2;
    slide.addShape('roundRect', { x: x + w - tagW - 0.05, y: y + 0.03, w: tagW, h: 0.22, fill: { color: opts.tagColor || C.primary, transparency: 85 }, line: { color: opts.tagColor || C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.04 });
    slide.addText(opts.tag, { x: x + w - tagW - 0.05, y: y + 0.03, w: tagW, h: 0.22, fontSize: S.xs, fontFace: F.mono, color: opts.tagColor || C.primary, bold: true, align: 'center', valign: 'middle' });
  }
}

function addToken(slide, text, opts) { return slide.addText(text, { ...opts, margin: 0, wrap: false, valign: 'middle' }); }

function drawCodeBlock(slide, x, y, w, h, lines, opts = {}) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 }, rectRadius: 0.05 });
  slide.addShape('rect', { x, y, w: 0.04, h, fill: { color: opts.accentColor || C.primary }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.12, y: y + 0.08, w: 0.08, h: 0.08, fill: { color: C.error }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.24, y: y + 0.08, w: 0.08, h: 0.08, fill: { color: C.warn }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.36, y: y + 0.08, w: 0.08, h: 0.08, fill: { color: C.success }, line: { width: 0 } });
  slide.addText(opts.title || 'terminal@fisco-dev', { x: x + 0.5, y: y + 0.06, w: w - 0.6, h: 0.12, fontSize: 7, fontFace: F.mono, color: C.textDimmer, valign: 'middle' });
  lines.forEach((line, i) => {
    slide.addText(line, { x: x + 0.15, y: y + 0.28 + i * 0.155, w: w - 0.25, h: 0.155, fontSize: S.xs, fontFace: F.mono, color: line.startsWith('$') ? C.primary : (line.startsWith('#') ? C.textDimmer : C.text), valign: 'middle' });
  });
}

function drawTag(slide, x, y, text, color = C.primary) {
  const w = text.length * 0.085 + 0.2;
  slide.addShape('roundRect', { x, y, w, h: 0.2, fill: { color, transparency: 85 }, line: { color, width: 0.5, transparency: 60 }, rectRadius: 0.03 });
  slide.addText(text, { x, y, w, h: 0.2, fontSize: S.xs, fontFace: F.mono, color, bold: true, align: 'center', valign: 'middle' });
  return w;
}

function drawArrowH(slide, x, y, w = 0.3) {
  slide.addShape('rect', { x, y: y + 0.08, w: w - 0.08, h: 0.02, fill: { color: C.primary, transparency: 50 }, line: { width: 0 } });
  slide.addShape('rightTriangle', { x: x + w - 0.1, y, w: 0.1, h: 0.18, fill: { color: C.primary, transparency: 50 }, line: { width: 0 } });
}

function drawArrowV(slide, x, y, h = 0.3) {
  slide.addShape('rect', { x: x - 0.01, y, w: 0.02, h: h - 0.08, fill: { color: C.primary, transparency: 50 }, line: { width: 0 } });
  slide.addShape('rightTriangle', { x: x - 0.09, y: y + h - 0.1, w: 0.18, h: 0.1, fill: { color: C.primary, transparency: 50 }, line: { width: 0 }, rotate: 90 });
}

function drawStepCircle(slide, x, y, num, size = 0.4, color = C.primary) {
  slide.addShape('ellipse', { x, y, w: size, h: size, fill: { color }, line: { width: 0 } });
  addToken(slide, String(num), { x, y, w: size, h: size, fontSize: size === 0.4 ? S.base : S.md, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
}

/** 截图卡片：深色框 + 浏览器窗口顶栏 + 图片（contain）+ 标签 */
function drawScreenshot(slide, x, y, w, h, imgPath, opts = {}) {
  // 外框卡片
  drawCard(slide, x, y, w, h, { fill: C.bg2, border: opts.border || C.border2, borderWidth: 0.75 });
  // 浏览器窗口顶栏
  const barH = 0.26;
  slide.addShape('rect', { x: x, y: y, w: w, h: barH, fill: { color: C.panel2 }, line: { width: 0 } });
  // 三个圆点
  slide.addShape('ellipse', { x: x + 0.1, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.error }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.22, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.warn }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.34, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.success }, line: { width: 0 } });
  // URL 文字
  const url = opts.url || 'localhost:5173';
  slide.addText(url, { x: x + 0.5, y: y + 0.04, w: w - 1.4, h: barH - 0.08, fontSize: 7, fontFace: F.mono, color: C.textDimmer, valign: 'middle' });
  // 右上 LIVE 标签
  if (opts.live !== false) {
    drawTag(slide, x + w - 0.62, y + 0.05, 'LIVE', C.success);
  }
  // 图片（高清 1920x1080，cover 模式填满卡片，避免 contain 留白堆叠）
  const imgY = y + barH;
  const imgH = h - barH;
  slide.addShape('rect', { x: x, y: imgY, w: w, h: imgH, fill: { color: C.bg }, line: { width: 0 } });
  // 16:9 图塞进接近正方形卡片：cover 会按高度填满、裁掉左右两侧（平台左右多为边距/侧栏，裁切安全）
  slide.addImage({ path: imgPath, x: x, y: imgY, w: w, h: imgH, sizing: { type: 'cover', w: w, h: imgH }, rounding: true });
}

// ============================================================================
// 幻灯片组合
// ============================================================================

// 1. 封面
function slide01_Cover(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  const cx = 5, cy = 2.2;
  slide.addShape('hexagon', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1.5 } });
  slide.addText('FISCO', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  slide.addText('FISCO 联盟链实训平台', { x: 1, y: 3.1, w: 8, h: 0.6, fontSize: S['4xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('操作手册 · Operation Manual', { x: 1, y: 3.75, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.primary, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.35, w: 2.4, h: 0.02, fill: { color: C.primary }, line: { width: 0 } });
  slide.addText('v3.0 · 2026年8月 · 天择教育', { x: 1, y: 4.6, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  ['10步搭链教程', '6角色业务闭环', '4维成绩评估'].forEach((t, i) => drawTag(slide, 2.2 + i * 2.3, 5.5, t, [C.primary, C.info, C.accent][i]));
  drawFooter(slide);
}

// 2. 目录
function slide02_TOC(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '目录', 'Table of Contents', 2, 26);
  drawFooter(slide);
  const chapters = [
    { num: '01', title: '平台概览', desc: '入口登录 · 系统架构 · 功能模块 · 角色体系', color: C.primary, pages: 'P03-07' },
    { num: '02', title: '10步搭链教程', desc: '链底层 → 联盟接入 → 合约部署 → 链路验证', color: C.info, pages: 'P08-19' },
    { num: '03', title: '生态实践与能量经济', desc: '能量发放 · 资产交易 · 钱包证书 · 区块浏览器', color: C.success, pages: 'P20-25' },
    { num: '04', title: '成绩与报告', desc: '4维评分体系 · 实训报告 · 等级划分 · 常见问题', color: C.accent, pages: 'P26-28' },
  ];
  chapters.forEach((ch, i) => {
    const y = 1.1 + i * 1.4;
    addToken(slide, ch.num, { x: 0.7, y: y + 0.1, w: 0.8, h: 0.6, fontSize: S['2xl'], fontFace: F.mono, color: ch.color, bold: true, align: 'center' });
    slide.addShape('rect', { x: 1.55, y: y + 0.38, w: 0.35, h: 0.02, fill: { color: ch.color, transparency: 50 }, line: { width: 0 } });
    slide.addText(ch.title, { x: 2.05, y: y + 0.08, w: 5, h: 0.32, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(ch.desc, { x: 2.05, y: y + 0.42, w: 6, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDim, valign: 'top' });
    drawTag(slide, 7.8, y + 0.15, ch.pages, ch.color);
  });
}

// 3. 平台入口（登录页截图）
function slide03_Entry(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '平台入口 · 登录', 'Platform Entry', 3, 26);
  drawFooter(slide);
  // 左侧：说明卡片
  drawCard(slide, 0.5, 1.0, 4.0, 5.5);
  drawCardTitle(slide, 0.65, 1.1, 3.7, '登录方式', { tag: '账号密码', tagColor: C.primary });
  const items = [
    { t: '账号密码登录', d: '输入学号/工号与密码，系统经 RSA 加密后转发至 SSO 完成认证', c: C.primary },
    { t: '单点登录会话', d: '登录态写入 localStorage，刷新自动恢复，无需重复输入', c: C.info },
    { t: '角色自动识别', d: 'roleId: 1=管理员 3=教师 4=学生，登录后回填 roleName', c: C.success },
    { t: '默认钱包绑定', d: '学生首次登录写入 0xlearner 钱包，后续不覆盖真实绑定', c: C.warn },
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.1;
    slide.addShape('ellipse', { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fill: { color: it.c }, line: { width: 0 } });
    addToken(slide, String(i + 1), { x: 0.75, y: y + 0.08, w: 0.12, h: 0.12, fontSize: 6, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(it.t, { x: 1.0, y: y, w: 3.3, h: 0.28, fontSize: S.base, fontFace: F.sans, color: it.c, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: 1.0, y: y + 0.3, w: 3.3, h: 0.65, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
  // 右侧：登录页截图
  drawScreenshot(slide, 4.8, 1.0, 4.7, 5.5, shot('login.png'), { url: 'localhost:5173/#/login', border: C.primary });
  // 截图下方注释
  slide.addText('登录页：区块节点星球动画 + 链网状态面板 + 底部区块浏览器滚动条', { x: 4.8, y: 6.55, w: 4.7, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// 4. 系统架构
function slide04_Architecture(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '系统架构', 'System Architecture', 4, 26);
  drawFooter(slide);
  const layers = [
    { name: '前端层', color: C.primary, y: 1.1, items: [{ t: 'Vue 3', d: '响应式框架' }, { t: 'TypeScript', d: '类型安全' }, { t: 'Element Plus', d: 'UI组件库' }, { t: 'Pinia', d: '状态管理' }] },
    { name: '后端层', color: C.info, y: 3.3, items: [{ t: 'FastAPI', d: '异步API框架' }, { t: 'SQLite', d: '业务数据存储' }, { t: 'FISCO SDK', d: '链交互SDK' }, { t: 'WebSocket', d: '实时通信' }] },
    { name: '区块链层', color: C.accent, y: 5.5, items: [{ t: 'FISCO-BCOS', d: '联盟链引擎' }, { t: '4节点PBFT', d: '共识网络' }, { t: 'Solidity', d: '智能合约' }, { t: '控制台', d: '链管理工具' }] },
  ];
  layers.forEach((layer) => {
    slide.addShape('roundRect', { x: 0.5, y: layer.y, w: 1.3, h: 0.4, fill: { color: layer.color, transparency: 80 }, line: { color: layer.color, width: 1 }, rectRadius: 0.05 });
    slide.addText(layer.name, { x: 0.5, y: layer.y, w: 1.3, h: 0.4, fontSize: S.base, fontFace: F.sans, color: layer.color, bold: true, align: 'center', valign: 'middle' });
    layer.items.forEach((item, i) => {
      const x = 2.1 + i * 1.85;
      drawCard(slide, x, layer.y, 1.7, 0.4, { border: layer.color, borderWidth: 0.75 });
      slide.addText(item.t, { x, y: layer.y, w: 1.7, h: 0.18, fontSize: S.sm, fontFace: F.sans, color: C.text, bold: true, align: 'center', valign: 'middle' });
      slide.addText(item.d, { x, y: layer.y + 0.2, w: 1.7, h: 0.18, fontSize: 7, fontFace: F.sans, color: C.textDim, align: 'center', valign: 'middle' });
    });
    if (layer.y < 5) drawArrowV(slide, 1.15, layer.y + 0.45, 0.45);
  });
  slide.addShape('roundRect', { x: 0.5, y: 6.5, w: 9, h: 0.45, fill: { color: C.primary, transparency: 90 }, line: { color: C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.06 });
  slide.addText('数据流向：用户操作 → 前端请求 → 后端API → 区块链交易 → 状态同步回前端', { x: 0.6, y: 6.5, w: 8.8, h: 0.45, fontSize: S.xs, fontFace: F.mono, color: C.primary, align: 'center', valign: 'middle' });
}

// 5. 总览看板（dashboard 截图）
function slide05_Dashboard(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '总览数据看板', 'Dashboard Overview', 5, 26);
  drawFooter(slide);
  // 顶部说明条
  slide.addShape('roundRect', { x: 0.5, y: 0.95, w: 9, h: 0.42, fill: { color: C.info, transparency: 88 }, line: { color: C.info, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
  slide.addText('登录后首页即总览看板：聚合链状态、块高、TPS、节点数、合约部署进度等核心指标，15秒轮询刷新', { x: 0.65, y: 0.95, w: 8.7, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.info, valign: 'middle' });
  // 大截图
  drawScreenshot(slide, 0.5, 1.5, 6.6, 5.4, shot('dashboard.png'), { url: 'localhost:5173/#/dashboard', border: C.primary });
  // 右侧要点
  drawCard(slide, 7.3, 1.5, 2.2, 5.4);
  drawCardTitle(slide, 7.45, 1.6, 1.9, '看板要点', { tag: '6项', tagColor: C.primary });
  const points = [
    { t: '链模式', d: 'FISCO/EVM/沙盒', c: C.primary },
    { t: '块高', d: '实时区块高度', c: C.info },
    { t: 'TPS', d: '每秒交易吞吐', c: C.success },
    { t: '节点数', d: '4共识节点', c: C.warn },
    { t: '合约', d: '部署状态', c: C.accent },
    { t: '进度', d: '10步完成率', c: C.primary2 },
  ];
  points.forEach((p, i) => {
    const y = 2.05 + i * 0.75;
    slide.addShape('ellipse', { x: 7.5, y: y + 0.05, w: 0.1, h: 0.1, fill: { color: p.c }, line: { width: 0 } });
    slide.addText(p.t, { x: 7.7, y, w: 1.6, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: p.c, bold: true, valign: 'middle' });
    slide.addText(p.d, { x: 7.7, y: y + 0.24, w: 1.6, h: 0.2, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  });
}

// 6. 功能模块地图
function slide06_Modules(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '功能模块地图', 'Feature Modules', 6, 26);
  drawFooter(slide);
  const groups = [
    { name: '链底层搭建', color: C.primary, modules: [{ t: '总览', d: '数据看板' }, { t: '搭链云桌面', d: '10步教程' }] },
    { name: '业务合约开发', color: C.info, modules: [{ t: '合约IDE', d: 'Monaco编辑器' }, { t: '合约管理', d: '部署状态' }] },
    { name: '联盟治理与运营', color: C.success, modules: [{ t: '绿色低碳链', d: '6角色发能量' }, { t: 'ERC20钱包', d: '代币余额' }, { t: 'NFT市场', d: '资产交易' }] },
    { name: '链上验证', color: C.accent, modules: [{ t: '接口调试', d: 'API测试' }, { t: '调用监听器', d: '事件推送' }, { t: '区块链浏览器', d: '交易查询' }, { t: '实训报告', d: '成绩报告' }, { t: '我的成绩', d: '学生查看' }] },
  ];
  groups.forEach((g, gi) => {
    const colX = 0.5 + gi * 2.35;
    slide.addShape('roundRect', { x: colX, y: 1.0, w: 2.15, h: 0.32, fill: { color: g.color, transparency: 80 }, line: { color: g.color, width: 0.75 }, rectRadius: 0.05 });
    slide.addText(g.name, { x: colX, y: 1.0, w: 2.15, h: 0.32, fontSize: S.sm, fontFace: F.sans, color: g.color, bold: true, align: 'center', valign: 'middle' });
    g.modules.forEach((m, i) => {
      const y = 1.5 + i * 1.05;
      drawCard(slide, colX, y, 2.15, 0.9, { border: g.color, borderWidth: 0.5 });
      slide.addShape('roundRect', { x: colX + 0.1, y: y + 0.08, w: 0.3, h: 0.03, fill: { color: g.color }, line: { width: 0 }, rectRadius: 0.02 });
      slide.addText(m.t, { x: colX + 0.1, y: y + 0.15, w: 1.95, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
      slide.addText(m.d, { x: colX + 0.1, y: y + 0.48, w: 1.95, h: 0.35, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
    });
  });
}

// 7. 角色体系
function slide07_Roles(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '角色体系', 'Role System', 7, 26);
  drawFooter(slide);
  // 左：6 联盟角色
  drawCard(slide, 0.5, 1.0, 5.5, 5.5);
  drawCardTitle(slide, 0.65, 1.1, 5.2, '联盟角色（6个）', { tag: 'mint白名单', tagColor: C.primary });
  const roles = [
    { name: '管理员', wallet: '0xadmin', energy: '管理', cond: '全局控制', color: C.primary },
    { name: '地铁', wallet: '0xmetro', energy: '+50', cond: '距离≥10km', color: C.info },
    { name: '公交', wallet: '0xbus', energy: '+20', cond: '运营≥5min', color: C.success },
    { name: '共享单车', wallet: '0xbike', energy: '+15', cond: '骑行≥3min', color: C.warn },
    { name: '外卖', wallet: '0xtakeout', energy: '+10', cond: '无需餐具', color: C.accent },
    { name: '回收', wallet: '0xrecycle', energy: '+100', cond: '重量≥1kg', color: C.primary2 },
  ];
  slide.addShape('rect', { x: 0.65, y: 1.5, w: 5.2, h: 0.3, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  ['角色', '钱包', '能量', '条件', '节点'].forEach((h, i) => slide.addText(h, { x: 0.65 + i * 1.05, y: 1.5, w: 1.05, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, align: 'center', valign: 'middle' }));
  roles.forEach((r, i) => {
    const y = 1.8 + i * 0.42;
    slide.addShape('rect', { x: 0.65, y, w: 5.2, h: 0.42, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
    slide.addShape('rect', { x: 0.65, y, w: 0.04, h: 0.42, fill: { color: r.color }, line: { width: 0 } });
    slide.addText(r.name, { x: 0.7, y, w: 1.0, h: 0.42, fontSize: S.sm, fontFace: F.sans, color: r.color, bold: true, align: 'center', valign: 'middle' });
    slide.addText(r.wallet, { x: 1.7, y, w: 1.05, h: 0.42, fontSize: S.xs, fontFace: F.mono, color: C.text, align: 'center', valign: 'middle' });
    slide.addText(r.energy, { x: 2.75, y, w: 1.05, h: 0.42, fontSize: S.sm, fontFace: F.mono, color: C.success, bold: true, align: 'center', valign: 'middle' });
    slide.addText(r.cond, { x: 3.8, y, w: 1.05, h: 0.42, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center', valign: 'middle' });
    slide.addText('node' + Math.floor(i / 2), { x: 4.85, y, w: 1.0, h: 0.42, fontSize: S.xs, fontFace: F.mono, color: C.textDim, align: 'center', valign: 'middle' });
  });
  // 右：4 用户角色
  drawCard(slide, 6.3, 1.0, 3.2, 5.5);
  drawCardTitle(slide, 6.45, 1.1, 2.9, '用户角色（4个）', { tag: '权限', tagColor: C.info });
  const users = [
    { name: '学生', wallet: '0xlearner', perm: '完成实训、查看成绩', color: C.primary },
    { name: '教师', wallet: '0xteacher', perm: '管理学生、评价成绩', color: C.info },
    { name: '访客', wallet: '0xguest', perm: '浏览平台、查看演示', color: C.textDim },
    { name: '超管', wallet: '0xsuperadmin', perm: '系统配置、全局管理', color: C.accent },
  ];
  users.forEach((u, i) => {
    const y = 1.6 + i * 1.1;
    drawCard(slide, 6.45, y, 2.9, 0.9, { border: u.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: 6.55, y: y + 0.1, w: 0.3, h: 0.04, fill: { color: u.color }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(u.name, { x: 6.55, y: y + 0.18, w: 1.2, h: 0.3, fontSize: S.md, fontFace: F.sans, color: u.color, bold: true, valign: 'middle' });
    slide.addText(u.wallet, { x: 7.6, y: y + 0.2, w: 1.6, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.textDim, valign: 'middle' });
    slide.addText(u.perm, { x: 6.55, y: y + 0.5, w: 2.7, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
  slide.addText('联盟角色 0-5 对应私钥，用户角色 6-9 对应私钥，显式 1:1 绑定', { x: 0.5, y: 6.7, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// 8. 教程总览（cloud 截图）
function slide08_TutorialOverview(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '10步搭链教程 · 总览', 'Tutorial Overview', 8, 26);
  drawFooter(slide);
  // 左：cloud 截图
  drawScreenshot(slide, 0.5, 1.0, 5.0, 5.5, shot('cloud.png'), { url: 'localhost:5173/#/cloud', border: C.primary });
  slide.addText('搭链云桌面：左侧 10 步导航 + 总进度环，右侧终端实时输出', { x: 0.5, y: 6.55, w: 5.0, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：四阶段
  drawCard(slide, 5.7, 1.0, 3.8, 5.5);
  drawCardTitle(slide, 5.85, 1.1, 3.5, '四阶段流程', { tag: '严格顺序', tagColor: C.warn });
  const stages = [
    { name: '链底层搭建', range: 'Step 1-4', color: C.primary, items: ['生成配置', '构建证书', '启动节点', '接入控制台'] },
    { name: '联盟组织接入', range: 'Step 5-8', color: C.info, items: ['证书核查', '治理规则', '钱包注册', '健康检查'] },
    { name: '合约部署', range: 'Step 9', color: C.success, items: ['部署 GreenEnergy'] },
    { name: '链路验证', range: 'Step 10', color: C.accent, items: ['5角色发能量'] },
  ];
  stages.forEach((s, i) => {
    const y = 1.6 + i * 1.15;
    drawCard(slide, 5.85, y, 3.5, 0.95, { border: s.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: 5.95, y: y + 0.08, w: 0.8, h: 0.03, fill: { color: s.color }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(s.name, { x: 5.95, y: y + 0.15, w: 2.2, h: 0.28, fontSize: S.base, fontFace: F.sans, color: s.color, bold: true, valign: 'middle' });
    addToken(slide, s.range, { x: 7.95, y: y + 0.15, w: 1.3, h: 0.28, fontSize: S.sm, fontFace: F.mono, color: C.text, align: 'right' });
    slide.addText(s.items.join(' · '), { x: 5.95, y: y + 0.5, w: 3.3, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
    if (i < 3) drawArrowV(slide, 7.6, y + 0.95, 0.2);
  });
}

// 9-18. Step 详情页
function slideStep(pptx, stepNum, page, title, desc, commands, output, tips, stageColor) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, `Step ${stepNum} · ${title}`, '搭链教程', page, 26);
  drawFooter(slide);
  slide.addShape('ellipse', { x: 0.5, y: 0.95, w: 0.7, h: 0.7, fill: { color: stageColor, transparency: 80 }, line: { color: stageColor, width: 1.5 } });
  addToken(slide, String(stepNum), { x: 0.5, y: 0.95, w: 0.7, h: 0.7, fontSize: S['2xl'], fontFace: F.mono, color: stageColor, bold: true, align: 'center' });
  slide.addText(title, { x: 1.35, y: 0.95, w: 5, h: 0.35, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
  slide.addText(desc, { x: 1.35, y: 1.3, w: 8, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  drawCard(slide, 0.5, 1.9, 4.8, 3.8);
  drawCardTitle(slide, 0.65, 2.0, 4.5, '执行命令', { tag: `${commands.length}条`, tagColor: C.info });
  drawCodeBlock(slide, 0.65, 2.35, 4.5, 3.2, commands, { title: 'bash — cloud-desktop' });
  drawCard(slide, 5.6, 1.9, 3.9, 3.8);
  drawCardTitle(slide, 5.75, 2.0, 3.6, '预期输出', { tag: '验证', tagColor: C.success });
  drawCodeBlock(slide, 5.75, 2.35, 3.6, 3.2, output, { title: 'output', accentColor: C.success });
  drawCard(slide, 0.5, 5.9, 9, 0.9, { fill: C.panel, border: C.warn, borderWidth: 0.5 });
  drawCardTitle(slide, 0.65, 5.95, 8.7, '操作要点', { tag: '提示', tagColor: C.warn });
  tips.forEach((t, i) => {
    slide.addShape('ellipse', { x: 0.75, y: 6.35 + i * 0.22 + 0.05, w: 0.05, h: 0.05, fill: { color: C.warn }, line: { width: 0 } });
    slide.addText(t, { x: 0.9, y: 6.32 + i * 0.22, w: 8.4, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
  });
}

// Step 数据
const STEPS = [
  { num: 1, title: '生成链配置', page: 9, desc: '生成 FISCO-BCOS 链配置文件，含4节点PBFT共识配置', commands: ['$ cd /root/fisco', '$ curl -LO https://github.com/FISCO-BCOS/build_chain.sh', '$ chmod +x build_chain.sh', '$ bash build_chain.sh -l "127.0.0.1:4" -p 30300,20200,8545'], output: ['[OK] Downloading build_chain.sh', '[INFO] FISCO-BCOS Path   : bin/fisco-bcos', '[INFO] Start Port       : 30300', '[INFO] Node Count       : 4', '[INFO] Output Dir       : nodes/127.0.0.1', '[INFO] All completed.'], tips: ['确保已安装 OpenSSL 和 curl', '配置文件位于 nodes/127.0.0.1 目录', '4个节点端口：30300-30303'], color: C.primary },
  { num: 2, title: '构建链证书', page: 10, desc: '生成 CA 证书、机构证书和节点证书，用于链身份验证', commands: ['$ cd /root/fisco/nodes/127.0.0.1', '$ bash generate_cert.sh', '$ ls -la cert/', '$ openssl x509 -in cert/ca.crt -text -noout | head -5'], output: ['[OK] CA certificate generated', '[OK] Agency certificate generated', '[OK] Node certificates generated (4 nodes)', 'cert/ca.crt  cert/agency.crt', 'cert/node0/node.crt  cert/node1/node.crt', 'Issuer: CN=FISCO-BCOS-CA'], tips: ['证书文件位于 cert/ 目录', 'SDK证书需复制到控制台', '证书链：CA → 机构 → 节点'], color: C.primary },
  { num: 3, title: '启动链节点', page: 11, desc: '启动 4 个联盟链节点，验证节点正常运行和持续出块', commands: ['$ cd /root/fisco/nodes/127.0.0.1', '$ bash start_all.sh', '$ ps -ef | grep fisco-bcos | wc -l', '$ tail -f node0/log/log_INFO | grep "+++"'], output: ['[OK] node0 started successfully', '[OK] node1 started successfully', '[OK] node2 started successfully', '[OK] node3 started successfully', '4  (4个进程运行中)', '+++ generating seal on: 1 txs'], tips: ['4个节点全部启动成功', '查看日志确认 PBFT 持续出块', '+++ 表示 sealer 开始打包'], color: C.primary },
  { num: 4, title: '接入控制台', page: 12, desc: '配置 SDK 证书并接入区块链控制台，进行链上交互验证', commands: ['$ cd /root/fisco/console', '$ cp -r ../nodes/127.0.0.1/sdk_cert ./', '$ bash start.sh', '[group:1]> getBlockNumber', '[group:1]> getSealerList'], output: ['[OK] SDK certificate copied', '[INFO] Console connected to FISCO-BCOS', 'Welcome to FISCO BCOS console!', 'blockNumber = 1', 'SealerList (4):', '  0x1234...node0  0x5678...node1'], tips: ['SDK证书必须从节点目录复制', '控制台通过 Channel 协议连接', '运维四件套：块高/Peer/Sealer/Group'], color: C.primary },
  { num: 5, title: '组织证书核查', page: 13, desc: '验证联盟组织的证书有效性，确保节点身份合法', commands: ['$ cd /root/fisco/nodes/127.0.0.1', '$ for i in 0 1 2 3; do', '    openssl verify -CAfile cert/ca.crt cert/node$i/node.crt', '  done', '$ cat cert/node0/node.cnf | grep -A2 "[v3_req]"'], output: ['node0: OK', 'node1: OK', 'node2: OK', 'node3: OK', '[v3_req]', '  basicConstraints = CA:FALSE'], tips: ['检查证书颁发者和主题', '确保证书链完整有效', '4个节点证书全部验证通过'], color: C.info },
  { num: 6, title: '联盟治理规则', page: 14, desc: '配置 6 大联盟角色的治理规则和业务权限映射', commands: ['$ cat /root/fisco/roles.json', '$ curl http://localhost:8000/api/eco/roles', '$ curl http://localhost:8000/api/eco/energy/rules'], output: ['{', '  "metro":   { "energy": 50, "proof": "distance>=10km" },', '  "bus":     { "energy": 20, "proof": "duration>=5min" },', '  "bike":    { "energy": 15, "proof": "duration>=3min" },', '  "takeout": { "energy": 10, "proof": "no_cutlery=1" },', '  "recycle": { "energy": 100, "proof": "weight>=1kg" }', '}'], tips: ['每个角色有独立钱包地址', '能量发放需满足业务凭证阈值', '管理员不发能量避免利益冲突'], color: C.info },
  { num: 7, title: '钱包注册', page: 15, desc: '注册用户钱包并与联盟角色建立显式 1:1 私钥绑定', commands: ['$ curl -X POST http://localhost:8000/api/wallet/register \\', '    -H "Content-Type: application/json" \\', '    -d \'{"wallet":"0xlearner","role":"student"}\'', '$ curl http://localhost:8000/api/eco/wallets'], output: ['{', '  "success": true,', '  "wallet": "0xlearner",', '  "role": "student",', '  "balance": 0', '}', '6 alliance wallets + 4 user wallets registered'], tips: ['钱包地址必须唯一', '联盟角色 0-5 对应私钥', '用户角色 6-9 对应私钥'], color: C.info },
  { num: 8, title: '健康检查', page: 16, desc: '检查节点状态、合约部署情况，确保系统健康运行', commands: ['$ curl http://localhost:8000/api/chain/status', '$ curl http://localhost:8000/api/contracts/status', '$ curl http://localhost:8000/api/eco/health'], output: ['{ "mode": "docker", "engine": "fisco-bcos",', '  "height": 100, "nodes": 4,', '  "status": "healthy" }', 'GreenEnergy: not deployed', 'PlantCertificate: not deployed', 'EcoBadge: not deployed'], tips: ['节点高度应持续增长', '所有节点状态应为 healthy', '合约未部署是正常状态（Step 9 部署）'], color: C.info },
  { num: 9, title: '部署 GreenEnergy', page: 17, desc: '编译并部署 GreenEnergy ERC20 智能合约到联盟链', commands: ['$ cd /root/fisco/console', '$ [group:1]> deploy GreenEnergy 1000000', '$ curl -X POST http://localhost:8000/api/contracts/deploy \\', '    -d \'{"name":"GreenEnergy","owner":"0xadmin"}\''], output: ['contract address: 0x1234...5678', 'transaction hash: 0xabcd...1234', 'Gas used: 1500000', '', '{ "success": true,', '  "address": "0x1234...5678",', '  "deployer": "0xadmin" }'], tips: ['合约部署者必须是 0xadmin', '记录合约地址用于后续操作', 'GreenEnergy 是 ERC20 标准代币'], color: C.success },
  { num: 10, title: '链路验证', page: 18, desc: '使用 5 个联盟角色完成能量发放的完整链路验证', commands: ['$ curl -X POST http://localhost:8000/api/eco/energy/issue \\', '    -d \'{"role":"metro","distance":15,"to":"0xlearner"}\'', '$ curl http://localhost:8000/api/wallet/balance/0xlearner'], output: ['{ "success": true,', '  "energy": 50,', '  "tx_hash": "0xabcd...1234",', '  "proof_no": "metro-001" }', '', 'Balance of 0xlearner: 50'], tips: ['5个角色都需要验证', '余额应与发放能量一致', '防重复：相同 proof_no 不可重复发放'], color: C.accent },
];

// 19. 能量发放规则
function slide19_EnergyRules(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '能量发放规则', 'Energy Issuance Rules', 19, 26);
  drawFooter(slide);
  drawCard(slide, 0.5, 1.0, 9, 3.5);
  drawCardTitle(slide, 0.65, 1.1, 8.7, '6角色能量发放映射表', { tag: 'mint白名单', tagColor: C.primary });
  const rules = [
    { role: '地铁', wallet: '0xmetro', proof: 'distance >= 10km', energy: '+50', signer: '0xmetro', color: C.info },
    { role: '公交', wallet: '0xbus', proof: 'duration >= 5min', energy: '+20', signer: '0xbus', color: C.success },
    { role: '共享单车', wallet: '0xbike', proof: 'duration >= 3min', energy: '+15', signer: '0xbike', color: C.warn },
    { role: '外卖', wallet: '0xtakeout', proof: 'no_cutlery = 1', energy: '+10', signer: '0xtakeout', color: C.accent },
    { role: '回收', wallet: '0xrecycle', proof: 'weight >= 1kg', energy: '+100', signer: '0xrecycle', color: C.primary2 },
    { role: '管理员', wallet: '0xadmin', proof: '—', energy: '0', signer: 'owner', color: C.primary },
  ];
  slide.addShape('rect', { x: 0.65, y: 1.5, w: 8.7, h: 0.32, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  const widths = [1.2, 1.8, 2.7, 1.2, 1.8];
  ['角色', '钱包地址', '业务凭证', '能量', '签名者'].forEach((h, i) => {
    let x = 0.65;
    for (let j = 0; j < i; j++) x += widths[j];
    slide.addText(h, { x, y: 1.5, w: widths[i], h: 0.32, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, align: 'center', valign: 'middle' });
  });
  rules.forEach((r, i) => {
    const y = 1.82 + i * 0.38;
    slide.addShape('rect', { x: 0.65, y, w: 8.7, h: 0.38, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
    slide.addShape('rect', { x: 0.65, y, w: 0.04, h: 0.38, fill: { color: r.color }, line: { width: 0 } });
    const cells = [{ t: r.role, c: r.color, b: true, f: F.sans }, { t: r.wallet, c: C.text, b: false, f: F.mono }, { t: r.proof, c: C.text, b: false, f: F.mono }, { t: r.energy, c: C.success, b: true, f: F.mono }, { t: r.signer, c: C.textDim, b: false, f: F.mono }];
    let x = 0.65;
    cells.forEach((cell, j) => {
      slide.addText(cell.t, { x, y, w: widths[j], h: 0.38, fontSize: S.xs, fontFace: cell.f, color: cell.c, bold: cell.b, align: 'center', valign: 'middle' });
      x += widths[j];
    });
  });
  // 业务闭环
  drawCard(slide, 0.5, 4.8, 9, 2.0);
  drawCardTitle(slide, 0.65, 4.9, 8.7, '能量发放业务闭环', { tag: '5步', tagColor: C.success });
  const flow = [{ n: '1', t: '联盟角色签名', c: C.primary }, { n: '2', t: '凭证阈值校验', c: C.info }, { n: '3', t: '链上 mint 铸造', c: C.success }, { n: '4', t: '防重复记录', c: C.warn }, { n: '5', t: '余额同步更新', c: C.accent }];
  flow.forEach((f, i) => {
    const x = 0.8 + i * 1.75;
    drawStepCircle(slide, x, 5.4, f.n, 0.35, f.c);
    slide.addText(f.t, { x: x - 0.3, y: 5.8, w: 0.95, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, align: 'center', valign: 'top' });
    if (i < 4) drawArrowH(slide, x + 0.35, 5.5, 1.4);
  });
  slide.addText('UNIQUE(proof_no, role_key) 索引防止同一业务凭证重复发放能量', { x: 0.5, y: 6.4, w: 9, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.info, align: 'center' });
}

// 20. 能量发放操作（eco 截图）
function slide20_EnergyOperation(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '能量发放操作', 'Energy Issuance Operation', 20, 26);
  drawFooter(slide);
  // 左：eco 截图
  drawScreenshot(slide, 0.5, 1.0, 5.2, 5.5, shot('eco.png'), { url: 'localhost:5173/#/eco', border: C.success });
  slide.addText('绿色低碳联盟链：6角色卡片切换 + 能量发放凭证表单（含阈值校验）', { x: 0.5, y: 6.55, w: 5.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：5步流程
  drawCard(slide, 5.9, 1.0, 3.6, 5.5);
  drawCardTitle(slide, 6.05, 1.1, 3.3, '操作流程', { tag: '5步', tagColor: C.primary });
  const steps = [
    { n: '1', t: '选择联盟角色', d: '在生态实践页点击角色卡片切换', c: C.primary },
    { n: '2', t: '填写业务凭证', d: '输入符合阈值的业务数据', c: C.info },
    { n: '3', t: '签名确认', d: '系统用联盟钱包私钥签名', c: C.success },
    { n: '4', t: '链上铸造', d: '调用 GreenEnergy.mint() 上链', c: C.warn },
    { n: '5', t: '记录更新', d: '写入能量记录并更新余额', c: C.accent },
  ];
  steps.forEach((s, i) => {
    const y = 1.6 + i * 0.95;
    drawStepCircle(slide, 6.1, y, s.n, 0.3, s.c);
    slide.addText(s.t, { x: 6.5, y: y - 0.02, w: 2.9, h: 0.25, fontSize: S.base, fontFace: F.sans, color: s.c, bold: true, valign: 'middle' });
    slide.addText(s.d, { x: 6.5, y: y + 0.22, w: 2.9, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    if (i < 4) drawArrowV(slide, 6.25, y + 0.32, 0.6);
  });
}

// 21. 资产市场交易（nft 截图）
function slide21_Market(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '资产市场交易', 'Energy Asset Market', 21, 26);
  drawFooter(slide);
  // 顶部交易流程
  drawCard(slide, 0.5, 1.0, 9, 1.5);
  drawCardTitle(slide, 0.65, 1.1, 8.7, '交易流程', { tag: '4步闭环', tagColor: C.primary });
  const flow = [{ n: '1', t: '上架', d: '能量资产挂牌', c: C.primary }, { n: '2', t: '浏览', d: '市场列表展示', c: C.info }, { n: '3', t: '购买', d: '余额完成交易', c: C.success }, { n: '4', t: '同步', d: '更新双方余额', c: C.accent }];
  flow.forEach((f, i) => {
    const x = 0.9 + i * 2.2;
    drawStepCircle(slide, x, 1.6, f.n, 0.28, f.c);
    slide.addText(f.t, { x: x - 0.2, y: 1.95, w: 0.7, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: f.c, bold: true, align: 'center', valign: 'middle' });
    slide.addText(f.d, { x: x - 0.4, y: 2.18, w: 1.1, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center', valign: 'middle' });
    if (i < 3) drawArrowH(slide, x + 0.28, 1.7, 1.92);
  });
  // 下方：nft 截图 + 规则
  drawScreenshot(slide, 0.5, 2.7, 5.5, 3.8, shot('nft.png'), { url: 'localhost:5173/#/nft', border: C.accent });
  drawCard(slide, 6.2, 2.7, 3.3, 3.8);
  drawCardTitle(slide, 6.35, 2.8, 3.0, '市场规则', { tag: '5条', tagColor: C.warn });
  const rules = [
    '已上架资产显示 On Sale 标签，隐藏上架按钮防重复',
    '购买/取消后同步刷新市场列表和钱包余额',
    '取消上架后资产返回钱包，可重新上架',
    '交易记录写入链上并同步到业务账本',
    '价格由卖家设定，用 GreenEnergy 计价',
  ];
  rules.forEach((r, i) => {
    slide.addShape('ellipse', { x: 6.45, y: 3.35 + i * 0.55 + 0.05, w: 0.06, h: 0.06, fill: { color: C.warn }, line: { width: 0 } });
    slide.addText(r, { x: 6.6, y: 3.3 + i * 0.55, w: 2.75, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// 22. 钱包与证书（wallet 截图）
function slide22_Wallet(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, 'ERC20 钱包与证书勋章', 'Wallet & Certificates', 22, 26);
  drawFooter(slide);
  // 左：wallet 截图
  drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, shot('wallet.png'), { url: 'localhost:5173/#/wallet', border: C.info });
  slide.addText('钱包页：代币余额 + 转账 + NFT 资产展示 + 能量发放记录', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：证书 vs 勋章
  drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  drawCardTitle(slide, 6.35, 1.1, 3.0, '证书 vs 勋章', { tag: 'NFT', tagColor: C.accent });
  slide.addShape('rect', { x: 6.35, y: 1.5, w: 3.0, h: 0.3, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  ['对比项', '证书/勋章'].forEach((h, i) => slide.addText(h, { x: 6.35 + i * 1.5, y: 1.5, w: 1.5, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, align: 'center', valign: 'middle' }));
  const rows = [
    { k: '代币标准', v: 'ERC721 / ERC1155' },
    { k: '唯一性', v: '独一无二 / 可批量' },
    { k: '创建权限', v: '0xadmin / 联盟角色' },
    { k: '图片要求', v: '均需图片URL' },
  ];
  rows.forEach((r, i) => {
    const y = 1.8 + i * 0.5;
    slide.addShape('rect', { x: 6.35, y, w: 3.0, h: 0.5, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
    slide.addText(r.k, { x: 6.4, y, w: 1.4, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.textDim, bold: true, valign: 'middle' });
    slide.addText(r.v, { x: 7.8, y, w: 1.5, h: 0.5, fontSize: S.xs, fontFace: F.mono, color: C.accent, valign: 'middle' });
  });
  // 创建流程
  drawCardTitle(slide, 6.35, 4.0, 3.0, '创建流程', { tag: '5步', tagColor: C.success });
  const flow = [{ n: '1', t: '选类型', c: C.primary }, { n: '2', t: '填信息', c: C.info }, { n: '3', t: '权限校验', c: C.success }, { n: '4', t: '链上mint', c: C.warn }, { n: '5', t: '钱包展示', c: C.accent }];
  flow.forEach((f, i) => {
    const x = 6.4 + i * 0.58;
    drawStepCircle(slide, x, 4.5, f.n, 0.25, f.c);
    slide.addText(f.t, { x: x - 0.15, y: 4.78, w: 0.55, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.text, align: 'center', valign: 'top' });
    if (i < 4) drawArrowH(slide, x + 0.25, 4.6, 0.33);
  });
  slide.addText('证书勋章创建后可在钱包查看，支持 NFT 市场挂牌', { x: 6.2, y: 6.2, w: 3.3, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
}

// 23. 区块链浏览器（explorer 截图）
function slide23_Explorer(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '区块链浏览器', 'Chain Explorer', 23, 26);
  drawFooter(slide);
  // 大截图
  drawScreenshot(slide, 0.5, 1.0, 6.2, 5.5, shot('explorer.png'), { url: 'localhost:5173/#/explorer', border: C.info });
  slide.addText('区块链浏览器：区块列表 / 交易详情 / 合约查询 / 地址余额追溯', { x: 0.5, y: 6.55, w: 6.2, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：功能说明
  drawCard(slide, 6.9, 1.0, 2.6, 5.5);
  drawCardTitle(slide, 7.05, 1.1, 2.3, '浏览器能力', { tag: '4维', tagColor: C.primary });
  const feats = [
    { t: '区块查询', d: '块高/哈希/时间/交易数', c: C.primary },
    { t: '交易追溯', d: 'tx hash / from / to / input', c: C.info },
    { t: '合约状态', d: '部署地址 / has_code', c: C.success },
    { t: '地址余额', d: 'GreenEnergy 余额查询', c: C.accent },
  ];
  feats.forEach((f, i) => {
    const y = 1.6 + i * 1.15;
    slide.addShape('roundRect', { x: 7.05, y: y, w: 2.3, h: 0.04, fill: { color: f.c }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(f.t, { x: 7.05, y: y + 0.1, w: 2.3, h: 0.3, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, align: 'center', valign: 'middle' });
    slide.addText(f.d, { x: 7.05, y: y + 0.4, w: 2.3, h: 0.6, fontSize: S.xs, fontFace: F.sans, color: C.text, align: 'center', valign: 'top' });
  });
}

// 24. 成绩计算（my-grades 截图）
function slide24_Grades(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '成绩计算体系', 'Grade Calculation', 24, 26);
  drawFooter(slide);
  // 左：my-grades 截图
  drawScreenshot(slide, 0.5, 1.0, 5.0, 5.5, shot('my-grades.png'), { url: 'localhost:5173/#/my-grades', border: C.accent });
  slide.addText('我的成绩：4维评分雷达 + 实训得分 + 教师评价 + 班级排名', { x: 0.5, y: 6.55, w: 5.0, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：4维卡片
  const dims = [
    { name: '链搭建', score: 30, items: '10步完成度/命令准确性', color: C.primary },
    { name: '合约开发', score: 25, items: 'IDE创建/编译/部署', color: C.info },
    { name: '链上验证', score: 25, items: '能量发放/市场/证书', color: C.success },
    { name: '联盟治理', score: 20, items: '角色切换/凭证填写', color: C.accent },
  ];
  dims.forEach((d, i) => {
    const y = 1.0 + i * 1.2;
    drawCard(slide, 5.7, y, 3.8, 1.05, { border: d.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: 5.85, y: y + 0.08, w: 3.5, h: 0.04, fill: { color: d.color }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addText(d.name, { x: 5.85, y: y + 0.15, w: 2, h: 0.3, fontSize: S.md, fontFace: F.sans, color: d.color, bold: true, valign: 'middle' });
    addToken(slide, `${d.score}`, { x: 8.4, y: y + 0.13, w: 0.9, h: 0.3, fontSize: S.lg, fontFace: F.mono, color: C.warn, bold: true, align: 'center' });
    slide.addText('分', { x: 9.0, y: y + 0.18, w: 0.3, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
    slide.addText(d.items, { x: 5.85, y: y + 0.5, w: 3.5, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    // 进度条
    slide.addShape('roundRect', { x: 5.85, y: y + 0.85, w: 3.5, h: 0.05, fill: { color: C.border }, line: { width: 0 }, rectRadius: 0.02 });
    slide.addShape('roundRect', { x: 5.85, y: y + 0.85, w: 3.5 * d.score / 30, h: 0.05, fill: { color: d.color }, line: { width: 0 }, rectRadius: 0.02 });
  });
  // 公式
  slide.addShape('roundRect', { x: 5.7, y: 6.0, w: 3.8, h: 0.5, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1 }, rectRadius: 0.08 });
  slide.addText('final = train×0.6 + teacher×0.4', { x: 5.8, y: 6.0, w: 3.6, h: 0.5, fontSize: S.sm, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
}

// 25. 实训报告（report 截图）
function slide25_Report(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '实训报告与等级', 'Training Report', 25, 26);
  drawFooter(slide);
  // 左：report 截图
  drawScreenshot(slide, 0.5, 1.0, 5.5, 5.5, shot('report.png'), { url: 'localhost:5173/#/report', border: C.success });
  slide.addText('实训报告：成绩构成 + 等级评定 + 各维度明细 + 改进建议', { x: 0.5, y: 6.55, w: 5.5, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 右：等级划分
  drawCard(slide, 6.2, 1.0, 3.3, 5.5);
  drawCardTitle(slide, 6.35, 1.1, 3.0, '等级划分', { tag: '5级', tagColor: C.success });
  const grades = [
    { grade: '优秀', range: '90-100', desc: '全面掌握，独立完成', color: C.success },
    { grade: '良好', range: '80-89', desc: '较好掌握，少量待完善', color: C.primary },
    { grade: '中等', range: '70-79', desc: '基本掌握，部分需加强', color: C.info },
    { grade: '及格', range: '60-69', desc: '完成基础，需练习', color: C.warn },
    { grade: '不及格', range: '<60', desc: '未完成核心，需重修', color: C.error },
  ];
  grades.forEach((g, i) => {
    const y = 1.55 + i * 0.92;
    drawCard(slide, 6.35, y, 3.0, 0.8, { border: g.color, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: 6.45, y: y + 0.1, w: 0.8, h: 0.28, fill: { color: g.color, transparency: 80 }, line: { color: g.color, width: 0.75 }, rectRadius: 0.04 });
    slide.addText(g.grade, { x: 6.45, y: y + 0.1, w: 0.8, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: g.color, bold: true, align: 'center', valign: 'middle' });
    addToken(slide, g.range, { x: 7.35, y: y + 0.12, w: 0.95, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.text, valign: 'middle' });
    slide.addText(g.desc, { x: 6.45, y: y + 0.42, w: 2.8, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
  });
}

// 26. 常见问题与结束
function slide26_FAQEnd(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  drawHeader(slide, '常见问题', 'FAQ', 26, 26);
  drawFooter(slide);
  const faqs = [
    { q: '教程步骤可以跳过吗？', a: '不可以，10步严格按顺序执行，每步完成才能进入下一步。' },
    { q: '能量发放失败怎么办？', a: '检查业务凭证是否满足阈值，确认使用联盟角色钱包签名。' },
    { q: '资产上架后能改价格吗？', a: '需先取消上架，改价格后重新上架。' },
    { q: '证书和勋章的区别？', a: '证书是ERC721唯一，勋章是ERC1155可批量，权限也不同。' },
    { q: '成绩如何计算？', a: 'training_score × 0.6 + teacher_score × 0.4。' },
    { q: '如何切换联盟角色？', a: '在生态实践页点击角色卡片切换，每角色独立钱包。' },
  ];
  faqs.forEach((faq, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7;
    const y = 1.0 + row * 1.7;
    drawCard(slide, x, y, 4.4, 1.5, { border: C.info, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.1, w: 0.25, h: 0.25, fill: { color: C.info }, line: { width: 0 }, rectRadius: 0.04 });
    addToken(slide, 'Q', { x: x + 0.1, y: y + 0.1, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.q, { x: x + 0.45, y: y + 0.08, w: 3.85, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.info, bold: true, valign: 'middle' });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.6, w: 0.25, h: 0.25, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.04 });
    addToken(slide, 'A', { x: x + 0.1, y: y + 0.6, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center' });
    slide.addText(faq.a, { x: x + 0.45, y: y + 0.55, w: 3.85, h: 0.85, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// 结束页（第27页，不计入目录页码但作为收尾）
function slideEnd(pptx) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  slide.addShape('hexagon', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 1.5 } });
  slide.addText('FISCO', { x: 4.4, y: 1.8, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  slide.addText('感谢使用', { x: 1, y: 3.3, w: 8, h: 0.5, fontSize: S['2xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText('FISCO 联盟链实训平台', { x: 1, y: 3.85, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: C.primary, align: 'center' });
  slide.addShape('rect', { x: 3.8, y: 4.45, w: 2.4, h: 0.02, fill: { color: C.primary }, line: { width: 0 } });
  slide.addText('技术支持', { x: 1, y: 4.75, w: 8, h: 0.25, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  slide.addText('platform@fisco-chain.edu', { x: 1, y: 5.1, w: 8, h: 0.3, fontSize: S.md, fontFace: F.mono, color: C.primary, align: 'center' });
  slide.addText('v3.0 · 2026年8月 · 天择教育', { x: 1, y: 5.6, w: 8, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDimmer, align: 'center' });
  drawFooter(slide);
}

// ============================================================================
// 主函数
// ============================================================================
async function main() {
  console.log('开始生成实训平台操作手册 PPT v3...');
  // 预校验所有截图存在
  ['login', 'dashboard', 'cloud', 'eco', 'nft', 'wallet', 'explorer', 'my-grades', 'report'].forEach(n => shot(`${n}.png`));
  console.log('所有截图校验通过');

  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'FISCO 联盟链实训平台';
  pptx.company = '天择教育';
  pptx.subject = '实训平台操作手册';
  pptx.title = 'FISCO 联盟链实训平台操作手册';

  slide01_Cover(pptx);
  slide02_TOC(pptx);
  slide03_Entry(pptx);
  slide04_Architecture(pptx);
  slide05_Dashboard(pptx);
  slide06_Modules(pptx);
  slide07_Roles(pptx);
  slide08_TutorialOverview(pptx);
  STEPS.forEach(s => slideStep(pptx, s.num, s.page, s.title, s.desc, s.commands, s.output, s.tips, s.color));
  slide19_EnergyRules(pptx);
  slide20_EnergyOperation(pptx);
  slide21_Market(pptx);
  slide22_Wallet(pptx);
  slide23_Explorer(pptx);
  slide24_Grades(pptx);
  slide25_Report(pptx);
  slide26_FAQEnd(pptx);
  slideEnd(pptx);

  const outputPath = path.join(__dirname, 'output', '实训平台操作手册.pptx');
  await pptx.writeFile({ fileName: outputPath });
  console.log(`PPT v3 生成成功: ${outputPath}`);
  console.log('共 27 页，嵌入 9 张平台真实截图，深色设计系统 + 业务闭环');
}

main().catch(err => {
  console.error('生成失败:', err);
  process.exit(1);
});
