/**
 * FISCO 联盟链实训平台 · 使用手册 PPT 生成脚本
 * 设计系统与 frontend/src/styles/global.scss（--dq-* tokens）逐值一致：
 *   深蓝灰底 #070B16 + 青绿主色 #00E6C3 + 品红强调 #F5379B，微软雅黑 + Consolas
 * 画布：LAYOUT_WIDE 13.33 x 7.5
 * 输出：docs/output/实训平台使用手册.pptx
 */
const path = require('path');
const PptxGenJS = require('pptxgenjs');

// ================= 设计令牌（与平台一致） =================
const C = {
  bg: '070B16', bg2: '0E1424', panel: '131B2E', panel2: '1A2440',
  border: '1F2A44', border2: '2A3A5E',
  text: 'D6E2FF', dim: '8E9CBB', dimmer: '5A6B8A',
  primary: '00E6C3', primary2: '13C2A6', primary3: '0A9D88', primary4: '0E7A6B',
  accent: 'F5379B', warn: 'FFCF4D', success: '2DD4BF', error: 'FF5470', info: '4D8DFF',
};
const F = { sans: 'Microsoft YaHei', mono: 'Consolas' };
const W = 13.33, H = 7.5, M = 0.5, TOTAL = 16;
const IMG_DIR = path.join(__dirname, 'assets', 'screenshots', 'ppt');
const IMG = (n) => path.join(IMG_DIR, n);

const pres = new PptxGenJS();
pres.layout = 'LAYOUT_WIDE';
pres.author = '天择教育';
pres.company = '天择教育';
pres.subject = '使用手册';
pres.title = 'FISCO 联盟链实训平台 · 使用手册';

let pageNo = 0;

// ================= 基础工具 =================
function txtW(t, pt) { // 估算文本宽度（英寸）：CJK 全宽，拉丁 0.55
  let w = 0;
  for (const ch of t) w += ch.charCodeAt(0) > 0x2e7f ? pt / 72 : (pt * 0.55) / 72;
  return w;
}
function shadow() { return { type: 'outer', blur: 7, offset: 2, color: '000000', opacity: 0.35 }; }

function deco(s) { // 母题：六边形轮廓 + 微光
  s.addShape('ellipse', { x: -1.6, y: -1.9, w: 4.2, h: 3.4, fill: { color: C.primary, transparency: 95 }, line: { width: 0 } });
  s.addShape('hexagon', { x: 12.55, y: 6.35, w: 1.35, h: 1.2, fill: { type: 'none' }, line: { color: C.border, width: 1 } });
  s.addShape('hexagon', { x: 12.25, y: 6.7, w: 0.55, h: 0.5, fill: { type: 'none' }, line: { color: C.border2, width: 0.75 } });
}

