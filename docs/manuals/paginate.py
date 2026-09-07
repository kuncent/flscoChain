#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分页校准工具（文档工程脚本，非产品代码）

手册 HTML 采用「一个 <section class=\"page\"> = 一张 A4 版面」的版式，页眉页脚
按版面定位；若某版面内容超出一页，Chrome 打印时会溢出成无页脚的残页。

本工具在浏览器里完成：
  测量（含 margin 的块流模型）→ 超高表格 / 栅格按块展开 → 贪心装箱
  → 孤行控制（标题不与其后内容分家）→ 稀疏页回并 → 生成续页 → 重排页码
再把结果写回文件，避免源码正则与 DOM 结构对不上的问题。

用法：
  python paginate.py <html 文件> [--check|--report] [--safety N] [--rounds N]
  --check    只报告哪些版面超页，不修改文件
  --report   输出每个版面的逐块高度明细（定位「谁占了一页」）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# 说明：JS 在 window.load 之后执行，确保图片具备真实布局高度。
JS_CORE = r"""
  var MM = 96 / 25.4, PAGE_H = 296 * MM, SAFETY = window.__SAFETY__ || 10;
  var COLS = { GRID2: 2, GRID3: 3, GRID4: 4 };
  var HEADINGS = { H1: 1, H2: 1, H3: 1, H4: 1 };
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function hasCls(c, n) { return (' ' + String(c.className) + ' ').indexOf(' ' + n + ' ') >= 0; }
  function secs() { return Array.prototype.slice.call(document.querySelectorAll('.page')); }
  function px(v) { return parseFloat(v) || 0; }
  function out(obj) {
    var old = document.getElementById('PAGEROUT');
    if (old) old.remove();
    var d = document.createElement('div');
    d.id = 'PAGEROUT';
    d.textContent = JSON.stringify(obj);
    document.body.appendChild(d);
  }
  function metrics() {
    var list = secs();
    if (!list.length) return null;
    var ref = list.filter(function (s) { return !hasCls(s, 'cover'); })[0] || list[0];
    var cs = getComputedStyle(ref);
    return {
      list: list,
      padTop: px(cs.paddingTop),
      padBottom: px(cs.paddingBottom),
      cap: PAGE_H - px(cs.paddingTop) - px(cs.paddingBottom) - SAFETY
    };
  }
  // 块流模型：每个直接子元素的占位 = max(前块 margin-bottom, 自身 margin-top) + 自身高度
  function itemsOf(sec) {
    var kids = Array.prototype.slice.call(sec.children).filter(function (c) {
      return !hasCls(c, 'ftr');
    });
    var items = [];
    kids.forEach(function (c) {
      var cs = getComputedStyle(c), r = c.getBoundingClientRect();
      var mt = px(cs.marginTop), mb = px(cs.marginBottom);
      if (c.tagName === 'HR' || c.tagName === 'BR') { mt = mb = 0; }
      items.push({
        el: c, h: r.height, mt: mt, mb: mb,
        label: c.tagName.toLowerCase() + (c.className ? '.' + String(c.className).split(' ')[0] : '')
      });
    });
    return items;
  }
  function gapOf(prev, it) { return prev ? Math.max(prev.mb, it.mt) : it.mt; }
  function flowH(items) {
    var acc = 0, prev = null;
    items.forEach(function (it) { acc += gapOf(prev, it) + it.h; prev = it; });
    return acc;
  }
  // 读取一个版面的直接子块：拆出页眉，标记标题，并把表格展开成可拆的行单元
  function readItems(sec) {
    var all = itemsOf(sec);
    var hdr = (all.length && hasCls(all[0].el, 'hdr')) ? all.shift() : null;
    all.forEach(function (it) {
      it.head = (HEADINGS[it.el.tagName] || hasCls(it.el, 'kicker')) ? 1 : 0;
      it.unit = null;
      var el = it.el, cs = getComputedStyle(el);
      if (el.tagName === 'TABLE' && el.tBodies && el.tBodies[0] && el.tBodies[0].rows.length >= 2) {
        it.unit = {
          kind: 'table', headH: el.tHead ? el.tHead.getBoundingClientRect().height : 0, rowGap: 0,
          parts: Array.prototype.slice.call(el.tBodies[0].rows).map(function (r) {
            return { nodes: [r], h: r.getBoundingClientRect().height };
          })
        };
      } else if (COLS[el.tagName] && el.children.length >= 2) {
        var rowsP = [], key = null;
        Array.prototype.slice.call(el.children).forEach(function (c) {
          var r = c.getBoundingClientRect();
          if (key === null || Math.abs(r.top - key) > 3) { key = r.top; rowsP.push({ top: r.top, nodes: [c], h: r.height }); }
          else { var g = rowsP[rowsP.length - 1]; g.nodes.push(c); g.h = Math.max(g.h, r.height); }
        });
        it.unit = { kind: 'grid', headH: 0, rowGap: px(cs.rowGap) || 0, parts: rowsP };
      }
    });
    return { hdr: hdr, items: all };
  }
"""

