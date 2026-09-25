#!/usr/bin/env python3
"""
Rebuild the standalone index.html by inlining dashboard-data.json into
dashboard.html. Run this after regenerating dashboard-data.json so the
presentation copy (index.html) stays in sync and still needs no server
or network access to run -- just double-click it in any browser.

Usage (from the repo root):
    python3 tools/build_index.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard.html"
DATA = ROOT / "dashboard-data.json"
OUT = ROOT / "index.html"

FETCH_BLOCK = '''  fetch("dashboard-data.json").then(function(r){ return r.json(); }).then(function(data){
    DATA = data;
    render();
  }).catch(function(err){
    document.getElementById("kpi-grid").innerHTML = '<div class="kpi"><div class="label">Data failed to load</div><div class="sub">'+esc(err.message)+'</div></div>';
  });'''

REPLACEMENT = '''  setTimeout(function(){
    try {
      DATA = window.__EMBEDDED_DATA__;
      if(!DATA) throw new Error("embedded data missing");
      render();
    } catch(err) {
      document.getElementById("kpi-grid").innerHTML = '<div class="kpi"><div class="label">Data failed to load</div><div class="sub">'+esc(err.message)+'</div></div>';
    }
  }, 0);'''

MARKER = "<script>\n(function(){"


def main():
    html = SRC.read_text(encoding="utf-8")
    data = DATA.read_text(encoding="utf-8")
    json.loads(data)  # validate

    if FETCH_BLOCK not in html:
        sys.exit("build_index.py: fetch block not found in dashboard.html -- "
                 "did the loader code change? Update FETCH_BLOCK to match.")
    html = html.replace(FETCH_BLOCK, REPLACEMENT)

    if MARKER not in html:
        sys.exit("build_index.py: main <script> marker not found in dashboard.html")
    data_script = "<script>\nwindow.__EMBEDDED_DATA__ = " + data.strip() + ";\n</script>\n"
    html = html.replace(MARKER, data_script + MARKER, 1)

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