function header(s, section, title, route, stepTag) {
  s.addText(section, { x: M, y: 0.4, w: 7, h: 0.26, fontSize: 12, fontFace: F.mono, color: C.dimmer, charSpacing: 2, margin: 0 });
  s.addText(title, { x: M, y: 0.66, w: 8.8, h: 0.56, fontSize: 27, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  // 右上：路由胶囊（像浏览器地址栏）
  s.addShape('roundRect', { x: 11.03, y: 0.52, w: 1.8, h: 0.44, fill: { color: C.panel }, line: { color: C.border2, width: 0.75 }, rectRadius: 0.08 });
  s.addShape('hexagon', { x: 11.18, y: 0.65, w: 0.18, h: 0.16, fill: { type: 'none' }, line: { color: C.primary, width: 1 } });
  s.addText(route, { x: 11.4, y: 0.52, w: 1.4, h: 0.44, fontSize: 13, fontFace: F.mono, color: C.primary, valign: 'middle', margin: 0 });
  if (stepTag) {
    const cw = txtW(stepTag, 12) + 0.3;
    s.addShape('roundRect', { x: 10.85 - cw, y: 0.62, w: cw, h: 0.26, fill: { color: C.accent, transparency: 86 }, line: { color: C.accent, width: 0.5, transparency: 55 }, rectRadius: 0.05 });
    s.addText(stepTag, { x: 10.85 - cw, y: 0.62, w: cw, h: 0.26, fontSize: 12, fontFace: F.mono, color: C.accent, bold: true, align: 'center', valign: 'middle', margin: 0 });
  }
}

function footer(s) {
  pageNo += 1;
  s.addText('FISCOChain · 联盟链实训平台 · 使用手册 v3.0', { x: M, y: 7.12, w: 6, h: 0.26, fontSize: 12, fontFace: F.mono, color: C.dimmer, margin: 0 });
  s.addText(`${String(pageNo).padStart(2, '0')} / ${TOTAL}`, { x: 11.9, y: 7.12, w: 0.93, h: 0.26, fontSize: 12, fontFace: F.mono, color: C.dimmer, align: 'right', margin: 0 });
}

function chip(s, x, y, text, color = C.primary, opts = {}) {
  const w = txtW(text, 12) + 0.3;
  s.addShape('roundRect', { x, y, w, h: 0.32, fill: { color, transparency: opts.solid ? 0 : 85 }, line: { color, width: 0.5, transparency: opts.solid ? 0 : 55 }, rectRadius: 0.05 });
  s.addText(text, { x, y, w, h: 0.32, fontSize: 12, fontFace: F.mono, color: opts.solid ? C.bg : color, bold: true, align: 'center', valign: 'middle', margin: 0 });
  return w;
}

function panel(s, x, y, w, h, opts = {}) {
  s.addShape('roundRect', { x, y, w, h, fill: { color: opts.fill || C.panel }, line: { color: opts.border || C.border, width: opts.bw || 0.75 }, rectRadius: 0.07, shadow: opts.shadow ? shadow() : undefined });
}

/** 浏览器窗口式截图卡片 */
function browserFrame(s, x, y, w, imgH, img, opts = {}) {
  const barH = 0.32;
  s.addShape('roundRect', { x, y, w, h: imgH + barH, fill: { color: C.bg2 }, line: { color: C.border2, width: 1 }, rectRadius: 0.05, shadow: shadow() });
  s.addShape('rect', { x: x + 0.02, y: y, w: w - 0.04, h: barH, fill: { color: C.panel2 }, line: { width: 0 } });
  s.addShape('ellipse', { x: x + 0.12, y: y + 0.125, w: 0.07, h: 0.07, fill: { color: C.error }, line: { width: 0 } });
  s.addShape('ellipse', { x: x + 0.26, y: y + 0.125, w: 0.07, h: 0.07, fill: { color: C.warn }, line: { width: 0 } });
  s.addShape('ellipse', { x: x + 0.4, y: y + 0.125, w: 0.07, h: 0.07, fill: { color: C.success }, line: { width: 0 } });
  s.addText(opts.url || 'https://chain.tianze.edu', { x: x + 0.56, y: y, w: w - 1.6, h: barH, fontSize: 12, fontFace: F.mono, color: C.dimmer, valign: 'middle', margin: 0 });
  if (opts.live !== false) {
    const tw = txtW('LIVE', 12) + 0.24;
    s.addShape('roundRect', { x: x + w - tw - 0.12, y: y + 0.05, w: tw, h: 0.22, fill: { color: C.success, transparency: 82 }, line: { color: C.success, width: 0.5, transparency: 50 }, rectRadius: 0.04 });
    s.addText('LIVE', { x: x + w - tw - 0.12, y: y + 0.05, w: tw, h: 0.22, fontSize: 12, fontFace: F.mono, color: C.success, bold: true, align: 'center', valign: 'middle', margin: 0 });
  }
  s.addShape('rect', { x, y: y + barH, w, h: imgH, fill: { color: C.bg }, line: { width: 0 } });
  s.addImage({ path: IMG(img), x, y: y + barH, w, h: imgH, sizing: { type: 'cover', w, h: imgH } });
}

/** 终端代码块 */
function codeBlock(s, x, y, w, h, lines, title = 'student@fisco-cloud:~') {
  s.addShape('roundRect', { x, y, w, h, fill: { color: C.bg2 }, line: { color: C.border, width: 0.75 }, rectRadius: 0.05, shadow: shadow() });
  s.addShape('rect', { x: x + 0.02, y: y, w: w - 0.04, h: 0.3, fill: { color: C.panel2 }, line: { width: 0 } });
  [['error', 0.12], ['warn', 0.26], ['success', 0.4]].forEach(([c, dx]) =>
    s.addShape('ellipse', { x: x + dx, y: y + 0.115, w: 0.07, h: 0.07, fill: { color: C[c] }, line: { width: 0 } }));
  s.addText(title, { x: x + 0.56, y, w: w - 0.7, h: 0.3, fontSize: 12, fontFace: F.mono, color: C.dimmer, valign: 'middle', margin: 0 });
  lines.forEach((line, i) => {
    const color = line.startsWith('$') ? C.primary : line.startsWith('#') ? C.dimmer : C.text;
    s.addText(line, { x: x + 0.2, y: y + 0.36 + i * 0.26, w: w - 0.35, h: 0.26, fontSize: 12, fontFace: F.mono, color, valign: 'middle', margin: 0 });
  });
}

/** 图标行：方块序号 + 加粗导语 + 说明 */
function rowItem(s, x, y, w, num, lead, desc, opts = {}) {
  const box = 0.34;
  s.addShape('roundRect', { x, y: y + 0.03, w: box, h: box, fill: { color: opts.mark || C.panel2 }, line: { color: opts.markBorder || C.border2, width: 0.75 }, rectRadius: 0.06 });
  s.addText(num, { x, y: y + 0.03, w: box, h: box, fontSize: 13, fontFace: F.mono, color: opts.numColor || C.primary, bold: true, align: 'center', valign: 'middle', margin: 0 });
  s.addText(lead, { x: x + 0.5, y, w: w - 0.5, h: 0.3, fontSize: 15, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  s.addText(desc, { x: x + 0.5, y: y + 0.31, w: w - 0.5, h: 0.52, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0 });
}

function arrowH(s, x, y, w = 0.32) {
  s.addShape('rect', { x, y: y + 0.09, w: w - 0.09, h: 0.025, fill: { color: C.primary, transparency: 40 }, line: { width: 0 } });
  s.addShape('rightTriangle', { x: x + w - 0.1, y, w: 0.11, h: 0.2, fill: { color: C.primary, transparency: 40 }, line: { width: 0 } });
}

function logo(s, x, y, size = 0.52) {
  s.addShape('hexagon', { x, y, w: size, h: size * 0.9, fill: { type: 'none' }, line: { color: C.primary, width: 1.5 } });
  s.addShape('hexagon', { x: x + size * 0.22, y: y + size * 0.2, w: size * 0.56, h: size * 0.5, fill: { type: 'none' }, line: { color: C.primary2, width: 1 } });
  s.addShape('ellipse', { x: x + size * 0.44, y: y + size * 0.39, w: 0.12, h: 0.12, fill: { color: C.accent }, line: { width: 0 } });
}

// ============================================================================
// S1 封面
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addImage({ path: IMG('s-login.jpg'), x: 0, y: 0, w: W, h: H, flipH: true }); // 星球视觉翻到右侧
  s.addImage({ path: IMG('grad-cover.png'), x: 0, y: 0, w: W, h: H });           // 左侧渐变遮罩
  logo(s, M, 0.55, 0.5);
  s.addText('FISCOChain · 联盟链实训平台', { x: 1.15, y: 0.55, w: 5, h: 0.5, fontSize: 13, fontFace: F.mono, color: C.primary, valign: 'middle', margin: 0 });
  s.addText('USER MANUAL · 使用手册', { x: M, y: 2.18, w: 6, h: 0.32, fontSize: 14, fontFace: F.mono, color: C.primary, bold: true, charSpacing: 4, margin: 0 });
  s.addText('FISCO 联盟链实训平台', { x: M, y: 2.58, w: 8.6, h: 0.95, fontSize: 46, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  s.addText('学生 × 教师 · 双角色实操指南', { x: M, y: 3.66, w: 7, h: 0.45, fontSize: 20, fontFace: F.sans, color: C.dim, margin: 0 });
  s.addText('从一条真实的绿色低碳联盟链出发：云桌面搭链 → 合约开发 → 联盟运营 → 链上验证 → 报告交付', {
    x: M, y: 4.28, w: 6.7, h: 0.6, fontSize: 14, fontFace: F.sans, color: C.dimmer, margin: 0,
  });
  let cx = M;
  ['v3.0', 'FISCO-BCOS', '天择教育', '2026'].forEach((t) => { cx += chip(s, cx, 5.25, t, C.primary) + 0.18; });
  s.addText('EVM 真实链运行中 · PBFT 4 节点 · 6 联盟组织', { x: M, y: 6.72, w: 7, h: 0.28, fontSize: 12, fontFace: F.mono, color: C.dimmer, margin: 0 });
})();

// ============================================================================
// S2 平台全景
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 平台认知', '平台全景：六大模块，一条主线', '/dashboard');
  const stats = [
    ['10', '搭链步骤 · 终端实操'],
    ['48', '实战命令 · 边敲边学'],
    ['6', '联盟角色 · 轮值运营'],
    ['3', '链上模式 · EVM/FISCO/沙盒'],
  ];
  stats.forEach(([n, label], i) => {
    const x = M + i * 3.17;
    s.addText(n, { x, y: 1.5, w: 2.9, h: 0.85, fontSize: 46, fontFace: F.mono, color: i === 2 ? C.accent : C.primary, bold: true, margin: 0 });
    s.addText(label, { x, y: 2.38, w: 2.9, h: 0.28, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0 });
    if (i < 3) s.addShape('line', { x: x + 2.98, y: 1.62, w: 0, h: 0.95, line: { color: C.border, width: 0.75 } });
  });
  const mods = [
    ['云桌面 · 搭链教程', '/cloud', '浏览器内 Linux 终端，10 步起链'],
    ['合约 IDE', '/ide', 'Monaco 编辑 · solc 真实编译'],
    ['接口调试', '/interfaces', '按 ABI 生成表单，填参即调用'],
    ['绿色低碳联盟', '/eco', '6 角色能量发放与资产兑换'],
    ['能量钱包', '/wallet', '余额 · 转账 · 兑换绿色资产'],
    ['区块链浏览器', '/explorer', '块高 · 交易 · 回执全程溯源'],
  ];
  mods.forEach(([t, r, d], i) => {
    const x = M + (i % 3) * 4.2, y = 3.0 + Math.floor(i / 3) * 1.62;
    panel(s, x, y, 3.96, 1.42, { shadow: true });
    s.addShape('hexagon', { x: x + 0.22, y: y + 0.22, w: 0.24, h: 0.21, fill: { type: 'none' }, line: { color: C.primary, width: 1.25 } });
    s.addText(t, { x: x + 0.56, y: y + 0.14, w: 3.2, h: 0.32, fontSize: 15, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
    s.addText(r, { x: x + 0.56, y: y + 0.47, w: 3.2, h: 0.24, fontSize: 12, fontFace: F.mono, color: C.primary, margin: 0 });
    s.addText(d, { x: x + 0.22, y: y + 0.86, w: 3.55, h: 0.42, fontSize: 12.5, fontFace: F.sans, color: C.dim, margin: 0 });
  });
  s.addShape('roundRect', { x: M, y: 6.38, w: W - 2 * M, h: 0.56, fill: { color: C.primary, transparency: 92 }, line: { color: C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.07 });
  s.addText('真实编译 · 真实上链 · 真实验证 —— 不是模拟器，是一条真的能跑的联盟链', {
    x: M, y: 6.38, w: W - 2 * M, h: 0.56, fontSize: 15, fontFace: F.sans, color: C.primary, bold: true, align: 'center', valign: 'middle', margin: 0,
  });
  footer(s);
})();

// ============================================================================
// S3 快速上手 · 登录
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 快速上手', '30 秒登录，直达实训台', '/login');
  const steps = [
    ['01', '打开平台地址', '浏览器访问实训平台网址，建议使用 Chrome / Edge'],
    ['02', '输入账号密码', '学号 / 工号登录，密码全程 RSA 加密传输'],
    ['03', '自动发放钱包', '登录即分配 stu: 专属链上钱包，直达实训总览'],
  ];
  steps.forEach(([n, t, d], i) => rowItem(s, M, 1.62 + i * 1.06, 7.4, n, t, d));
  panel(s, M, 4.95, 7.4, 1.06, { fill: C.panel });
  chip(s, M + 0.25, 5.17, 'SSO', C.info, { solid: true });
  s.addText('校园统一身份认证：URL 携带 ?token= 参数即可静默登录，首访无感直达；登录态 JWT 24 小时有效。', {
    x: M + 1.05, y: 5.08, w: 6.1, h: 0.8, fontSize: 13, fontFace: F.sans, color: C.dim, valign: 'middle', margin: 0,
  });
  s.addText('POST /api/auth/login → 200 OK · role = student | teacher', {
    x: M, y: 6.35, w: 7.4, h: 0.28, fontSize: 12, fontFace: F.mono, color: C.primary2, margin: 0,
  });
  browserFrame(s, 8.75, 1.55, 3.55, 4.2, 's-login-form.jpg', { url: 'login · 天择教育', live: false });
  s.addText('登录页：账号 + 密码，一键进入链上世界', { x: 8.75, y: 6.2, w: 3.55, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  footer(s);
})();

// ============================================================================
// S4 学习路径（四阶段地图）
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 学习路径', '四阶段 · 十节点，跟着地图走', '/dashboard');
  const stages = [
    { n: '01', t: '链底层搭建', tag: ['必修', C.warn], items: [['总览 · 联盟链', '/dashboard'], ['云桌面 · 搭链教程', '/cloud']] },
    { n: '02', t: '业务合约开发', items: [['合约 IDE', '/ide'], ['合约管理', '/contracts'], ['接口调试', '/interfaces']] },
    { n: '03', t: '联盟治理与运营', tag: ['核心', C.accent], items: [['绿色低碳联盟链', '/eco'], ['能量钱包', '/wallet'], ['绿色资产市场', '/nft']] },
    { n: '04', t: '链上验证与交付', tag: ['交付', C.info], items: [['调用监听器', '/monitor'], ['区块链浏览器', '/explorer'], ['生成实训报告', '/report']] },
  ];
  stages.forEach((st, i) => {
    const x = M + i * 3.22, y = 1.62, w = 2.92, h = 3.9;
    panel(s, x, y, w, h, { shadow: true });
    s.addText(st.n, { x: x + 0.2, y: y + 0.1, w: 1.2, h: 0.7, fontSize: 38, fontFace: F.mono, color: C.primary, bold: true, margin: 0 });
    if (st.tag) chip(s, x + w - txtW(st.tag[0], 12) - 0.42, y + 0.26, st.tag[0], st.tag[1]);
    s.addText(st.t, { x: x + 0.2, y: y + 0.88, w: w - 0.4, h: 0.34, fontSize: 16, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
    st.items.forEach(([name, r], j) => {
      const iy = y + 1.38 + j * 0.78;
      s.addShape('rect', { x: x + 0.2, y: iy + 0.055, w: 0.09, h: 0.09, fill: { color: C.primary2 }, line: { width: 0 } });
      s.addText(name, { x: x + 0.42, y: iy - 0.05, w: w - 0.6, h: 0.28, fontSize: 13.5, fontFace: F.sans, color: C.text, margin: 0 });
      s.addText(r, { x: x + 0.42, y: iy + 0.22, w: w - 0.6, h: 0.24, fontSize: 12, fontFace: F.mono, color: C.primary2, margin: 0 });
    });
    if (i < 3) arrowH(s, x + w + 0.045, y + 1.75, 0.31);
  });
  s.addShape('roundRect', { x: M, y: 5.85, w: W - 2 * M, h: 0.72, fill: { color: C.panel }, line: { color: C.border, width: 0.75 }, rectRadius: 0.07 });
  s.addText([
    { text: '侧边栏已按阶段分组：', options: { bold: true, color: C.text } },
    { text: '跟着菜单走，就是推荐学习顺序 —— 每完成一步，进度自动保存，实训报告自动累计。', options: { color: C.dim } },
  ], { x: M + 0.3, y: 5.85, w: W - 2 * M - 0.6, h: 0.72, fontSize: 14, fontFace: F.sans, valign: 'middle', margin: 0 });
  footer(s);
})();

// ============================================================================
// S5 STEP01 云桌面搭链
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '云桌面：10 步搭起联盟链', '/cloud', 'STEP 01 / 06');
  s.addText('浏览器里的 Linux 终端 —— 跟着 10 步教程，从零搭起一条 4 节点 PBFT 联盟链。', {
    x: M, y: 1.58, w: 5.9, h: 0.62, fontSize: 15, fontFace: F.sans, color: C.dim, margin: 0,
  });
  const rows = [
    ['A', '组织 × 节点 × 角色', '4 共识节点承载 6 联盟组织，矩阵面板一览全局'],
    ['B', '命令 + 排错提示', '每步附「预期输出 + 排错提示」，对照执行不迷路'],
    ['C', '进度自动保存', '完成 10/10，自动创建「区块链实训」成绩草稿'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, M, 2.4 + i * 0.92, 5.9, n, t, d));
  codeBlock(s, M, 5.28, 5.9, 1.62, [
    '$ bash build_chain.sh -l 127.0.0.1:4   # 生成 4 节点链',
    '$ bash nodes/127.0.0.1/start_all.sh    # 启动全部节点',
    '# PBFT 共识建立，块高持续增长 …',
  ]);
  browserFrame(s, 6.85, 1.55, 5.98, 3.36, 's-cloud.jpg', { url: '/cloud · 云桌面 · 搭链教程' });
  s.addText('左侧：10 步教程清单与组织矩阵；右侧：Ubuntu 云桌面终端', { x: 6.85, y: 5.3, w: 5.98, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  footer(s);
})();

// ============================================================================
// S6 STEP02 合约 IDE
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '合约 IDE：编写 · 编译 · 部署', '/ide', 'STEP 02 / 06');
  browserFrame(s, M, 1.55, 6.3, 3.54, 's-ide.jpg', { url: '/ide · 合约 IDE · ERC1155.sol' });
  s.addText('Monaco 编辑器 + 编译 / 审计 / 部署面板', { x: M, y: 5.5, w: 6.3, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  const rows = [
    ['A', '多文件合约工程', '内置 ERC20 / 721 / 1155 与业务合约模板'],
    ['B', 'solc 真实编译', '报错定位到行，秒级反馈，不离开浏览器'],
    ['C', '一键部署上链', 'tx_hash 回执实时入链，部署结果立等可见'],
    ['D', '静态安全审计', '重入 / 访问控制 / 事件 / Gas 综合打分'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, 7.25, 1.6 + i * 0.98, 5.58, n, t, d));
  let cx = 7.25;
  ['保存', '编译', '安全审计', '部署'].forEach((t, i) => { cx += chip(s, cx, 5.72, t, [C.info, C.primary, C.warn, C.accent][i], { solid: i === 1 }) + 0.16; });
  footer(s);
})();

// ============================================================================
// S7 STEP03 合约管理 & 接口调试（双截图）
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '合约管理 & 接口调试', '/contracts', 'STEP 03 / 06');
  const cards = [
    ['s-contracts.jpg', '合约管理', '/contracts', '部署实例统一管理，地址与调用记录可溯'],
    ['s-interfaces.jpg', '接口调试', '/interfaces', '按 ABI 自动生成表单，填参数即调用'],
  ];
  cards.forEach(([img, t, r, d], i) => {
    const x = M + i * 6.38;
    s.addText([
      { text: t + '  ', options: { fontSize: 16, bold: true, color: C.text } },
      { text: r, options: { fontSize: 13, fontFace: F.mono, color: C.primary } },
    ], { x, y: 1.58, w: 5.95, h: 0.32, fontFace: F.sans, margin: 0 });
    s.addText(d, { x, y: 1.92, w: 5.95, h: 0.28, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0 });
    browserFrame(s, x, 2.32, 5.95, 2.62, img, { url: r, live: i === 0 });
  });
  s.addShape('roundRect', { x: M, y: 5.5, w: W - 2 * M, h: 0.72, fill: { color: C.panel }, line: { color: C.border, width: 0.75 }, rectRadius: 0.07 });
  s.addText([
    { text: 'TIP  ', options: { fontFace: F.mono, bold: true, color: C.warn } },
    { text: '合约升级或 ABI 变更后，接口表单一键重新生成 —— 不写前端代码，也能完成链上调用。', options: { color: C.text } },
  ], { x: M + 0.3, y: 5.5, w: W - 2 * M - 0.6, h: 0.72, fontSize: 14, fontFace: F.sans, valign: 'middle', margin: 0 });
  footer(s);
})();