JS_SPLIT = JS_CORE + r"""
  var m = metrics();
  if (!m) { out({ error: 'no .page found' }); return; }
  var CAP = m.cap;
  var log = [];

  // 一组块在页面上占用的总高（含页眉，块流 margin 合并模型）
  function groupH(hdr, grp) {
    var acc = hdr ? hdr.h + hdr.mb : 0, prev = null;
    grp.forEach(function (it) {
      acc += (prev ? Math.max(prev.mb, it.mt) : it.mt) + it.h;
      prev = it;
    });
    return acc;
  }

  // 把可拆块（表格 / 栅格）的 parts[from,to) 装进一个同构容器，返回新元素
  function makeChunk(piece) {
    var src = piece.src, unit = src.unit, orig = src.el;
    var wrap = orig.cloneNode(unit.kind === 'table');
    if (unit.kind === 'table') {
      var nb = wrap.tBodies[0];
      while (nb.rows.length) nb.deleteRow(0);
    } else {
      while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
    }
    for (var i = piece.from; i < piece.to; i++) {
      unit.parts[i].nodes.forEach(function (n) { wrap.appendChild(n); });
    }
    return wrap;
  }

  // 装箱：逐个块放入，空间不够就换页；可拆块按行/按栅格行填满剩余空间
  function packInto(hdr, items, capX) {
    var hdrCost = hdr ? hdr.h + hdr.mb : 0;
    var groups = [], cur = [], used = hdrCost, prev = null;
    function close() { if (cur.length) groups.push(cur); cur = []; used = hdrCost; prev = null; }
    items.forEach(function (src) {
      if (!src.unit) {
        var it = { el: src.el, h: src.h, mt: src.mt, mb: src.mb, head: src.head };
        if (cur.length && used + Math.max(prev.mb, it.mt) + it.h > capX) close();
        cur.push(it); used += (prev ? Math.max(prev.mb, it.mt) : it.mt) + it.h; prev = it;
        return;
      }
      var parts = src.unit.parts, i = 0;
      while (i < parts.length) {
        var base = used + (prev ? Math.max(prev.mb, src.mt) : src.mt);
        var h = src.unit.headH + 2, j = i, room = capX - base;
        while (j < parts.length) {
          var add = parts[j].h + (j > i ? src.unit.rowGap : 0);
          if (h + add + (j === parts.length - 1 ? src.mb : 0) > room) break;
          h += add; j++;
        }
        if (j === i) {
          if (cur.length) { close(); continue; }
          h += parts[i].h; j = i + 1;
        }
        var piece = { el: null, h: h, mt: src.mt, mb: src.mb, head: 0, src: src, from: i, to: j };
        cur.push(piece);
        used = base + h + (j === parts.length ? src.mb : 0);
        prev = piece;
        i = j;
        if (i < parts.length) close();
      }
    });
    close();
    return groups;
  }

  function isWhole(p) { return !p.src || (p.from === 0 && p.to === p.src.unit.parts.length); }

  // 同一张表的两个相邻碎片若能合回一页，合并为一张表（避免 1 行孤表）
  function mergeChunks(groups, capX) {
    for (var g = groups.length - 1; g >= 1; g--) {
      var a = groups[g - 1], b = groups[g];
      if (!a.length || !b.length) continue;
      var p = a[a.length - 1], q = b[0];
      if (!p.src || p.src !== q.src || p.to !== q.from) continue;
      var sum = p.h + q.h - p.src.unit.headH - 2;
      if (sum > capX) continue;
      a.pop(); b.shift();
      a.push({ el: null, h: sum, mt: p.mt, mb: q.mb, head: 0, src: p.src, from: p.from, to: q.to });
      if (!b.length) groups.splice(g, 1);
    }
    return groups;
  }

  m.list.forEach(function (sec) {
    if (hasCls(sec, 'cover')) return;
    var st = readItems(sec);
    var hdr = st.hdr, items = st.items;
    if (!items.length) return;
    var total = groupH(hdr, items);
    if (total <= CAP) return;

    // 先按页数均分目标高度，避免“满页 + 大半空页”的两极分布
    var n = Math.ceil(total / CAP);
    var groups = mergeChunks(packInto(hdr, items, CAP), CAP);
    if (groupH(hdr, groups[groups.length - 1]) < CAP * 0.62 && n > 1) {
      var capX = Math.max(total / n, CAP * 0.8);
      var g2 = mergeChunks(packInto(hdr, items, capX), capX);
      if (g2.length <= groups.length) groups = g2;
    }

    // 稀疏页回并：从上一页尾部借整块（不拆表），避免大半空页
    var MIN = CAP * 0.6;
    for (var k = groups.length - 1; k >= 1; k--) {
      if (groupH(hdr, groups[k]) >= MIN) continue;
      var src = groups[k - 1];
      while (src.length > 1) {
        var take = src[src.length - 1];
        if (!isWhole(take)) break;
        if (groupH(hdr, [take].concat(groups[k])) > CAP) break;
        var rest = groupH(hdr, src.slice(0, src.length - 1));
        if (rest < MIN && src.length > 2) break;
        groups[k].unshift(src.pop());
      }
    }

    // 孤行控制：页尾不能只留标题，标题必须与其后第一块内容同页
    for (var g2i = groups.length - 1; g2i >= 1; g2i--) {
      var grp = groups[g2i - 1];
      while (grp.length > 1 && grp[grp.length - 1].head) {
        var moved = grp.pop();
        if (groupH(hdr, [moved].concat(groups[g2i])) > CAP) { grp.push(moved); break; }
        groups[g2i].unshift(moved);
      }
    }

    groups = groups.filter(function (x) { return x.length; });
    if (groups.length < 2) return;

    // 物化：先搭模板，再清空原版面，按组重建 / 新增续页版面
    var tplHdr = hdr ? hdr.el.cloneNode(true) : null;
    var tplFtr = sec.querySelector('.ftr');
    tplFtr = tplFtr ? tplFtr.cloneNode(true) : null;
    groups.forEach(function (grp) {
      grp.forEach(function (p) { if (p.src) p.el = makeChunk(p); });
    });
    function fill(section, grp, cont) {
      while (section.firstChild) section.removeChild(section.firstChild);
      if (tplHdr) {
        var nh = tplHdr.cloneNode(true);
        if (cont && nh.children[1]) {
          nh.children[1].innerHTML = String(nh.children[1].innerHTML)
            .replace(/(\s*\u00b7\s*\u7eed)+$/, '') + ' \u00b7 \u7eed';
        }
        section.appendChild(nh);
      }
      grp.forEach(function (p) { section.appendChild(p.el); });
      if (tplFtr) {
        var nf = tplFtr.cloneNode(true);
        if (nf.children[1]) nf.children[1].textContent = '00 / 00';
        section.appendChild(nf);
      }
    }
    fill(sec, groups[0], false);
    var anchor = sec;
    for (var jj = 1; jj < groups.length; jj++) {
      var ns = document.createElement('section');
      ns.className = 'page' + (hasCls(sec, 'page--alt') ? ' page--alt' : '');
      anchor.parentNode.insertBefore(ns, anchor.nextSibling);
      anchor = ns;
      fill(ns, groups[jj], true);
    }
    log.push({ parts: groups.length, need: Math.round(total) });
  });

  var all = secs();
  all.forEach(function (sec, i) {
    var f = sec.querySelector('.ftr');
    if (f && f.children[1]) f.children[1].textContent = pad(i + 1) + ' / ' + pad(all.length);
  });
  var s = document.getElementById('__pager__');
  if (s) s.remove();
  out({ total: all.length, cap: Math.round(CAP), log: log });
"""

