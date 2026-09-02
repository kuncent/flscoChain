/**
 * 学生 / 教师 使用手册 PPT 生成脚本
 * - 设计系统严格对齐平台深色 UI（与 generate-manual-ppt.js 同一套 Design Tokens）
 * - 嵌入平台真实页面截图，图文并茂；文案简洁，突出操作路径与业务闭环
 * - 输出：docs/output/学生使用手册.pptx 与 docs/output/教师使用手册.pptx
 */

const PptxGenJS = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

const SHOT_DIR = path.join(__dirname, 'assets', 'screenshots');
function shot(name) {
  const p = path.join(SHOT_DIR, name);
  if (!fs.existsSync(p)) throw new Error(`截图缺失: ${p}`);
  return p;
}

// ============================================================================
// 设计系统 - Design Tokens（对齐平台深色 UI）
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

// ============================================================================
// 基础组件
// ============================================================================
function drawBackground(slide) {
  slide.background = { color: C.bg };
  slide.addShape('rect', { x: 0, y: 0, w: '100%', h: 2.5, fill: { type: 'gradient', color: C.primary, transparency: 94, angle: 135 }, line: { width: 0 } });
  // 装饰椭圆完全收入画布内（避免越界被裁）
  slide.addShape('ellipse', { x: 7.3, y: 0, w: 2.7, h: 2.7, fill: { color: C.accent, transparency: 92 }, line: { width: 0 } });
}

/** 文本宽度估算：中文按全角（≈1.05 倍字号），ASCII 按半角，避免中文被低估导致溢出 */
function textWidth(text, fontSize) {
  let w = 0;
  for (const ch of text) w += ch.charCodeAt(0) > 255 ? 1.05 : 0.58;
  return (w * fontSize) / 72;
}