// ============================================================================
// S8 STEP04 绿色低碳联盟
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '绿色低碳联盟：让能量流转起来', '/eco', 'STEP 04 / 06');
  // 业务闭环图
  const loop = [['低碳行为', '地铁 / 骑行 / 植树'], ['发放绿色能量', '凭证上链 mint'], ['兑换绿色资产', '证书 / 勋章 / 骑行券']];
  loop.forEach(([t, d], i) => {
    const x = M + i * 2.12;
    panel(s, x, 1.66, 1.86, 1.08, { fill: C.panel, border: C.border2 });
    s.addText(t, { x, y: 1.8, w: 1.86, h: 0.3, fontSize: 14, fontFace: F.sans, color: C.primary, bold: true, align: 'center', margin: 0 });
    s.addText(d, { x: x + 0.08, y: 2.12, w: 1.7, h: 0.5, fontSize: 12, fontFace: F.sans, color: C.dim, align: 'center', margin: 0 });
    if (i < 2) arrowH(s, x + 1.88, 2.1, 0.22);
  });
  s.addText('6 大联盟角色 · 轮值切换', { x: M, y: 3.05, w: 6.1, h: 0.3, fontSize: 15, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  const roles = ['管理员', '地铁集团', '公交集团', '共享单车', '外卖平台', '回收公司'];
  roles.forEach((r, i) => { chip(s, M + (i % 3) * 2.12, 3.42 + Math.floor(i / 3) * 0.44, r, i === 0 ? C.info : C.primary2); });
  s.addText('切换角色后填写业务凭证（如地铁出行 trip_no + 里程），阈值校验通过即 mint 能量；', {
    x: M, y: 4.55, w: 6.1, h: 0.52, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0,
  });
  s.addText('同一业务单号仅发放一次 —— 服务端幂等校验，防重复领能量。', {
    x: M, y: 5.05, w: 6.1, h: 0.3, fontSize: 13, fontFace: F.sans, color: C.warn, bold: true, margin: 0,
  });
  s.addText('GreenEnergy(ERC20) · PlantCertificate(ERC721) · EcoBadge(ERC1155)', {
    x: M, y: 5.55, w: 6.1, h: 0.28, fontSize: 12, fontFace: F.mono, color: C.primary2, margin: 0,
  });
  browserFrame(s, 6.85, 1.9, 5.98, 2.35, 's-eco.jpg', { url: '/eco · 绿色低碳联盟链' });
  s.addText('生态运营台：联盟组织 · 业务合约 · 6 角色操作面板', { x: 6.85, y: 4.35, w: 5.98, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  footer(s);
})();

// ============================================================================
// S9 STEP05 能量钱包 & NFT 市场（双截图）
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '能量钱包 & 绿色资产市场', '/wallet', 'STEP 05 / 06');
  const cards = [
    ['s-wallet.jpg', '能量钱包', '/wallet', 'ERC20 能量余额 · 转账记录一目了然'],
    ['s-nft.jpg', '绿色资产市场', '/nft', 'NFT 铸造 · 挂牌 · 购买全流程'],
  ];
  cards.forEach(([img, t, r, d], i) => {
    const x = M + i * 6.38;
    browserFrame(s, x, 1.62, 5.95, 2.62, img, { url: r });
    s.addText(t, { x, y: 4.42, w: 5.95, h: 0.32, fontSize: 16, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
    s.addText([
      { text: r + '   ', options: { fontSize: 12.5, fontFace: F.mono, color: C.primary } },
      { text: d, options: { fontSize: 12.5, color: C.dim } },
    ], { x, y: 4.76, w: 5.95, h: 0.28, margin: 0 });
  });
  s.addShape('roundRect', { x: M, y: 5.15, w: W - 2 * M, h: 1.06, fill: { color: C.panel }, line: { color: C.border, width: 0.75 }, rectRadius: 0.07 });
  s.addText([
    { text: '兑换什么？', options: { bold: true, color: C.primary } },
    { text: '  植树证书 · 生态勋章 · 骑行券 —— 用积累的能量兑换（ERC721 / ERC1155）。', options: { color: C.text, breakLine: true } },
    { text: '钥匙在哪？', options: { bold: true, color: C.accent } },
    { text: '  私钥 keystore v3 加密托管，一人一钱包，登录即用。', options: { color: C.text } },
  ], { x: M + 0.3, y: 5.15, w: W - 2 * M - 0.6, h: 1.06, fontSize: 14, fontFace: F.sans, valign: 'middle', paraSpaceAfter: 6, margin: 0 });
  footer(s);
})();

// ============================================================================
// S10 STEP06 链上验证
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 实训六步', '链上验证：让成果自证清白', '/explorer', 'STEP 06 / 06');
  const rows = [
    ['A', '调用监听器  /monitor', '合约事件实时推送，每一次调用全程可见'],
    ['B', '区块链浏览器  /explorer', '按块高 / 交易哈希逐笔溯源，回执一目了然'],
    ['C', '证据链入报告', '关键 tx_hash 自动写入实训报告，自证上链'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, M, 1.66 + i * 1.0, 6.1, n, t, d));
  codeBlock(s, M, 4.85, 6.1, 1.62, [
    'tx  0x9f3e…c21a   OK  PBFT 3/3 节点确认',
    'block #19840077 · gas 21000',
    '# 交易成功率 97.3%（综合报告实测）',
  ], 'explorer · receipt');
  browserFrame(s, 6.85, 1.55, 5.98, 3.36, 's-explorer.jpg', { url: '/explorer · 区块链浏览器' });
  s.addText('块高 / 交易 / 合约，链上数据逐笔可查', { x: 6.85, y: 5.3, w: 5.98, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  footer(s);
})();

// ============================================================================
// S11 实训报告与成绩（学生交付）
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 学生篇 · 交付与激励', '实训报告：一键生成交作业', '/report');
  // 评分构成
  const parts = [['55', '基础模块', C.primary], ['40', '高级实战', C.primary2], ['5', '综合拓展', C.info]];
  parts.forEach(([n, t, c], i) => {
    const x = M + i * 1.62;
    panel(s, x, 1.66, 1.42, 1.28, { fill: C.panel });
    s.addText(n, { x, y: 1.74, w: 1.42, h: 0.62, fontSize: 34, fontFace: F.mono, color: c, bold: true, align: 'center', margin: 0 });
    s.addText(t, { x, y: 2.42, w: 1.42, h: 0.28, fontSize: 12.5, fontFace: F.sans, color: C.dim, align: 'center', margin: 0 });
    s.addText('+', { x: x + 1.37, y: 2.0, w: 0.3, h: 0.44, fontSize: 20, fontFace: F.mono, color: C.dimmer, align: 'center', margin: 0 });
  });
  panel(s, M + 4.86, 1.66, 1.42, 1.28, { fill: C.primary, border: C.primary, shadow: true });
  s.addText('100', { x: M + 4.86, y: 1.74, w: 1.42, h: 0.62, fontSize: 34, fontFace: F.mono, color: C.bg, bold: true, align: 'center', margin: 0 });
  s.addText('自动评分 V2', { x: M + 4.86, y: 2.42, w: 1.42, h: 0.28, fontSize: 12.5, fontFace: F.sans, color: C.bg, bold: true, align: 'center', margin: 0 });
  const rows = [
    ['A', '服务端核算，防代刷', '按真实链上行为打分：行为埋点 + 搭链节奏'],
    ['B', 'Markdown / JSON 一键导出', '报告即作业，直接提交给老师'],
    ['C', '成就墙激励', '15 枚成就 + 3 项挑战任务，完成即解锁积分'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, M, 3.3 + i * 0.98, 6.28, n, t, d));
  browserFrame(s, 7.15, 1.55, 5.68, 3.2, 's-report.jpg', { url: '/report · 实训综合报告' });
  s.addText('实训综合报告：评分 82 / 100 · 良好（示例数据）', { x: 7.15, y: 5.15, w: 5.68, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  s.addText('我的成绩实时可查：/my-grades', { x: M, y: 6.35, w: 6, h: 0.28, fontSize: 12, fontFace: F.mono, color: C.primary2, margin: 0 });
  footer(s);
})();

// ============================================================================
// S12 教师篇 · 双轨成绩制
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 教师篇 · 教学管理', '双轨成绩制：实训分 × 教师评分', '/grades');
  // 流程条
  const flow = ['链上活动', '实训成绩', '教师评分', '综合成绩'];
  flow.forEach((t, i) => {
    const x = M + i * 1.62;
    panel(s, x, 1.62, 1.4, 0.52, { fill: i === 3 ? C.primary : C.panel, border: i === 3 ? C.primary : C.border2 });
    s.addText(t, { x, y: 1.62, w: 1.4, h: 0.52, fontSize: 13.5, fontFace: F.sans, color: i === 3 ? C.bg : C.text, bold: true, align: 'center', valign: 'middle', margin: 0 });
    if (i < 3) arrowH(s, x + 1.42, 1.78, 0.18);
  });
  // 实训分构成图
  s.addText('实训分 · 4 维自动加权', { x: M, y: 2.42, w: 6, h: 0.3, fontSize: 15, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  s.addChart(pres.charts.BAR, [{
    name: '权重',
    labels: ['联盟治理 25%', '链上验证 25%', '合约开发 30%', '链搭建 20%'],
    values: [25, 25, 30, 20],
  }], {
    x: M, y: 2.78, w: 6.1, h: 2.5, barDir: 'bar',
    chartColors: ['0E7A6B', '13C2A6', '00E6C3', 'F5379B'], varyColors: true,
    chartArea: { fill: { color: C.panel } }, plotArea: { fill: { color: C.panel } },
    catAxisLabelColor: C.dim, catAxisLabelFontSize: 12, catAxisLabelFontFace: F.sans, catAxisLineShow: false,
    valAxisHidden: true, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    showValue: true, dataLabelColor: C.text, dataLabelFontSize: 12, dataLabelFontFace: F.mono, dataLabelFormatCode: '0"%"',
    showLegend: false, barGapWidthPct: 60, valAxisMaxVal: 32,
  });
  panel(s, M, 5.5, 6.1, 0.66, { fill: C.bg2, border: C.border2 });
  s.addText('综合成绩 = 实训分 × 60% + 教师评分 × 40%', { x: M, y: 5.5, w: 6.1, h: 0.66, fontSize: 15, fontFace: F.mono, color: C.primary, bold: true, align: 'center', valign: 'middle', margin: 0 });
  browserFrame(s, 7.15, 1.55, 5.68, 3.2, 's-tdash.jpg', { url: '/dashboard · 教师视角' });
  s.addText('教师视角：班级实训进度看板 + 实训链状态', { x: 7.15, y: 5.15, w: 5.68, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  s.addText('教师登录自动开启「教学管理」菜单；成绩由服务端按链上活动核算，全程防作弊。', {
    x: M, y: 6.42, w: 11, h: 0.28, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0,
  });
  footer(s);
})();

// ============================================================================
// S13 教师篇 · 学生成绩管理
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 教师篇 · 教学管理', '学生成绩管理：录入 · 刷新 · 统计', '/grades');
  const rows = [
    ['A', '新增成绩', '学号 + 课程唯一，必填学生钱包地址'],
    ['B', '刷新实训成绩', '按链上活动一键批量重算，即时生效'],
    ['C', '成绩列表三列对照', '实训分 · 教师评分 · 综合成绩，一屏看清'],
    ['D', '班级搭链看板', '人均完成 x/10 步，卡点步骤一目了然'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, M, 1.62 + i * 1.02, 6.1, n, t, d));
  let cx = M;
  ['新增成绩', '刷新实训成绩', '查询'].forEach((t, i) => { cx += chip(s, cx, 5.85, t, [C.primary, C.info, C.warn][i]) + 0.16; });
  browserFrame(s, 6.85, 1.55, 5.98, 3.36, 's-tgrades.jpg', { url: '/grades · 学生成绩管理' });
  s.addText('课程成绩统计 + 搭链进度班级看板 + 成绩列表', { x: 6.85, y: 5.3, w: 5.98, h: 0.28, fontSize: 12, fontFace: F.sans, color: C.dimmer, align: 'center', margin: 0 });
  s.addText('综合成绩合成闭环：平台自动采集链上活动 → 计算实训成绩 → 教师录入评价 → 合成综合成绩。', {
    x: M, y: 6.42, w: 11.5, h: 0.28, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0,
  });
  footer(s);
})();

// ============================================================================
// S14 教师篇 · 督导与沙盘演练
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 教师篇 · 教学督导', '督导与沙盘：异常早发现', '/sandbox');
  const rows = [
    ['A', '报告聚合抽查', '全班实训报告一键汇总核对，交付质量尽在掌握'],
    ['B', '生态日志对账', '异常上链操作自动留痕，随时可查可追溯'],
    ['C', '沙盘故障演练', '注入故障无风险演练，练出链上应急能力'],
  ];
  rows.forEach(([n, t, d], i) => rowItem(s, M, 1.66 + i * 1.02, 6.1, n, t, d));
  s.addText('四类可注入故障', { x: M, y: 4.85, w: 6, h: 0.3, fontSize: 15, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  const faults = [['node_down', '节点宕机'], ['consensus_stall', '共识停滞'], ['replay_attack', '重放攻击'], ['gas_spike', 'Gas 飙升']];
  faults.forEach(([en, cn], i) => {
    const x = M + (i % 2) * 3.05, y = 5.25 + Math.floor(i / 2) * 0.5;
    chip(s, x, y, en, C.error);
    s.addText(cn, { x: x + txtW(en, 12) + 0.42, y, w: 1.3, h: 0.32, fontSize: 13, fontFace: F.sans, color: C.dim, valign: 'middle', margin: 0 });
  });
  // 沙盘控制台（示意）
  const px = 7.0, py = 1.62, pw = 5.83, ph = 4.35;
  codeBlock(s, px, py, pw, 2.5, [
    '$ sandbox inject --fault node_down',
    '> 故障已注入 · 负载生成器 5 TPS · 监控中…',
    '> node2 心跳超时 → 告警推送（SSE 实时）',
    '$ sandbox recover --fault node_down',
    '> KPI  MTTD 2.1s · MTTR 18.4s  记分板已更新',
  ], 'sandbox@fisco-lab (示意)');
  panel(s, px, py + 2.72, pw, 1.6, { fill: C.panel });
  s.addText([
    { text: '怎么用？', options: { bold: true, color: C.primary, breakLine: true } },
    { text: '课堂演示典型链上事故：学生观察告警 → 定位 → 恢复；', options: { color: C.dim, breakLine: true } },
    { text: 'MTTD / MTTR 自动计算，演练成绩进入记分板。', options: { color: C.dim, breakLine: true } },
    { text: '＊示意界面，以平台实际功能为准', options: { color: C.dimmer, fontSize: 12 } },
  ], { x: px + 0.28, y: py + 2.86, w: pw - 0.56, h: 1.35, fontSize: 13, fontFace: F.sans, paraSpaceAfter: 4, margin: 0 });
  footer(s);
})();

// ============================================================================
// S15 FAQ
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  deco(s);
  header(s, '// 附录', '常见问题 FAQ', '/help');
  const faqs = [
    ['Q1', '登录失败怎么办？', '核对学号 / 工号与密码；也支持 URL 携带 ?token= 静默登录；登录态 24 小时有效。'],
    ['Q2', '云桌面命令报错？', '每步附「预期输出 + 排错提示」，对照即可定位；进度已保存，可从当前步重试。'],
    ['Q3', '绿色能量没到账？', '同一业务单号只能发放一次；到「调用监听器」查看 mint 事件，确认是否上链。'],
    ['Q4', '合约部署失败？', '先看「编译」面板报错行号；安全审计存在高危项时，修复后再部署。'],
  ];
  faqs.forEach(([q, t, a], i) => {
    const x = M + (i % 2) * 6.42, y = 1.62 + Math.floor(i / 2) * 2.28;
    panel(s, x, y, 5.92, 2.02, { shadow: true });
    chip(s, x + 0.26, y + 0.26, q, i % 2 ? C.accent : C.primary, { solid: true });
    s.addText(t, { x: x + 0.9, y: y + 0.24, w: 4.7, h: 0.34, fontSize: 16, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
    s.addShape('line', { x: x + 0.26, y: y + 0.78, w: 5.4, h: 0, line: { color: C.border, width: 0.75 } });
    s.addText(a, { x: x + 0.26, y: y + 0.94, w: 5.4, h: 0.9, fontSize: 13.5, fontFace: F.sans, color: C.dim, margin: 0 });
  });
  s.addText([
    { text: '更多帮助：', options: { bold: true, color: C.text } },
    { text: '顶栏「? 快捷键」打开帮助中心 · 或联系授课教师', options: { color: C.dim } },
  ], { x: M, y: 6.35, w: 11, h: 0.3, fontSize: 14, fontFace: F.sans, margin: 0 });
  footer(s);
})();

// ============================================================================
// S16 封底
// ============================================================================
(() => {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addImage({ path: IMG('s-login.jpg'), x: 0, y: 0, w: W, h: H, flipH: true, transparency: 62 });
  s.addImage({ path: IMG('grad-cover.png'), x: 0, y: 0, w: W, h: H });
  logo(s, M, 1.7, 0.62);
  s.addText('GO BUILD YOUR CHAIN', { x: M, y: 2.62, w: 6, h: 0.32, fontSize: 14, fontFace: F.mono, color: C.primary, bold: true, charSpacing: 4, margin: 0 });
  s.addText('现在，去搭一条属于你的联盟链', { x: M, y: 3.0, w: 10.5, h: 0.85, fontSize: 40, fontFace: F.sans, color: C.text, bold: true, margin: 0 });
  s.addText('从云桌面的第一条命令，到链上的第一笔交易 —— 六步闭环，一步一个脚印。', {
    x: M, y: 3.95, w: 8.5, h: 0.4, fontSize: 16, fontFace: F.sans, color: C.dim, margin: 0,
  });
  let cx = M;
  ['/cloud', '/ide', '/contracts', '/eco', '/wallet', '/explorer', '/report'].forEach((t) => { cx += chip(s, cx, 4.75, t, C.primary2) + 0.14; });
  s.addShape('line', { x: M, y: 6.35, w: 5.5, h: 0, line: { color: C.border, width: 0.75 } });
  s.addText('FISCOChain · 联盟链实训平台 · 天择教育', { x: M, y: 6.5, w: 6, h: 0.3, fontSize: 13, fontFace: F.sans, color: C.dim, margin: 0 });
  s.addText('USER MANUAL v3.0 · 2026', { x: M, y: 6.82, w: 6, h: 0.28, fontSize: 12, fontFace: F.mono, color: C.dimmer, margin: 0 });
})();

// ============================================================================
pres.writeFile({ fileName: path.join(__dirname, 'output', '实训平台使用手册.pptx') })
  .then(() => console.log('OK ->', path.join(__dirname, 'output', '实训平台使用手册.pptx')))
  .catch((e) => { console.error(e); process.exit(1); });