# ─────────────────────────────────────────────────────────────────────────────
# flow 模式：把全书内容当作一条连续块流做全局装箱（跨版面重排），
# 页眉取「本页第一个内容块所属章节」并自动标注「· 续」。用于消除
# 「版面内容 = 1.1~1.5 页」必然产生的半空页。
# ─────────────────────────────────────────────────────────────────────────────
JS_FLOW = JS_CORE + r"""
  var m = metrics();
  if (!m) { out({ error: 'no .page found' }); return; }
  var CAP = m.cap, list = m.list;
  var stream = [], coverSec = null, ftrTpl = null, defLeft = '', defRight = '';

  // 取页眉文案：先剔除源文件里已手写的「· 续 / (CONT.)」后缀，避免二次叠加
  function cleanLbl(s) {
    s = String(s == null ? '' : s);
    s = s.replace(/\s*\(\s*CONT\.\s*\)\s*$/i, '');
    s = s.replace(/(\s*\u00b7\s*(\u7eed|CONT\.))+$/i, '');
    return s.replace(/\s+$/, '');
  }

  list.forEach(function (sec) {
    if (hasCls(sec, 'cover')) { coverSec = sec; return; }
    var st = readItems(sec), hd = st.hdr;
    var ch = { tpl: hd ? hd.el : null, cost: hd ? hd.h + hd.mb : 0, left: '', right: '' };
    if (ch.tpl) {
      ch.left = cleanLbl(ch.tpl.children[0] ? ch.tpl.children[0].innerHTML : '');
      ch.right = cleanLbl(ch.tpl.children[1] ? ch.tpl.children[1].innerHTML : '');
      if (!defLeft) { defLeft = ch.left; defRight = ch.right; }
    }
    if (!ftrTpl) { var f = sec.querySelector('.ftr'); if (f) ftrTpl = f.cloneNode(true); }
    st.items.forEach(function (it, idx) {
      it.start = idx === 0 ? 1 : 0;
      it.ch = ch;
      stream.push(it);
    });
  });
  if (!stream.length) { out({ error: 'empty flow' }); return; }

  function gapOf2(prev, it) { return prev ? Math.max(prev.mb, it.mt) : it.mt; }

  // 贪心装箱：普通块整块放，表格按行拆；剩余行 <=2 时放宽到 CAP 并页，避免孤行表
  function pack(capX) {
    var res = [], cur = null;
    function open(ch) { cur = { ch: ch, items: [], used: ch.cost, prev: null }; res.push(cur); }
    stream.forEach(function (it) {
      if (!cur) open(it.ch);
      if (!it.unit) {
        var need = gapOf2(cur.prev, it) + it.h;
        if (cur.items.length && cur.used + need > capX) { open(it.ch); need = it.mt + it.h; }
        cur.items.push({ it: it, h: it.h });
        cur.used += need; cur.prev = it;
        return;
      }
      var parts = it.unit.parts, i = 0;
      while (i < parts.length) {
        var base = cur.used + gapOf2(cur.prev, it);
        var h = it.unit.headH + 2, j = i;
        while (j < parts.length) {
          var add = parts[j].h + (j > i ? it.unit.rowGap : 0);
          if (h + add + (j === parts.length - 1 ? it.mb : 0) > capX - base) break;
          h += add; j++;
        }
        if (j < parts.length && parts.length - j <= 2) {
          var h2 = h, j2 = j;
          while (j2 < parts.length) {
            var add2 = parts[j2].h + (j2 > i ? it.unit.rowGap : 0);
            if (h2 + add2 + (j2 === parts.length - 1 ? it.mb : 0) > CAP - base) break;
            h2 += add2; j2++;
          }
          if (j2 === parts.length) { h = h2; j = j2; }
        }
        if (j === i) {
          if (cur.items.length) { open(it.ch); continue; }
          h += parts[i].h; j = i + 1;
        }
        cur.items.push({ it: it, h: h, from: i, to: j });
        cur.used = base + h + (j === parts.length ? it.mb : 0);
        cur.prev = it;
        i = j;
        if (i < parts.length) open(it.ch);
      }
    });
    return res;
  }

  function recompute(p) {
    p.ch = p.items[0].it.ch;
    p.cont = p.items[0].it.start ? 0 : 1;
    var acc = p.ch.cost, prev = null;
    p.items.forEach(function (x) {
      var it = x.it;
      acc += (prev ? Math.max(prev.mb, it.mt) : it.mt) + x.h;
      if (x.to !== undefined && x.to === it.unit.parts.length) acc += it.mb;
      prev = it;
    });
    p.used = acc;
  }

  var pages = pack(CAP);
  pages.forEach(function (p) { recompute(p); });
  // 均分重排：把总高摊到每页，避免「满页 + 半空页」
  for (var t = 0; t < 6; t++) {
    var usedAll = 0;
    pages.forEach(function (p) { usedAll += p.used; });
    var capX = usedAll / pages.length;
    if (capX >= CAP * 0.9) break;
    var cand = pack(Math.min(CAP, Math.max(capX, CAP * 0.72)));
    if (cand.length > pages.length) break;
    pages = cand;
    pages.forEach(function (p) { recompute(p); });
  }
  // 孤行控制：页尾不能只留标题（标题必须与其后第一块同页）
  for (var g = pages.length - 1; g >= 1; g--) {
    var a = pages[g - 1], b = pages[g];
    while (a.items.length > 1 && a.items[a.items.length - 1].it.head) {
      var mv = a.items.pop();
      b.items.unshift(mv);
      recompute(a); recompute(b);
      if (b.used > CAP) { b.items.shift(); a.items.push(mv); recompute(a); recompute(b); break; }
    }
  }
  // 末页过空：把前页尾部整块顺移下来均摊（前页保持 >=0.75 页）
  for (var r = 0; r < 6; r++) {
    var last = pages[pages.length - 1];
    if (pages.length < 2 || last.used >= CAP * 0.5) break;
    var prevP = pages[pages.length - 2], moved = 0;
    while (prevP.items.length > 1) {
      var take = prevP.items[prevP.items.length - 1];
      if (take.to !== undefined) break;
      if (last.used + Math.max(0, take.it.mt) + take.h > CAP) break;
      if (prevP.used - take.h < CAP * 0.75) break;
      last.items.unshift(prevP.items.pop());
      recompute(prevP); recompute(last); moved = 1;
    }
    if (!moved) break;
    if (last.used >= CAP * 0.5) break;
  }

  // 物化
  function makeChunk2(x) {
    var orig = x.it.el, unit = x.it.unit;
    if (x.from === 0 && x.to === unit.parts.length) return orig;
    var wrap = unit.kind === 'table' ? orig.cloneNode(true) : orig.cloneNode(false);
    if (unit.kind === 'table') {
      var nb = wrap.tBodies[0];
      while (nb.rows.length) nb.deleteRow(0);
    } else {
      while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
    }
    for (var i = x.from; i < x.to; i++) {
      unit.parts[i].nodes.forEach(function (n) { wrap.appendChild(n); });
    }
    return wrap;
  }
  var built = [];
  pages.forEach(function (p) {
    var sec = document.createElement('section');
    sec.className = 'page' + (hasCls(p.items[0].it.el.parentNode, 'page--alt') ? ' page--alt' : '');
    if (p.ch.cost || p.ch.tpl) {
      // 运行页眉：取本页首个内容块所属章节。印刷品惯例里页眉本身即表示“续”，不再加标记
      var nh = document.createElement('div');
      nh.className = 'hdr';
      var t1 = document.createElement('span');
      t1.innerHTML = p.ch.left || defLeft;
      var t2 = document.createElement('span');
      t2.innerHTML = p.ch.right || defRight;
      nh.appendChild(t1); nh.appendChild(t2);
      sec.appendChild(nh);
    }
    p.items.forEach(function (x) { sec.appendChild(x.to !== undefined ? makeChunk2(x) : x.it.el); });
    if (ftrTpl) sec.appendChild(ftrTpl.cloneNode(true));
    built.push(sec);
  });
  var anchor = coverSec ? coverSec.nextSibling : list[0];
  built.forEach(function (s) { document.body.insertBefore(s, anchor); });
  list.forEach(function (sec) { if (!hasCls(sec, 'cover')) sec.parentNode.removeChild(sec); });

  var all = secs();
  all.forEach(function (sec, i) {
    var f = sec.querySelector('.ftr');
    if (f && f.children[1]) f.children[1].textContent = pad(i + 1) + ' / ' + pad(all.length);
  });
  var s2 = document.getElementById('__pager__');
  if (s2) s2.remove();
  out({
    total: all.length, cap: Math.round(CAP),
    log: pages.map(function (p, i) { return { parts: 1, need: Math.round(p.used), fill: Math.round(p.used / CAP * 100) }; })
  });
"""

