#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册构建脚本：从 *.src.html 源版出发，自动校准分页 -> 生成 PDF -> 校验一致性。

每次尝试都从源文件重新复制一份工作版，保证分页是幂等的（不会在已拆分的基础上
反复拆分，造成「续 · 续 · 续」和空版面）。

用法：python build_pdf.py <src.html> <输出 pdf> [--safety-ladder 10,18,28,45] [--flow]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paginate as pg  # noqa: E402


def pdf_pages(pdf: Path) -> int:
    data = pdf.read_bytes()
    return len(re.findall(rb'/Type\s*/Page[^s]', data))


def make_pdf(html: Path, pdf: Path, chrome: str) -> int:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", "--virtual-time-budget=30000",
         f"--print-to-pdf={pdf}", html.resolve().as_uri()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    return pdf_pages(pdf)


def run_paginate(html: Path, chrome: str, safety: int, rounds: int = 3, flow: bool = False) -> int:
    js = pg.JS_FLOW if flow else pg.JS_SPLIT
    for _ in range(1 if flow else rounds):
        info, inner = pg.run(html, chrome, js, safety)
        if not inner:
            return info["total"]
        src = html.read_text(encoding="utf-8")
        html.write_text(re.sub(r'(?s)(<body[^>]*>).*(</body>)',
                              lambda m: m.group(1) + "\n" + inner + "\n" + m.group(2),
                              src, count=1), encoding="utf-8")
        if flow:
            return info["total"]
    info, _ = pg.run(html, chrome, pg.JS_CHECK, safety)
    return info["total"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("pdf")
    ap.add_argument("--chrome")
    ap.add_argument("--ladder", default="10,18,28,45")
    ap.add_argument("--flow", action="store_true", help="用全局流式装箱（跨版面重排）代替逐版面拆分")
    args = ap.parse_args()

    chrome = pg.find_chrome(args.chrome)
    src = Path(args.src).resolve()
    pdf = Path(args.pdf).resolve()
    work = src.with_name(src.name.replace(".src.html", ".html"))

    for safety in [int(x) for x in args.ladder.split(",")]:
        shutil.copyfile(src, work)
        total = run_paginate(work, chrome, safety, flow=args.flow)
        pages = make_pdf(work, pdf, chrome)
        print(f"[build] safety={safety}px -> 版面 {total} · PDF {pages} 页")
        if pages == total:
            info, _ = pg.run(work, chrome, pg.JS_CHECK, safety)
            print(f"[build] OK -> {pdf}（复检超页：{info['over'] or '无'}）")
            return
    print(f"[build] 警告：版面 {total} / PDF {pages} 不一致，仍有页溢出，请精简内容或加大 safety")


if __name__ == "__main__":
    main()
