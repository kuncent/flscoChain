/**
 * PPT 共享主题模块（docs/ppt_theme.js）
 * 完整复用 generate-manual-ppt.js 的设计体系：
 *   - C 色彩常量（与前端 global.scss 逐值一致）
 *   - F 字体（中文 Microsoft YaHei / 代码 Consolas）
 *   - drawBackground / drawHeader / drawFooter / drawCard / drawCardTitle /
 *     drawCodeBlock / drawStepCircle / drawArrowH(V) / drawScreenshot 组件函数
 * 布局规格：16:9（PAGE_W=10, PAGE_H=7.5）
 */

const PptxGenJS = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

// 截图根目录与预校验
const SHOT_DIR = path.join(__dirname, 'assets', 'screenshots');
function shot(name) {
  const p = path.join(SHOT_DIR, name.endsWith('.png') ? name : `${name}.png`);
  if (!fs.existsSync(p)) throw new Error(`截图缺失: ${p}`);
  return p;
}
/** 启动时批量预校验所有用到的截图存在，缺失直接报错 */
function requireShots(names) {
  names.forEach((n) => shot(n));
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

function drawFooter(slide, text) {
  slide.addShape('rect', { x: 0, y: 7.18, w: '100%', h: 0.32, fill: { color: C.bg2 }, line: { color: C.border, width: 0.5 } });
  slide.addText(text || 'FISCO 联盟链实训平台 · 操作手册 v3.0', { x: 0.5, y: 7.2, w: 5, h: 0.28, fontSize: S.xs, fontFace: F.sans, color: C.textDimmer, valign: 'middle' });
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

/** 截图卡片：深色框 + 浏览器窗口顶栏 + 图片（cover）+ 标签 */
function drawScreenshot(slide, x, y, w, h, imgPath, opts = {}) {
  drawCard(slide, x, y, w, h, { fill: C.bg2, border: opts.border || C.border2, borderWidth: 0.75 });
  const barH = 0.26;
  slide.addShape('rect', { x: x, y: y, w: w, h: barH, fill: { color: C.panel2 }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.1, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.error }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.22, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.warn }, line: { width: 0 } });
  slide.addShape('ellipse', { x: x + 0.34, y: y + 0.09, w: 0.08, h: 0.08, fill: { color: C.success }, line: { width: 0 } });
  const url = opts.url || 'localhost:5173';
  slide.addText(url, { x: x + 0.5, y: y + 0.04, w: w - 1.4, h: barH - 0.08, fontSize: 7, fontFace: F.mono, color: C.textDimmer, valign: 'middle' });
  if (opts.live !== false) {
    drawTag(slide, x + w - 0.62, y + 0.05, 'LIVE', C.success);
  }
  const imgY = y + barH;
  const imgH = h - barH;
  slide.addShape('rect', { x: x, y: imgY, w: w, h: imgH, fill: { color: C.bg }, line: { width: 0 } });
  // 高清 3840x2160 截图：cover 按高度填满、裁掉左右两侧（页面左右多为边距/侧栏，裁切安全）
  slide.addImage({ path: imgPath, x: x, y: imgY, w: w, h: imgH, sizing: { type: 'cover', w: w, h: imgH }, rounding: true });
}

// ============================================================================
// 工厂函数
// ============================================================================
function createPptx(meta = {}) {
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = meta.author || 'FISCO 联盟链实训平台';
  pptx.company = meta.company || '天择教育';
  pptx.subject = meta.subject || '使用手册';
  pptx.title = meta.title || 'FISCO 联盟链实训平台';
  return pptx;
}

function ensureOutputDir() {
  const dir = path.join(__dirname, 'output');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

module.exports = {
  PptxGenJS, shot, requireShots, SHOT_DIR,
  C, F, S, PAGE_W, PAGE_H,
  drawBackground, drawHeader, drawFooter, drawCard, drawCardTitle, addToken,
  drawCodeBlock, drawTag, drawArrowH, drawArrowV, drawStepCircle, drawScreenshot,
  createPptx, ensureOutputDir,
};