JS_CHECK = JS_CORE + r"""
  var m = metrics();
  if (!m) { out({ error: 'no .page found' }); return; }
  var over = [];
  m.list.forEach(function (sec, i) {
    if (hasCls(sec, 'cover')) return;
    var items = itemsOf(sec);
    var h = flowH(items);
    var real = sec.scrollHeight - m.padTop - m.padBottom;
    var need = h;
    if (need > m.cap) over.push({ page: i + 1, need: Math.round(need), dom: Math.round(real), cap: Math.round(m.cap) });
  });
  out({ total: m.list.length, cap: Math.round(m.cap), over: over });
"""

JS_REPORT = JS_CORE + r"""
  var m = metrics();
  if (!m) { out({ error: 'no .page found' }); return; }
  var pages = [];
  m.list.forEach(function (sec, i) {
    if (hasCls(sec, 'cover')) return;
    var items = itemsOf(sec), rows = [], prev = null;
    items.forEach(function (it) {
      var g = prev ? Math.max(prev.mb, it.mt) : it.mt;
      rows.push(it.label + ' ' + Math.round(it.h) + '(+' + Math.round(g) + ')');
      prev = it;
    });
    var flow = flowH(items);
    pages.push({ page: i + 1, flow: Math.round(flow), dom: Math.round(sec.scrollHeight - m.padTop - m.padBottom), rows: rows });
  });
  out({ total: m.list.length, cap: Math.round(m.cap), pages: pages });
"""