function makeHeader(brand) {
  return function drawHeader(slide, title, subtitle, page, total) {
    slide.addShape('rect', { x: 0, y: 0, w: '100%', h: 0.72, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
    slide.addShape('rect', { x: 0.5, y: 0.18, w: 0.05, h: 0.36, fill: { color: C.primary }, line: { width: 0 } });
    slide.addText(title, { x: 0.65, y: 0.12, w: 6.2, h: 0.3, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    if (subtitle) slide.addText(subtitle, { x: 0.65, y: 0.42, w: 6.2, h: 0.22, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
    const label = `${brand} · ${page}/${total}`;
    const bw = textWidth(label, S.xs) + 0.3;
    slide.addShape('roundRect', { x: 9.55 - bw, y: 0.22, w: bw, h: 0.28, fill: { color: C.primary, transparency: 88 }, line: { color: C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.05 });
    slide.addText(label, { x: 9.55 - bw, y: 0.22, w: bw, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: C.primary, bold: true, align: 'center', valign: 'middle' });
  };
}

function makeFooter(brand) {
  return function drawFooter(slide) {
    slide.addShape('rect', { x: 0, y: 7.18, w: '100%', h: 0.32, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
    slide.addText(`FISCO 联盟链实训平台 · ${brand} · 2026.08 · 天择教育`, { x: 0.5, y: 7.2, w: 6, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: C.textDimmer, valign: 'middle' });
  };
}

function drawCard(slide, x, y, w, h, opts = {}) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: opts.fill || C.panel }, line: { color: opts.border || C.border, width: opts.borderWidth || 0.75 }, rectRadius: 0.08 });
}

function drawCardTitle(slide, x, y, w, title, opts = {}) {
  slide.addShape('roundRect', { x, y: y + 0.02, w: 0.04, h: 0.2, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.02 });
  slide.addText(title, { x: x + 0.12, y, w: w - 0.2, h: 0.28, fontSize: S.md, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
  if (opts.tag) {
    const tagW = textWidth(opts.tag, S.xs) + 0.24;
    slide.addShape('roundRect', { x: x + w - tagW - 0.05, y: y + 0.03, w: tagW, h: 0.22, fill: { color: opts.tagColor || C.primary, transparency: 85 }, line: { color: opts.tagColor || C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.04 });
    slide.addText(opts.tag, { x: x + w - tagW - 0.05, y: y + 0.03, w: tagW, h: 0.22, fontSize: S.xs, fontFace: F.mono, color: opts.tagColor || C.primary, bold: true, align: 'center', valign: 'middle' });
  }
}

function drawTag(slide, x, y, text, color = C.primary) {
  const w = textWidth(text, S.xs) + 0.24;
  slide.addShape('roundRect', { x, y, w, h: 0.2, fill: { color, transparency: 85 }, line: { color, width: 0.5, transparency: 60 }, rectRadius: 0.03 });
  slide.addText(text, { x, y, w, h: 0.2, fontSize: S.xs, fontFace: F.mono, color, bold: true, align: 'center', valign: 'middle' });
  return w;
}

function drawArrowH(slide, x, y, w = 0.3) {
  // 无线条箭头：单个 chevron 形状，避免细长横线带来的碑裂感
  slide.addShape('chevron', { x: x + (w - 0.22) / 2, y: y - 0.02, w: 0.22, h: 0.22, fill: { color: C.primary, transparency: 45 }, line: { width: 0 } });
}

function drawStepCircle(slide, x, y, num, size = 0.4, color = C.primary) {
  slide.addShape('ellipse', { x, y, w: size, h: size, fill: { color }, line: { width: 0 } });
  slide.addText(String(num), { x, y, w: size, h: size, fontSize: size >= 0.35 ? S.base : S.sm, fontFace: F.mono, color: C.bg, bold: true, align: 'center', valign: 'middle', margin: 0, wrap: false });
}

/** 读取 PNG 原始像素尺寸（IHDR），用于 contain 等比适配 */
function pngSize(imgPath) {
  const b = fs.readFileSync(imgPath);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

/** 截图卡片：深色框 + 浏览器窗口顶栏 + 图片（contain 等比居中，不裁切不变形） */
function drawScreenshot(slide, x, y, w, h, imgPath, opts = {}) {
  drawCard(slide, x, y, w, h, { fill: C.bg2, border: opts.border || C.border2, borderWidth: 0.75 });
  const barH = 0.26;
  slide.addShape('rect', { x, y, w, h: barH, fill: { color: C.panel2 }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.1, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.error }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.22, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.warn }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.34, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.success }, line: { width: 0 } });
  slide.addText(opts.url || 'localhost:5173', { x: x + 0.5, y: y + 0.04, w: w - 1.4, h: barH - 0.08, fontSize: 7, fontFace: F.mono, color: C.textDimmer, valign: 'middle' });
  drawTag(slide, x + w - 0.62, y + 0.05, 'LIVE', C.success);
  const imgY = y + barH, imgH = h - barH;
  slide.addShape('rect', { x, y: imgY, w, h: imgH, fill: { color: C.bg }, line: { width: 0 } });
  // contain：按原图比例缩放到区域内居中，完整画面不裁切、不拉伸变形；
  // 留白区与区域底色同为 C.bg，视觉无割裂（替代旧 cover 硬裁左右）
  const dim = pngSize(imgPath);
  const scale = Math.min(w / dim.w, imgH / dim.h);
  const dw = dim.w * scale, dh = dim.h * scale;
  slide.addImage({ path: imgPath, x: x + (w - dw) / 2, y: imgY + (imgH - dh) / 2, w: dw, h: dh });
}

function drawBulletList(slide, x, y, w, items, gap = 0.55) {
  items.forEach((it, i) => {
    const yy = y + i * gap;
    slide.addShape('ellipse', { x: x + 0.02, y: yy + 0.06, w: 0.08, h: 0.08, fill: { color: it.c || C.primary }, line: { width: 0 } });
    slide.addText(it.t, { x: x + 0.2, y: yy, w: w - 0.2, h: 0.24, fontSize: S.base, fontFace: F.sans, color: it.c || C.primary, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: x + 0.2, y: yy + 0.24, w: w - 0.2, h: gap - 0.26, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

function drawCover(pptx, opts) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  const cx = 5, cy = 2.1;
  slide.addShape('hexagon', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fill: { color: opts.themeColor, transparency: 88 }, line: { color: opts.themeColor, width: 1.5 } });
  slide.addText('FISCO', { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: opts.themeColor, bold: true, align: 'center', valign: 'middle' });
  slide.addText('FISCO 联盟链实训平台', { x: 1, y: 3.0, w: 8, h: 0.45, fontSize: S.xl, fontFace: F.sans, color: C.textDim, align: 'center' });
  slide.addText(opts.title, { x: 1, y: 3.45, w: 8, h: 0.7, fontSize: S['4xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText(opts.subtitle, { x: 1, y: 4.25, w: 8, h: 0.4, fontSize: S.lg, fontFace: F.sans, color: opts.themeColor, align: 'center' });
  slide.addText('v1.0 · 2026年8月 · 天择教育', { x: 1, y: 4.85, w: 8, h: 0.3, fontSize: S.base, fontFace: F.sans, color: C.textDim, align: 'center' });
  // 封面标签按实测宽度围绕中线等距排布，避免重叠/偏移
  const tagWs = opts.tags.map(t => textWidth(t, S.xs) + 0.24);
  const gap = 0.35;
  const totalW = tagWs.reduce((a, b) => a + b, 0) + gap * (opts.tags.length - 1);
  let tx = 5 - totalW / 2;
  opts.tags.forEach((t, i) => {
    drawTag(slide, tx, 5.7, t, [C.primary, C.info, C.accent][i]);
    tx += tagWs[i] + gap;
  });
}

function drawTOC(slide, chapters, drawHeader, drawFooter, page, total) {
  drawBackground(slide);
  drawHeader(slide, '目录', 'Table of Contents', page, total);
  drawFooter(slide);
  chapters.forEach((ch, i) => {
    const y = 1.15 + i * (5.3 / chapters.length);
    slide.addText(ch.num, { x: 0.7, y: y + 0.1, w: 0.8, h: 0.6, fontSize: S['2xl'], fontFace: F.mono, color: ch.color, bold: true, align: 'center', margin: 0, wrap: false });
    slide.addText(ch.title, { x: 1.75, y: y + 0.08, w: 5.3, h: 0.32, fontSize: S.lg, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
    slide.addText(ch.desc, { x: 1.75, y: y + 0.42, w: 6.3, h: 0.25, fontSize: S.sm, fontFace: F.sans, color: C.textDim, valign: 'top' });
    drawTag(slide, 7.8, y + 0.15, ch.pages, ch.color);
  });
}

function drawEnd(pptx, opts, drawFooter) {
  const slide = pptx.addSlide();
  drawBackground(slide);
  slide.addShape('hexagon', { x: 4.4, y: 1.7, w: 1.2, h: 1.2, fill: { color: opts.themeColor, transparency: 88 }, line: { color: opts.themeColor, width: 1.5 } });
  slide.addText('FISCO', { x: 4.4, y: 1.7, w: 1.2, h: 1.2, fontSize: S.lg, fontFace: F.mono, color: opts.themeColor, bold: true, align: 'center', valign: 'middle' });
  slide.addText(opts.endTitle, { x: 1, y: 3.2, w: 8, h: 0.5, fontSize: S['2xl'], fontFace: F.sans, color: C.text, bold: true, align: 'center' });
  slide.addText(opts.endSubtitle, { x: 1, y: 3.75, w: 8, h: 0.4, fontSize: S.xl, fontFace: F.sans, color: opts.themeColor, align: 'center' });
  slide.addText(opts.endTips, { x: 1.5, y: 4.5, w: 7, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.textDim, align: 'center' });
  slide.addText('技术支持 · platform@fisco-chain.edu', { x: 1, y: 5.0, w: 8, h: 0.3, fontSize: S.md, fontFace: F.mono, color: opts.themeColor, align: 'center' });
  drawFooter(slide);
}

/** 全宽横图版式：16:9 截图区域比例接近原图（几乎无留白），要点改为底部三卡横排 */
function slideScreenshot(slide, drawHeader, drawFooter, page, total, title, subtitle, shotName, url, border, caption, cardTitle, cardTag, cardTagColor, bullets) {
  drawBackground(slide);
  drawHeader(slide, title, subtitle, page, total);
  drawFooter(slide);
  drawScreenshot(slide, 0.5, 1.0, 9.0, 4.85, shot(shotName), { url, border });
  slide.addText(caption, { x: 0.5, y: 5.9, w: 9.0, h: 0.26, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  const items = bullets.slice(0, 4);
  const gapW = 0.1;
  const cw = (9.0 - gapW * (items.length - 1)) / items.length;
  items.forEach((it, i) => {
    const x = 0.5 + i * (cw + gapW);
    drawCard(slide, x, 6.25, cw, 0.85, { border: it.c || C.primary, borderWidth: 0.5 });
    slide.addText(it.t, { x: x + 0.12, y: 6.33, w: cw - 0.24, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: it.c || C.primary, bold: true, valign: 'middle' });
    slide.addText(it.d, { x: x + 0.12, y: 6.57, w: cw - 0.24, h: 0.44, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

function drawFAQ(slide, drawHeader, drawFooter, page, total, faqs) {
  drawBackground(slide);
  drawHeader(slide, '常见问题', 'FAQ', page, total);
  drawFooter(slide);
  faqs.forEach((faq, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7, y = 1.0 + row * 1.75;
    drawCard(slide, x, y, 4.4, 1.55, { border: C.info, borderWidth: 0.5 });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.1, w: 0.25, h: 0.25, fill: { color: C.info }, line: { width: 0 }, rectRadius: 0.04 });
    slide.addText('Q', { x: x + 0.1, y: y + 0.1, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center', valign: 'middle', margin: 0, wrap: false });
    slide.addText(faq.q, { x: x + 0.45, y: y + 0.08, w: 3.85, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: C.info, bold: true, valign: 'middle' });
    slide.addShape('roundRect', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fill: { color: C.primary }, line: { width: 0 }, rectRadius: 0.04 });
    slide.addText('A', { x: x + 0.1, y: y + 0.62, w: 0.25, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.bg, bold: true, align: 'center', valign: 'middle', margin: 0, wrap: false });
    slide.addText(faq.a, { x: x + 0.45, y: y + 0.56, w: 3.85, h: 0.9, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
  });
}

// ============================================================================
// 学生使用手册（15 页 + 结束页，行动导向：先讲怎么做）
// ============================================================================
function buildStudentManual() {
  const pptx = new PptxGenJS();
  // 全部坐标按 10in x 7.5in 画布设计，自定义布局避免 LAYOUT_16x9（10x5.625）裁掉底部内容
  pptx.defineLayout({ name: 'MANUAL', width: 10, height: 7.5 });
  pptx.layout = 'MANUAL';
  pptx.author = 'FISCO 联盟链实训平台';
  pptx.company = '天择教育';
  pptx.title = '学生使用手册';
  const TOTAL = 15;
  const drawHeader = makeHeader('学生手册');
  const drawFooter = makeFooter('学生使用手册');

  // 1 封面
  drawCover(pptx, { title: '学生使用手册', subtitle: 'Student Manual · 从零到一完成区块链实训', themeColor: C.primary, tags: ['4大实训模块', '业务闭环实操', '成绩实时可见'] });

  // 2 目录
  drawTOC(pptx.addSlide(), [
    { num: '01', title: '快速上手', desc: '6 步走通业务闭环，先看这张图再动手', color: C.primary, pages: 'P03' },
    { num: '02', title: '六步实训行动', desc: '登录 → 搭链 → 合约 → 发能量 → 资产 → 钱包', color: C.info, pages: 'P04-09' },
    { num: '03', title: '验证 · 报告 · 成绩', desc: '链上验证 · 实训报告 · 成绩怎么算 · 评分体系', color: C.success, pages: 'P10-13' },
    { num: '04', title: '高分攻略', desc: '6 条行动清单直取高分项', color: C.accent, pages: 'P14' },
    { num: '05', title: '常见问题', desc: 'FAQ 自助排查', color: C.warn, pages: 'P15' },
  ], drawHeader, drawFooter, 2, TOTAL);

  // 3 快速上手：6 步行动路线图（行动导向：先告诉学生怎么做）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '快速上手 · 6 步走通实训', 'Quick Start · 每步都自动计分', 3, TOTAL);
    drawFooter(slide);
    const steps = [
      { t: '登录并熟悉看板', d: '学号密码登录，看板看链状态', page: 'P04', c: C.primary },
      { t: '10 步教程搭链', d: '云桌面终端逐步执行，严格按序', page: 'P05', c: C.info },
      { t: '编写并部署合约', d: 'IDE 编译通过 → 一键部署上链', page: 'P06', c: C.success },
      { t: '5 角色发能量', d: '切角色 · 填凭证 · 满足阈值上链', page: 'P07', c: C.warn },
      { t: '兑换资产并成交', d: '能量兑换 → 挂牌 → 促成交易', page: 'P08', c: C.accent },
      { t: '验证并生成报告', d: '链上自证 → 报告查漏 → 查成绩', page: 'P10', c: C.primary2 },
    ];
    steps.forEach((s, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 0.5 + col * 3.2, y = 1.1 + row * 2.45;
      drawCard(slide, x, y, 2.8, 2.15, { border: s.c, borderWidth: 0.5 });
      drawStepCircle(slide, x + 0.18, y + 0.2, i + 1, 0.4, s.c);
      slide.addText(s.t, { x: x + 0.68, y: y + 0.2, w: 2.0, h: 0.4, fontSize: S.base, fontFace: F.sans, color: s.c, bold: true, valign: 'middle' });
      slide.addText(s.d, { x: x + 0.18, y: y + 0.78, w: 2.44, h: 0.62, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
      drawTag(slide, x + 0.18, y + 1.62, s.page + ' 详解', s.c);
      if (col < 2) drawArrowH(slide, x + 2.85, y + 0.95, 0.3);
    });
    slide.addShape('roundRect', { x: 0.5, y: 6.25, w: 9, h: 0.6, fill: { color: C.primary, transparency: 90 }, line: { color: C.primary, width: 0.5, transparency: 60 }, rectRadius: 0.06 });
    slide.addText('每步行为都自动计入实训成绩，全程约 2 小时 —— 按顺序做完即拿基础全分', { x: 0.6, y: 6.25, w: 8.8, h: 0.6, fontSize: S.sm, fontFace: F.sans, color: C.primary, align: 'center', valign: 'middle' });
  }
  
  // 4 第 1 步 · 登录平台（合并原看板页：登录后第一件事就是看看板）
  slideScreenshot(pptx.addSlide(), drawHeader, drawFooter, 4, TOTAL, '第 1 步 · 登录平台', 'How to · 登录后看看板确认链状态', 'login-hd.png', 'localhost:5173/#/login', C.primary,
    '登录页：学号密码 / SSO 统一认证，登录成功直达总览看板',
    '怎么做', '4步', C.primary, [
      { t: '① 输入学号与密码', d: '密码 RSA 加密，转发 SSO 统一认证', c: C.primary },
      { t: '② 自动发放个人钱包', d: '学生自动获得 stu: 专属钱包别名', c: C.info },
      { t: '③ 看板确认链状态', d: '块高 / TPS / 节点 / 教程进度，15秒刷新', c: C.success },
      { t: '④ 会话自动保持', d: '刷新页面自动恢复，无需重新登录', c: C.warn },
    ]);

  // 5 第 2 步 · 10 步教程搭链
  slideScreenshot(pptx.addSlide(), drawHeader, drawFooter, 5, TOTAL, '第 2 步 · 10 步教程搭链', 'How to · 云桌面终端按顺序执行', 'cloud-hd.png', 'localhost:5173/#/cloud', C.primary,
    '搭链云桌面：左侧 10 步导航 + 总进度环，右侧终端实时回显命令输出',
    '怎么做', '按序执行', C.warn, [
      { t: 'Step 1-4 链底层', d: '生成配置 → 构建证书 → 启动节点 → 接入控制台', c: C.primary },
      { t: 'Step 5-8 联盟接入', d: '证书核查 → 治理规则 → 钱包注册 → 健康检查', c: C.info },
      { t: 'Step 9 合约部署', d: '部署 GreenEnergy ERC20 合约', c: C.success },
      { t: 'Step 10 链路验证', d: '5 角色发能量，打通全链路', c: C.accent },
    ]);

  // 6 第 3 步 · 合约开发（低清竖图源图按纵向比例宽度铺满展示，控制放大倍率）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '第 3 步 · 合约开发', 'How to · 选模板 → 编译 → 部署 → 调用', 6, TOTAL);
    drawFooter(slide);
    const cols = [
      { img: 'ide.png', url: 'localhost:5173/#/ide', border: C.info, cap: '合约 IDE：内置模板 · Monaco 编辑 · 实时编译回显' },
      { img: 'contracts.png', url: 'localhost:5173/#/contracts', border: C.success, cap: '合约管理：部署状态 · 合约地址 · 方法调用' },
    ];
    cols.forEach((col, i) => {
      const x = 0.5 + i * 4.65;
      drawScreenshot(slide, x, 1.05, 4.35, 4.3, shot(col.img), { url: col.url, border: col.border });
      slide.addText(col.cap, { x, y: 5.42, w: 4.35, h: 0.26, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    });
    // 底部行动条：4 步操作（先告诉学生怎么做）
    const acts = [
      { n: '1', t: '选模板改代码', d: 'ERC20 / 721 / 1155 内置模板', c: C.info },
      { n: '2', t: '编译通过', d: '实时回显结果，编译计入得分', c: C.primary },
      { n: '3', t: '一键部署上链', d: '部署成功即计合约开发维度分', c: C.success },
      { n: '4', t: '界面调用方法', d: 'ABI 自动生成表单，调用即上链', c: C.warn },
    ];
    const cw = (9 - 3 * 0.15) / 4;
    acts.forEach((a, i) => {
      const x = 0.5 + i * (cw + 0.15);
      drawCard(slide, x, 5.95, cw, 1.15, { border: a.c, borderWidth: 0.5 });
      drawStepCircle(slide, x + 0.12, 6.07, a.n, 0.3, a.c);
      slide.addText(a.t, { x: x + 0.5, y: 6.07, w: cw - 0.6, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: a.c, bold: true, valign: 'middle' });
      slide.addText(a.d, { x: x + 0.12, y: 6.45, w: cw - 0.24, h: 0.56, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
    });
  }

  // 7 第 4 步 · 能量发放
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '第 4 步 · 能量发放', 'How to · 切角色 → 填凭证 → 签名 → 上链', 7, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 5.3, 4.35, shot('eco-hd.png'), { url: 'localhost:5173/#/eco', border: C.success });
    slide.addText('绿色低碳联盟链：角色卡片切换 + 凭证表单（含业务单号）', { x: 0.5, y: 5.42, w: 5.3, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 6.0, 1.0, 3.5, 4.35);
    drawCardTitle(slide, 6.15, 1.1, 3.2, '怎么做 · 5 步', { tag: '上链', tagColor: C.success });
    [
      { n: '1', t: '切换联盟角色', d: '地铁/公交/单车/外卖/回收', c: C.primary },
      { n: '2', t: '填业务凭证与单号', d: '满足阈值，如里程 ≥10km', c: C.info },
      { n: '3', t: '角色钱包签名', d: '联盟私钥签名防伪造', c: C.success },
      { n: '4', t: '链上 mint 铸造', d: 'GreenEnergy.mint 上链', c: C.warn },
      { n: '5', t: '记录与余额更新', d: 'proof_no 防重复发放', c: C.accent },
    ].forEach((s, i) => {
      const y = 1.55 + i * 0.74;
      drawStepCircle(slide, 6.2, y, s.n, 0.3, s.c);
      slide.addText(s.t, { x: 6.6, y: y - 0.03, w: 2.8, h: 0.24, fontSize: S.base, fontFace: F.sans, color: s.c, bold: true, valign: 'middle' });
      slide.addText(s.d, { x: 6.6, y: y + 0.2, w: 2.8, h: 0.24, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    });
    drawCard(slide, 0.5, 5.85, 9, 1.0);
    drawCardTitle(slide, 0.65, 5.9, 8.7, '能量规则速览', { tag: '阈值', tagColor: C.warn });
    [
      ['地铁 +50', '里程≥10km', C.info], ['公交 +20', '时长≥5min', C.success], ['单车 +15', '骑行≥3min', C.warn],
      ['外卖 +10', '无需餐具', C.accent], ['回收 +100', '重量≥1kg', C.primary2],
    ].forEach((r, i) => {
      const x = 0.75 + i * 1.75;
      slide.addText(r[0], { x, y: 6.28, w: 1.6, h: 0.22, fontSize: S.sm, fontFace: F.sans, color: r[2], bold: true, valign: 'middle' });
      slide.addText(r[1], { x, y: 6.52, w: 1.6, h: 0.2, fontSize: S.xs, fontFace: F.mono, color: C.textDim, valign: 'middle' });
    });
  }

  // 8 第 5 步 · 资产兑换与交易
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '第 5 步 · 资产兑换与交易', 'How to · 兑换 → 挂牌 → 成交', 8, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 5.4, 4.6, shot('nft-hd.png'), { url: 'localhost:5173/#/nft', border: C.accent });
    slide.addText('NFT 市场：绿色资产 + 数字 NFT 双市场 · 交易时间线', { x: 0.5, y: 5.68, w: 5.4, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 6.1, 1.0, 3.4, 4.6);
    drawCardTitle(slide, 6.25, 1.1, 3.1, '怎么做 · 4 步', { tag: '闭环', tagColor: C.primary });
    [
      { n: '1', t: '能量兑换资产', d: '植树证书 ERC721 / 勋章·骑行券 ERC1155', c: C.primary },
      { n: '2', t: '市场挂牌', d: '设定能量价格上架，可取消改价', c: C.info },
      { n: '3', t: '他人购买成交', d: '能量结算，资产链上过户', c: C.success },
      { n: '4', t: '成交计入成绩', d: '绿色成交同时计入 C 项 NFT 交易', c: C.accent },
    ].forEach((f, i) => {
      const y = 1.6 + i * 0.98;
      drawStepCircle(slide, 6.3, y, f.n, 0.3, f.c);
      slide.addText(f.t, { x: 6.7, y: y - 0.03, w: 2.7, h: 0.24, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, valign: 'middle' });
      slide.addText(f.d, { x: 6.7, y: y + 0.2, w: 2.7, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
    });
    slide.addShape('roundRect', { x: 0.5, y: 6.15, w: 9, h: 0.5, fill: { color: C.accent, transparency: 90 }, line: { color: C.accent, width: 0.5, transparency: 60 }, rectRadius: 0.06 });
    slide.addText('提示：卖出资产后报告分数不回退（持有 ∪ 已售口径）——鼓励流通，放心交易', { x: 0.6, y: 6.15, w: 8.8, h: 0.5, fontSize: S.xs, fontFace: F.sans, color: C.accent, align: 'center', valign: 'middle' });
  }

  // 9 第 6 步 · 钱包与证书
  slideScreenshot(pptx.addSlide(), drawHeader, drawFooter, 9, TOTAL, '第 6 步 · 钱包与证书', 'Wallet · 余额 / 转账 / NFT 资产', 'wallet-hd.png', 'localhost:5173/#/wallet', C.info,
    '钱包页：GE 余额 + 转账流水 + 证书/勋章展示 + 能量发放记录（含业务单号）',
    '资产三件套', 'NFT', C.accent, [
      { t: '植树证书 ERC721', d: '消耗能量兑换，每枚独一无二', c: C.success },
      { t: '勋章/骑行券 ERC1155', d: '联盟角色签发，可批量持有流转', c: C.info },
      { t: 'GE 能量代币', d: '发放获取，兑换与市场交易计价', c: C.warn },
    ]);

  // 10 第 7 步 · 链上验证（浏览器横图 + 接口调试竖图，低清图宽度铺满控制放大倍率）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '第 7 步 · 链上验证', 'How to · 复制 hash → 检索 → 调用 → 留证', 10, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.05, 5.35, 4.3, shot('explorer-hd.png'), { url: 'localhost:5173/#/explorer', border: C.info });
    slide.addText('区块链浏览器：区块 / 交易 / 合约 / 地址四维追溯', { x: 0.5, y: 5.42, w: 5.35, h: 0.26, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawScreenshot(slide, 6.15, 1.05, 3.35, 4.3, shot('interfaces.png'), { url: 'localhost:5173/#/interfaces', border: C.warn });
    slide.addText('接口调试：直接调用平台 API 验证', { x: 6.15, y: 5.42, w: 3.35, h: 0.26, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    const acts = [
      { n: '1', t: '复制交易 hash', d: '从交易详情或钱包流水获取', c: C.info },
      { n: '2', t: '浏览器检索核对', d: '入参解码可读，逐项核对', c: C.primary },
      { n: '3', t: '接口调试验证', d: '每次调用计入验证维度分', c: C.warn },
      { n: '4', t: '截图留证入报告', d: '作为实训报告佐证材料', c: C.success },
    ];
    const cw = (9 - 3 * 0.15) / 4;
    acts.forEach((a, i) => {
      const x = 0.5 + i * (cw + 0.15);
      drawCard(slide, x, 5.95, cw, 1.15, { border: a.c, borderWidth: 0.5 });
      drawStepCircle(slide, x + 0.12, 6.07, a.n, 0.3, a.c);
      slide.addText(a.t, { x: x + 0.5, y: 6.07, w: cw - 0.6, h: 0.3, fontSize: S.sm, fontFace: F.sans, color: a.c, bold: true, valign: 'middle' });
      slide.addText(a.d, { x: x + 0.12, y: 6.45, w: cw - 0.24, h: 0.56, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
    });
  }

  // 11 第 8 步 · 实训报告（9 项评分九宫格）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '第 8 步 · 生成实训报告', 'How to · 生成 → 查漏 → 补齐 → 导出', 11, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 5.4, 5.2, shot('report-hd.png'), { url: 'localhost:5173/#/report', border: C.success });
    slide.addText('实训报告：9 项得分 + 绿色资产 KPI + 改进建议 + Markdown 导出', { x: 0.5, y: 6.28, w: 5.4, h: 0.4, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 6.1, 1.0, 3.4, 5.2);
    drawCardTitle(slide, 6.25, 1.1, 3.1, '9 项评分构成', { tag: '100分', tagColor: C.warn });
    [
      ['A', '合约部署', '20', C.primary], ['B', '链上交易', '15', C.info], ['C', 'NFT交易', '10', C.accent],
      ['D', '搭链教程', '10', C.success], ['E', '角色体验', '10', C.warn], ['F', '能量发放', '10', C.primary2],
      ['G', '资产兑换', '15', C.info], ['H', '合约激活', '5', C.textDim], ['I', '综合拓展', '5', C.textDim],
    ].forEach((it, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 6.25 + col * 1.06, y = 1.6 + row * 1.25;
      drawCard(slide, x, y, 0.96, 1.1, { border: it[3], borderWidth: 0.5 });
      slide.addText(it[0], { x, y: y + 0.06, w: 0.96, h: 0.26, fontSize: S.md, fontFace: F.mono, color: it[3], bold: true, align: 'center', valign: 'middle' });
      slide.addText(it[1], { x, y: y + 0.34, w: 0.96, h: 0.24, fontSize: 8, fontFace: F.sans, color: C.text, align: 'center', valign: 'middle' });
      slide.addText(it[2] + '分', { x, y: y + 0.62, w: 0.96, h: 0.3, fontSize: S.sm, fontFace: F.mono, color: C.warn, bold: true, align: 'center', valign: 'middle' });
    });
    slide.addText('扣分项上限 15 分 · 市场成交计入 C 项', { x: 6.1, y: 5.35, w: 3.4, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
  }

  // 12 成绩怎么算（我的成绩）
  slideScreenshot(pptx.addSlide(), drawHeader, drawFooter, 12, TOTAL, '成绩怎么算', 'How to · 实训×0.6 + 教师×0.4', 'my-grades-hd.png', 'localhost:5173/#/my-grades', C.accent,
    '我的成绩：实训成绩 + 教师评分 + 综合成绩 + 四维雷达明细',
    '成绩怎么来', '公式', C.primary, [
      { t: '实训成绩（自动）', d: '平台行为数据 4 维加权，实时计算', c: C.primary },
      { t: '教师评分（录入）', d: '教师按报告与课堂表现打分', c: C.info },
      { t: '综合成绩', d: 'final = 实训×0.6 + 教师×0.4', c: C.warn },
    ]);

  // 13 评分体系
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '评分体系详解', 'Scoring System · 4 维加权', 13, TOTAL);
    drawFooter(slide);
    [
      { name: '链搭建 chain_setup', w: 0.20, how: 'IDE 打开 / 工程保存 / 教程完成', color: C.primary },
      { name: '合约开发 contract_dev', w: 0.30, how: '编译通过 / 合约部署数量', color: C.info },
      { name: '链上验证 chain_verify', w: 0.25, how: '接口调用 / 合约调用 / 链上交易', color: C.success },
      { name: '联盟治理 alliance_gov', w: 0.25, how: '角色切换 / 发能量 / NFT 铸造与市场成交', color: C.accent },
    ].forEach((d, i) => {
      const y = 1.05 + i * 1.28;
      drawCard(slide, 0.5, y, 9, 1.12, { border: d.color, borderWidth: 0.5 });
      slide.addText(d.name, { x: 0.7, y: y + 0.12, w: 3.4, h: 0.3, fontSize: S.md, fontFace: F.sans, color: d.color, bold: true, valign: 'middle' });
      slide.addText(d.how, { x: 0.7, y: y + 0.46, w: 4.6, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
      slide.addText('权重', { x: 5.5, y: y + 0.14, w: 0.6, h: 0.25, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'middle' });
      slide.addShape('roundRect', { x: 6.15, y: y + 0.2, w: 2.5, h: 0.14, fill: { color: C.border }, line: { width: 0 }, rectRadius: 0.05 });
      slide.addShape('roundRect', { x: 6.15, y: y + 0.2, w: 2.5 * d.w / 0.30, h: 0.14, fill: { color: d.color }, line: { width: 0 }, rectRadius: 0.05 });
      slide.addText(`${Math.round(d.w * 100)}%`, { x: 8.75, y: y + 0.08, w: 0.6, h: 0.35, fontSize: S.lg, fontFace: F.mono, color: d.color, bold: true, valign: 'middle' });
      slide.addText('单项得分（满分100）× 权重 → 实训总分', { x: 0.7, y: y + 0.78, w: 8.5, h: 0.22, fontSize: S.xs, fontFace: F.mono, color: C.textDimmer, valign: 'middle' });
    });
    slide.addShape('roundRect', { x: 0.5, y: 6.3, w: 9, h: 0.5, fill: { color: C.warn, transparency: 90 }, line: { color: C.warn, width: 0.5, transparency: 60 }, rectRadius: 0.06 });
    slide.addText('综合成绩 = 实训成绩 × 0.6 + 教师评分 × 0.4 —— 行为数据与教师评价双轨合一', { x: 0.6, y: 6.3, w: 8.8, h: 0.5, fontSize: S.sm, fontFace: F.mono, color: C.warn, bold: true, align: 'center', valign: 'middle' });
  }

  // 14 高分攻略（行动清单）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '高分攻略 · 照做清单', 'High-Score Playbook · 6 条行动', 14, TOTAL);
    drawFooter(slide);
    [
      { t: '10 步教程全做完', d: 'D 项满分 10 + 链搭建权重 20%', c: C.primary },
      { t: '编译并部署合约', d: 'contract_dev 权重最高 30%', c: C.info },
      { t: '5 角色都发能量', d: 'E 项多样性 + 治理维度双重计分', c: C.success },
      { t: '兑换资产并挂牌成交', d: 'G 项 15 分 + C 项市场成交加分', c: C.accent },
      { t: '接口调试多验证', d: 'chain_verify 每次调用都计数', c: C.warn },
      { t: '生成并导出报告', d: '按建议补齐短板项，冲卓越等级', c: C.primary2 },
    ].forEach((t, i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 0.5 + col * 3.1, y = 1.05 + row * 2.0;
      drawCard(slide, x, y, 2.9, 1.8, { border: t.c, borderWidth: 0.5 });
      drawStepCircle(slide, x + 0.15, y + 0.15, i + 1, 0.3, t.c);
      slide.addText(t.t, { x: x + 0.55, y: y + 0.15, w: 2.25, h: 0.35, fontSize: S.base, fontFace: F.sans, color: t.c, bold: true, valign: 'middle' });
      slide.addText(t.d, { x: x + 0.15, y: y + 0.7, w: 2.6, h: 0.95, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'top' });
    });
    slide.addText('等级：优秀 ≥90 · 良好 80-89 · 中等 70-79 · 及格 60-69 —— 报告页可查看每项差距', { x: 0.5, y: 6.55, w: 9, h: 0.3, fontSize: S.xs, fontFace: F.mono, color: C.textDim, align: 'center' });
  }

  // 15 FAQ
  drawFAQ(pptx.addSlide(), drawHeader, drawFooter, 15, TOTAL, [
    { q: '教程步骤可以跳过吗？', a: '不可以。10 步严格按顺序执行，前一步完成才能解锁下一步。' },
    { q: '能量发放失败怎么办？', a: '检查凭证是否满足阈值、业务单号是否重复（同一单号防重复发放）。' },
    { q: '卖出资产后分数会变少吗？', a: '不会。资产计数采用「持有 ∪ 已售」闭环口径，鼓励流通。' },
    { q: '成绩多久更新一次？', a: '实训成绩由行为数据实时聚合，打开「我的成绩」即为最新值。' },
    { q: '报告可以导出吗？', a: '可以。实训报告支持 Markdown 导出，含全部明细与建议。' },
    { q: '忘记切换角色会怎样？', a: '发放会用当前角色签名，凭证类型须与角色匹配，请先切换再填写。' },
  ]);

  // 结束页
  drawEnd(pptx, { themeColor: C.primary, endTitle: '祝实训顺利，成绩卓越', endSubtitle: 'FISCO 联盟链实训平台 · 学生使用手册', endTips: '按「高分攻略」走完业务闭环，报告建议项逐一补齐即可冲刺 90+' }, drawFooter);

  return pptx;
}

// ============================================================================
// 教师使用手册（14 页 + 结束页）
// ============================================================================
function buildTeacherManual() {
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: 'MANUAL', width: 10, height: 7.5 });
  pptx.layout = 'MANUAL';
  pptx.author = 'FISCO 联盟链实训平台';
  pptx.company = '天择教育';
  pptx.title = '教师使用手册';
  const TOTAL = 14;
  const drawHeader = makeHeader('教师手册');
  const drawFooter = makeFooter('教师使用手册');

  // 1 封面
  drawCover(pptx, { title: '教师使用手册', subtitle: 'Teacher Manual · 成绩管理与教学督导', themeColor: C.info, tags: ['成绩自动核算', '一键录入评价', '班级学情总览'] });

  // 2 目录
  drawTOC(pptx.addSlide(), [
    { num: '01', title: '登录与权限', desc: '教师身份识别 · 专属功能入口', color: C.primary, pages: 'P03' },
    { num: '02', title: '成绩评价双轨制', desc: '自动核算 60% + 教师评分 40%', color: C.info, pages: 'P04' },
    { num: '03', title: '学生成绩管理', desc: '成绩列表 · 自动核算 · 评分录入 · 学情统计', color: C.success, pages: 'P05-09' },
    { num: '04', title: '教学督导与答疑', desc: '报告抽查 · 平台监控 · 常见问题', color: C.accent, pages: 'P10-13' },
  ], drawHeader, drawFooter, 2, TOTAL);

  // 3 登录与权限
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '登录与教师权限', 'Teacher Login & Permissions', 3, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 5.2, 5.4, shot('login-hd.png'), { url: 'localhost:5173/#/login', border: C.primary });
    slide.addText('教师账号登录：roleId=3 自动识别，解锁「学生成绩」专属菜单', { x: 0.5, y: 6.5, w: 5.2, h: 0.4, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 5.9, 1.0, 3.6, 5.4);
    drawCardTitle(slide, 6.05, 1.1, 3.3, '教师能做什么', { tag: '权限', tagColor: C.info });
    drawBulletList(slide, 6.05, 1.6, 3.3, [
      { t: '学生成绩管理', d: '按班级查看/筛选全部学生成绩', c: C.primary },
      { t: '一键自动核算', d: '实时聚合行为数据算实训分', c: C.info },
      { t: '录入教师评分', d: '支持一键生成评分草稿', c: C.success },
      { t: '批量刷新训练分', d: '全班实训成绩一键重算', c: C.warn },
      { t: '学情统计分析', d: '班级均分 / 课程维度统计', c: C.accent },
    ], 0.95);
    slide.addText('非教师访问 /grades 将被路由守卫拦截', { x: 5.9, y: 6.55, w: 3.6, h: 0.25, fontSize: S.xs, fontFace: F.mono, color: C.textDimmer, align: 'center' });
  }

  // 4 双轨制评分模型
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '成绩评价双轨制', 'Grading Model · 数据 + 人工', 4, TOTAL);
    drawFooter(slide);
    drawCard(slide, 0.5, 1.1, 4.3, 3.6, { border: C.primary, borderWidth: 0.75 });
    drawCardTitle(slide, 0.65, 1.2, 4.0, '实训成绩（自动 60%）', { tag: '平台数据', tagColor: C.primary });
    drawBulletList(slide, 0.65, 1.75, 4.0, [
      { t: '数据自动聚合', d: '学习事件/部署/交易/市场成交统一聚合', c: C.primary },
      { t: '4 维加权', d: '链搭建20% · 合约30% · 链上验证25% · 联盟治理25%', c: C.info },
      { t: '实时可重算', d: '行为发生即可刷新，无主观偏差', c: C.success },
    ], 1.05);
    drawCard(slide, 5.2, 1.1, 4.3, 3.6, { border: C.accent, borderWidth: 0.75 });
    drawCardTitle(slide, 5.35, 1.2, 4.0, '教师评分（人工 40%）', { tag: '教师录入', tagColor: C.accent });
    drawBulletList(slide, 5.35, 1.75, 4.0, [
      { t: '报告质量评价', d: '实训报告完整性与深度', c: C.accent },
      { t: '课堂表现', d: '参与度 / 协作 / 答辩表现', c: C.warn },
      { t: '草稿辅助', d: 'auto-draft 依据实训分生成建议分', c: C.info },
    ], 1.05);
    slide.addShape('roundRect', { x: 1.5, y: 5.0, w: 7, h: 0.85, fill: { color: C.warn, transparency: 90 }, line: { color: C.warn, width: 1 }, rectRadius: 0.1 });
    slide.addText('综合成绩 = 实训成绩 × 0.6 + 教师评分 × 0.4', { x: 1.5, y: 5.06, w: 7, h: 0.45, fontSize: S.xl, fontFace: F.mono, color: C.warn, bold: true, align: 'center', valign: 'middle' });
    slide.addText('系统自动合成 final_score 并落库，教师只需录入自己的 40%', { x: 1.5, y: 5.52, w: 7, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    ['学生完成实训', '自动核算 60%', '教师录入 40%', '系统合成终评'].forEach((f, i) => {
      const x = 0.55 + i * 2.3;
      drawStepCircle(slide, x, 6.45, i + 1, 0.3, [C.primary, C.info, C.accent, C.warn][i]);
      slide.addText(f, { x: x + 0.4, y: 6.42, w: 1.85, h: 0.35, fontSize: S.sm, fontFace: F.sans, color: C.text, valign: 'middle' });
    });
  }

  // 5 学生成绩管理工作台（grades 页示意用 my-grades 截图）
  slideScreenshot(pptx.addSlide(), drawHeader, drawFooter, 5, TOTAL, '学生成绩管理工作台', 'Grades Console · 教师专属', 'my-grades-hd.png', 'localhost:5173/#/grades', C.info,
    '学生成绩页：班级筛选 + 三列成绩（实训/教师/综合）+ 明细展开 + 快捷操作',
    '核心操作', '4项', C.info, [
      { t: '班级/课程筛选', d: '教师默认只看本班数据', c: C.primary },
      { t: '单人核算', d: '行内一键实时算实训分与 4 维明细', c: C.info },
      { t: '全班刷新', d: '批量重算全班实训成绩并落库', c: C.success },
      { t: '录入教师分', d: '保存后自动合成综合终评', c: C.warn },
    ]);

  // 6 自动核算引擎（数据来源）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '实训成绩自动核算', 'Auto Scoring · 单一事实源聚合', 6, TOTAL);
    drawFooter(slide);
    drawCard(slide, 0.5, 1.0, 5.6, 5.4);
    drawCardTitle(slide, 0.65, 1.1, 5.3, '核算数据来源', { tag: '单一事实源', tagColor: C.primary });
    [
      ['learning_events', 'IDE/编译/角色切换/报告查看等行为'],
      ['deployed_contracts', '合约部署数量'],
      ['contract_calls', '合约调用次数'],
      ['transactions', '链上交易笔数'],
      ['nfts + nft_trades', 'NFT 铸造与交易'],
      ['eco_energy_records', '绿色能量发放记录'],
      ['eco_market_listings', '绿色市场成交（业务闭环）'],
    ].forEach((s, i) => {
      const y = 1.6 + i * 0.66;
      slide.addShape('rect', { x: 0.75, y, w: 5.0, h: 0.58, fill: { color: i % 2 === 0 ? C.panel : C.panel2 }, line: { color: C.border, width: 0.5 } });
      slide.addShape('rect', { x: 0.75, y, w: 0.04, h: 0.58, fill: { color: C.primary }, line: { width: 0 } });
      slide.addText(s[0], { x: 0.9, y, w: 2.2, h: 0.58, fontSize: S.xs, fontFace: F.mono, color: C.primary, valign: 'middle' });
      slide.addText(s[1], { x: 3.15, y, w: 2.5, h: 0.58, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    });
    drawCard(slide, 6.3, 1.0, 3.2, 5.4);
    drawCardTitle(slide, 6.45, 1.1, 2.9, '教师操作', { tag: '2种', tagColor: C.warn });
    drawBulletList(slide, 6.45, 1.7, 2.95, [
      { t: '单人核算', d: '列表行内点击「核算」，立即返回 4 维明细与实训分', c: C.info },
      { t: '全班刷新', d: '顶栏「刷新全班实训分」批量重算', c: C.warn },
      { t: '结果可解释', d: '每维展示原始计数，评分完全透明', c: C.success },
    ], 1.55);
  }

  // 7 教师评分录入流程
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '教师评分录入', 'Manual Scoring · 草稿 / 调整 / 合成', 7, TOTAL);
    drawFooter(slide);
    [
      { n: '1', t: '查看实训报告', d: '核对 9 项明细与建议项完成度', c: C.primary },
      { n: '2', t: '一键生成草稿', d: 'auto-draft 依实训分给出建议教师分', c: C.info },
      { n: '3', t: '人工调整确认', d: '结合课堂表现/答辩微调', c: C.success },
      { n: '4', t: '自动合成终评', d: '保存即合成 实训×0.6 + 教师×0.4', c: C.accent },
    ].forEach((f, i) => {
      const x = 0.6 + i * 2.35;
      drawCard(slide, x, 1.15, 2.15, 2.3, { border: f.c, borderWidth: 0.5 });
      drawStepCircle(slide, x + 0.82, 1.35, f.n, 0.4, f.c);
      slide.addText(f.t, { x: x + 0.1, y: 1.95, w: 1.95, h: 0.3, fontSize: S.base, fontFace: F.sans, color: f.c, bold: true, align: 'center', valign: 'middle' });
      slide.addText(f.d, { x: x + 0.1, y: 2.3, w: 1.95, h: 0.9, fontSize: S.xs, fontFace: F.sans, color: C.text, align: 'center', valign: 'top' });
      if (i < 3) drawArrowH(slide, x + 2.15, 2.2, 0.2);
    });
    drawCard(slide, 0.5, 3.85, 9, 2.7);
    drawCardTitle(slide, 0.65, 3.95, 8.7, '评分建议标准', { tag: '参考', tagColor: C.success });
    [
      ['90-100', '报告完整、闭环全走完、有拓展创新', C.success],
      ['80-89', '闭环基本完成，报告规范，少量短板', C.primary],
      ['70-79', '完成主要模块，报告有缺项', C.info],
      ['60-69', '仅完成基础操作，报告简略', C.warn],
      ['<60', '核心模块未完成', C.error],
    ].forEach((r, i) => {
      const y = 4.4 + i * 0.4;
      slide.addShape('roundRect', { x: 0.8, y, w: 0.9, h: 0.3, fill: { color: r[2], transparency: 82 }, line: { color: r[2], width: 0.5 }, rectRadius: 0.04 });
      slide.addText(r[0], { x: 0.8, y, w: 0.9, h: 0.3, fontSize: S.xs, fontFace: F.mono, color: r[2], bold: true, align: 'center', valign: 'middle' });
      slide.addText(r[1], { x: 1.9, y, w: 7.3, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    });
  }

  // 8 学情统计与报告抽查（report 截图）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '学情统计与报告抽查', 'Learning Analytics & Report Review', 8, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 5.3, 5.4, shot('report-hd.png'), { url: 'localhost:5173/#/report', border: C.success });
    slide.addText('实训报告页：可切换学生视角抽查 9 项得分明细与改进建议', { x: 0.5, y: 6.5, w: 5.3, h: 0.4, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 6.1, 1.0, 3.4, 5.4);
    drawCardTitle(slide, 6.25, 1.1, 3.1, '督导要点', { tag: '3招', tagColor: C.warn });
    drawBulletList(slide, 6.25, 1.6, 3.1, [
      { t: '班级统计', d: '均分/及格率/课程维度对比，定位薄弱班', c: C.primary },
      { t: '报告抽查', d: '按综合分排序抽查高低两端报告', c: C.success },
      { t: '短板干预', d: '按 4 维雷达图布置针对性补练', c: C.accent },
    ], 1.45);
  }

  // 9 平台运行监控（monitor 低清竖图按纵向比例展示）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '平台运行监控', 'Monitor · 课前环境自检', 9, TOTAL);
    drawFooter(slide);
    drawScreenshot(slide, 0.5, 1.0, 4.3, 5.4, shot('monitor.png'), { url: 'localhost:5173/#/monitor', border: C.warn });
    slide.addText('节点监控：节点状态 / 出块情况 / 接口健康', { x: 0.5, y: 6.5, w: 4.3, h: 0.4, fontSize: S.xs, fontFace: F.sans, color: C.textDim, align: 'center' });
    drawCard(slide, 5.0, 1.0, 4.5, 4.3);
    drawCardTitle(slide, 5.15, 1.1, 4.2, '课前自检清单', { tag: 'Check', tagColor: C.success });
    drawBulletList(slide, 5.15, 1.6, 4.2, [
      { t: '节点在线', d: '4 节点全部健康、持续出块', c: C.success },
      { t: '合约就绪', d: '三大业务合约已部署', c: C.info },
      { t: '账号可登录', d: '抽测 1-2 个学生账号', c: C.warn },
    ], 1.15);
    slide.addShape('roundRect', { x: 5.0, y: 5.5, w: 4.5, h: 0.9, fill: { color: C.warn, transparency: 90 }, line: { color: C.warn, width: 0.5, transparency: 60 }, rectRadius: 0.06 });
    slide.addText('课前 5 分钟完成自检，异常先查监控页再上课', { x: 5.1, y: 5.5, w: 4.3, h: 0.9, fontSize: S.xs, fontFace: F.sans, color: C.warn, align: 'center', valign: 'middle' });
  }

  // 10 教学组织建议（周计划）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '教学组织建议', 'Teaching Plan · 4 周闭环实训', 10, TOTAL);
    drawFooter(slide);
    [
      { w: '第 1 周', t: '链底层搭建', d: '10 步教程 + 总览看板解读', c: C.primary },
      { w: '第 2 周', t: '合约开发', d: 'IDE 编写/编译/部署 + 接口调试', c: C.info },
      { w: '第 3 周', t: '绿色联盟业务', d: '发能量 → 兑换 → 挂牌成交闭环', c: C.success },
      { w: '第 4 周', t: '评价与复盘', d: '核算成绩 + 教师评分 + 报告讲评', c: C.accent },
    ].forEach((wk, i) => {
      const x = 0.5 + i * 2.35;
      drawCard(slide, x, 1.15, 2.15, 2.6, { border: wk.c, borderWidth: 0.5 });
      slide.addShape('roundRect', { x: x + 0.1, y: 1.3, w: 0.75, h: 0.3, fill: { color: wk.c, transparency: 82 }, line: { color: wk.c, width: 0.5 }, rectRadius: 0.04 });
      slide.addText(wk.w, { x: x + 0.1, y: 1.3, w: 0.75, h: 0.3, fontSize: S.xs, fontFace: F.mono, color: wk.c, bold: true, align: 'center', valign: 'middle' });
      slide.addText(wk.t, { x: x + 0.1, y: 1.75, w: 1.95, h: 0.35, fontSize: S.md, fontFace: F.sans, color: C.text, bold: true, valign: 'middle' });
      slide.addText(wk.d, { x: x + 0.1, y: 2.15, w: 1.95, h: 1.2, fontSize: S.xs, fontFace: F.sans, color: C.textDim, valign: 'top' });
      if (i < 3) drawArrowH(slide, x + 2.15, 2.3, 0.2);
    });
    drawCard(slide, 0.5, 4.15, 9, 2.35);
    drawCardTitle(slide, 0.65, 4.25, 8.7, '课堂组织技巧', { tag: '5条', tagColor: C.primary });
    [
      '双人结对：一人发能量一人购买，天然形成市场成交闭环',
      '阶段验收：每周结束用「全班刷新」核算实训分并公示排名',
      '以赛促学：成就中心徽章 + 班级排名激发参与度',
      '报告讲评：抽取高分/低分报告对比讲解 9 项得分差异',
      '防作弊：行为数据链上可溯，浏览器可查交易哈希',
    ].forEach((t, i) => {
      const y = 4.7 + i * 0.34;
      slide.addShape('ellipse', { x: 0.8, y: y + 0.08, w: 0.06, h: 0.06, fill: { color: C.primary }, line: { width: 0 } });
      slide.addText(t, { x: 1.0, y, w: 8.2, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
    });
  }

  // 11 评分体系速查（与学生手册一致的 4 维）
  {
    const slide = pptx.addSlide();
    drawBackground(slide);
    drawHeader(slide, '评分体系速查', 'Scoring Reference · 4 维权重', 11, TOTAL);
    drawFooter(slide);
    [
      { name: '链搭建', key: 'chain_setup', w: 20, how: 'IDE 使用 / 工程保存 / 教程完成步数', color: C.primary },
      { name: '合约开发', key: 'contract_dev', w: 30, how: '编译通过次数 / 合约部署数量', color: C.info },
      { name: '链上验证', key: 'chain_verify', w: 25, how: '接口调用 / 合约调用 / 链上交易笔数', color: C.success },
      { name: '联盟治理', key: 'alliance_gov', w: 25, how: '角色切换 / 能量发放 / NFT 铸造交易 / 市场成交', color: C.accent },
    ].forEach((d, i) => {
      const y = 1.05 + i * 1.1;
      drawCard(slide, 0.5, y, 9, 0.95, { border: d.color, borderWidth: 0.5 });
      slide.addText(`${d.name} ${d.key}`, { x: 0.7, y: y + 0.1, w: 3.6, h: 0.3, fontSize: S.md, fontFace: F.sans, color: d.color, bold: true, valign: 'middle' });
      slide.addText(d.how, { x: 0.7, y: y + 0.48, w: 5.0, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, valign: 'middle' });
      slide.addShape('roundRect', { x: 6.2, y: y + 0.4, w: 2.4, h: 0.14, fill: { color: C.border }, line: { width: 0 }, rectRadius: 0.05 });
      slide.addShape('roundRect', { x: 6.2, y: y + 0.4, w: 2.4 * d.w / 30, h: 0.14, fill: { color: d.color }, line: { width: 0 }, rectRadius: 0.05 });
      slide.addText(`${d.w}%`, { x: 8.85, y: y + 0.15, w: 0.55, h: 0.4, fontSize: S.lg, fontFace: F.mono, color: d.color, bold: true, valign: 'middle' });
    });
    slide.addShape('roundRect', { x: 0.5, y: 5.7, w: 9, h: 0.9, fill: { color: C.warn, transparency: 90 }, line: { color: C.warn, width: 0.75, transparency: 60 }, rectRadius: 0.08 });
    slide.addText('实训总分 = Σ(单项得分 × 权重)　|　综合成绩 = 实训 × 0.6 + 教师 × 0.4', { x: 0.6, y: 5.78, w: 8.8, h: 0.4, fontSize: S.md, fontFace: F.mono, color: C.warn, bold: true, align: 'center', valign: 'middle' });
    slide.addText('等级：优秀 ≥90 · 良好 80-89 · 中等 70-79 · 及格 60-69 · 不及格 <60', { x: 0.6, y: 6.22, w: 8.8, h: 0.3, fontSize: S.xs, fontFace: F.sans, color: C.text, align: 'center', valign: 'middle' });
  }

  // 12 教师常见问题一（数据与核算）
  drawFAQ(pptx.addSlide(), drawHeader, drawFooter, 12, TOTAL, [
    { q: '学生实训分为什么是 0？', a: '确认该学生已在平台产生行为数据，且钱包绑定正确；点击「核算」实时重算。' },
    { q: '教师评分能修改吗？', a: '可以。重复录入即覆盖，系统自动重算综合成绩。' },
    { q: '能看到其他班级吗？', a: '教师默认按所属班级过滤；管理员可查看全部班级。' },
    { q: '市场成交算成绩吗？', a: '算。绿色市场成交计入联盟治理维度，并同时计入报告 C 项。' },
    { q: '成绩会实时更新吗？', a: '实训分随时可刷新；教师分录入保存后立即合成终评。' },
    { q: '学生卖出资产会扣分吗？', a: '不会。资产计数采用「持有 ∪ 已售」闭环口径，鼓励流通。' },
  ]);

  // 13 教师常见问题二（课堂与运维）
  drawFAQ(pptx.addSlide(), drawHeader, drawFooter, 13, TOTAL, [
    { q: '课前要做什么准备？', a: '按「课前自检清单」检查节点出块、合约部署与账号登录。' },
    { q: '学生登录失败怎么办？', a: '核对学号密码；登录走 SSO 认证，可先用教师账号验证平台可用性。' },
    { q: '能量发不出去？', a: '检查凭证阈值与业务单号：同一单号不可重复发放。' },
    { q: '如何导出学生成绩？', a: '成绩页支持筛选后导出；实训明细含每维原始计数可复核。' },
    { q: '报告建议怎么用？', a: '报告自动生成改进建议，可作为课后作业布置给学生补齐短板。' },
    { q: '平台数据会重置吗？', a: '演示环境提供账号重置脚本；正式教学数据不会被自动清除。' },
  ]);

  // 结束页（占 1 页，总计仍为 14 页内容 + 结束页）
  drawEnd(pptx, { themeColor: C.info, endTitle: '数据驱动评价，让教学更省心', endSubtitle: 'FISCO 联盟链实训平台 · 教师使用手册', endTips: '自动核算保底、教师评分点睛，双轨合一形成完整评价闭环' }, drawFooter);

  return pptx;
}

// ============================================================================
// 主函数：生成两份手册
// ============================================================================
async function main() {
  const outDir = path.join(__dirname, 'output');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  console.log('生成学生使用手册 ...');
  const stu = buildStudentManual();
  const stuPath = path.join(outDir, '学生使用手册.pptx');
  await stu.writeFile({ fileName: stuPath });
  console.log(`学生使用手册生成成功: ${stuPath}`);

  console.log('生成教师使用手册 ...');
  const tea = buildTeacherManual();
  const teaPath = path.join(outDir, '教师使用手册.pptx');
  await tea.writeFile({ fileName: teaPath });
  console.log(`教师使用手册生成成功: ${teaPath}`);
}

main().catch(err => {
  console.error('生成失败:', err);
  process.exit(1);
});