def find_chrome(explicit: str | None) -> str:
    for c in ([explicit] if explicit else CHROME_CANDIDATES):
        if c and Path(c).exists():
            return c
    sys.exit("未找到 Chrome，请用 --chrome 指定路径")


def run(path: Path, chrome: str, js: str, safety: int = 10) -> tuple[dict, str | None]:
    """把 JS 注入到临时页面，在 load 事件后执行，返回 PAGEROUT 与（可选）新 body。"""
    path = path.resolve()
    src = path.read_text(encoding="utf-8")
    body = re.search(r'(?s)<body[^>]*>(.*)</body>', src)
    head = re.search(r"(?s)<head.*?</head>", src)
    if not body or not head:
        sys.exit("文件格式不符：需要 <head> 与 <body>")
    # 隐藏滚动条：否则测量视口宽度比打印宽度小 ~15px，内容会偏高
    probe = ('<style id="__pageno__">html,body{overflow:hidden !important}'
             '::-webkit-scrollbar{width:0 !important;height:0 !important;display:none !important}</style>')
    err_catch = ("catch(e){var d=document.createElement('div');d.id='PAGEROUT';"
                 "d.textContent=JSON.stringify({error:'JS: '+(e&&e.stack?String(e.stack):String(e))});"
                 "document.body.appendChild(d);}")
    page = (
        "<!DOCTYPE html><html lang=\"zh-CN\">"
        + head.group(0).replace("</head>", probe + "</head>")
        + "<body>" + body.group(1)
        + f'<script>window.__SAFETY__={safety};</script>'
        + f'<script id="__pager__">window.addEventListener("load", function(){{try{{{js}}}{err_catch}}});</script>'
        + "</body></html>"
    )
    tmp = path.parent / (path.stem + ".__pagetmp__.html")
    tmp.write_text(page, encoding="utf-8")
    try:
        proc = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--window-size=794,1400", "--virtual-time-budget=30000",
             "--dump-dom", tmp.as_uri()],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
    finally:
        tmp.unlink(missing_ok=True)
    mm = re.search(r'id="PAGEROUT">(.*?)</div>', proc.stdout, re.S)
    if not mm:
        sys.exit("执行失败：未取回 PAGEROUT\n" + proc.stderr[-1500:])
    info = json.loads(mm.group(1))
    if info.get("error"):
        sys.exit(info["error"])
    if info.get("log"):
        b = re.search(r'(?s)<body[^>]*>(.*)</body>', proc.stdout)
        inner = b.group(1)
        inner = re.sub(r'(?s)<div id="PAGEROUT">.*?</div>', '', inner)
        inner = re.sub(r'(?s)<script id="__pager__">.*?</script>', '', inner)
        inner = re.sub(r'(?s)<script>window\.__SAFETY__=[^<]*</script>', '', inner)
        return info, inner.strip()
    return info, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--chrome")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--safety", type=int, default=10,
                    help="每页预留的安全余量(px)，抵消打印时的换行推挤")
    ap.add_argument("--flow", action="store_true",
                    help="全局流式装箱：跨版面重排内容，消除半空页（页眉按章节运行并自动标「续」）")
    args = ap.parse_args()

    chrome = find_chrome(args.chrome)
    path = Path(args.html).resolve()

    if args.check:
        info, _ = run(path, chrome, JS_CHECK, args.safety)
        print("[check] 版面", info["total"], "· 单页内容可用高", info["cap"], "px")
        for o in info["over"]:
            print(f"  超页：第 {o['page']} 版面 需 {o['need']}px > {o['cap']}px（DOM {o['dom']}）")
        if not info["over"]:
            print("  全部适配")
        return

    if args.report:
        info, _ = run(path, chrome, JS_REPORT, args.safety)
        print("[report] 版面", info["total"], "· 可用高", info["cap"], "px")
        for p in info["pages"]:
            print(f"  #{p['page']:02d} flow={p['flow']:5d} dom={p['dom']:5d}  " + " | ".join(p["rows"]))
        return

    for rnd in range(1, args.rounds + 1):
        info, inner = run(path, chrome, JS_FLOW if args.flow else JS_SPLIT, args.safety)
        if not inner:
            print(f"[paginate] OK：全部版面适配 A4，共 {info['total']} 页（cap {info['cap']}px）")
            return
        src = path.read_text(encoding="utf-8")
        new_src = re.sub(r'(?s)(<body[^>]*>).*(</body>)',
                         lambda mo: mo.group(1) + "\n" + inner + "\n" + mo.group(2),
                         src, count=1)
        path.write_text(new_src, encoding="utf-8")
        print(f"[paginate] round {rnd}: 拆分 {[x['parts'] for x in info['log']]} -> 共 {info['total']} 页")
        if args.flow:
            fills = [x.get('fill', 0) for x in info['log']]
            print(f"[paginate] 页填充率 min/mean/max = {min(fills)}%/{sum(fills)//len(fills)}%/{max(fills)}%")

    info, _ = run(path, chrome, JS_CHECK, args.safety)
    print("[paginate] 复检超页：", info["over"] or "无")


if __name__ == "__main__":
    main()
