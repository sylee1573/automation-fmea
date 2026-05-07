#!/usr/bin/env python3
"""
표준류 자동생성 시스템 — 프로젝트 현황 대시보드 생성기
실행: python show_status.py
     또는 대시보드.bat 더블클릭
"""
import re
import webbrowser
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent


def strip_code_blocks(text):
    return re.sub(r"```[\s\S]*?```", "", text)


def clean_md(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def parse_phases():
    path = BASE / "구현계획.md"
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8")
    content = strip_code_blocks(raw)

    phases = []
    # Split on phase headers — keep the header in each section
    parts = re.split(r"(?=\n### Phase)", content)

    for part in parts:
        m = re.match(r"\n?### (Phase \d+[^\n]*)", part)
        if not m:
            continue

        title = m.group(1).strip()

        # Strip trailing section markers (e.g. "← 완료", "← **구현 완료 (…)**")
        display_title = re.sub(r"\s*←.*$", "", title).strip()
        display_title = re.sub(r"\s*\*\*.*?\*\*\s*$", "", display_title).strip()

        is_complete = "완료" in title
        is_optional = bool(re.search(r"선택.*진행|pywebview.*래핑.*선택", part[:500]))

        done = [clean_md(x) for x in re.findall(r"- \[x\] (.+)", part)]
        pending_raw = re.findall(r"- \[ \] (.+)", part)
        pending = [clean_md(x) for x in pending_raw]

        todos = []
        for a, b in re.findall(r"\[TODO-([^\]]+)\]\s*(.{5,150})", part):
            todos.append(f"[TODO-{a}] {b.rstrip()}")

        human = [x for x in pending if any(k in x for k in ["담당자", "실행 필요", "실행 필수", "품질 담당자 검토"])]
        prereq = [x for x in pending if any(k in x for k in ["사전 필수", "선행 필수"])]

        n_done = len(done)
        n_total = len(done) + len(pending)

        if is_optional:
            status = "optional"
        elif is_complete and not pending:
            status = "complete"
        elif is_complete and pending:
            # 개발 완료 선언이 있어도 담당자 실행 항목이 남아 있으면 진행중
            status = "partial"
        elif n_total > 0 and n_done == n_total:
            status = "complete"
        elif n_done > 0:
            status = "partial"
        else:
            status = "pending"

        phases.append(
            dict(
                title=display_title,
                status=status,
                done=done,
                pending=pending,
                human=human,
                prereq=prereq,
                todos=todos,
                n_done=n_done,
                n_total=n_total,
            )
        )

    return phases


# ─────────────────────────── HTML 생성 ────────────────────────────

STATUS_META = {
    "complete": ("✅", "완료", "#22c55e"),
    "partial":  ("🔄", "진행중", "#f59e0b"),
    "pending":  ("⏳", "대기중", "#64748b"),
    "optional": ("⚙️", "선택사항", "#a78bfa"),
}


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_card(p):
    icon, label, color = STATUS_META.get(p["status"], ("❓", "?", "#94a3b8"))
    pct = int(p["n_done"] / p["n_total"] * 100) if p["n_total"] else 0

    rows = []

    if p["done"]:
        for item in p["done"]:
            rows.append(f'<li class="t-done">✅ {_esc(item[:90])}{"…" if len(item)>90 else ""}</li>')

    normal_pending = [x for x in p["pending"] if x not in p["human"] and x not in p["prereq"]]
    if normal_pending:
        rows.append('<li class="sec-label">미완료 항목</li>')
        for item in normal_pending:
            rows.append(f'<li class="t-pend">🔲 {_esc(item[:90])}{"…" if len(item)>90 else ""}</li>')

    if p["prereq"]:
        rows.append('<li class="sec-label">사전 필수 확인</li>')
        for item in p["prereq"]:
            rows.append(f'<li class="t-pre">⚠️ {_esc(item[:90])}{"…" if len(item)>90 else ""}</li>')

    if p["human"]:
        rows.append('<li class="sec-label">👤 담당자 실행 필요</li>')
        for item in p["human"]:
            rows.append(f'<li class="t-human">▶ {_esc(item[:90])}{"…" if len(item)>90 else ""}</li>')

    if p["todos"]:
        rows.append('<li class="sec-label">📌 TODO 주의사항</li>')
        for item in p["todos"]:
            rows.append(f'<li class="t-todo">{_esc(item[:110])}{"…" if len(item)>110 else ""}</li>')

    task_list = "<ul class='tlist'>" + "".join(rows) + "</ul>" if rows else ""

    progress_bar = ""
    if p["n_total"]:
        progress_bar = f"""
        <div class="prog-row">
          <div class="prog-track"><div class="prog-fill" style="width:{pct}%;background:{color}"></div></div>
          <span class="prog-txt">{p['n_done']}/{p['n_total']} ({pct}%)</span>
        </div>"""

    return f"""
    <div class="card" data-status="{p['status']}">
      <div class="card-head">
        <span class="ctitle">{_esc(p['title'])}</span>
        <span class="badge" style="background:{color}18;color:{color};border:1px solid {color}40">{icon} {label}</span>
      </div>
      {progress_bar}
      {task_list}
    </div>"""


def generate_html(phases):
    now = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")

    total_tasks = sum(p["n_total"] for p in phases)
    done_tasks  = sum(p["n_done"]  for p in phases)
    pct_overall = int(done_tasks / total_tasks * 100) if total_tasks else 0

    complete_cnt = sum(1 for p in phases if p["status"] == "complete")
    inprog_cnt   = sum(1 for p in phases if p["status"] in ("partial", "pending"))
    optional_cnt = sum(1 for p in phases if p["status"] == "optional")

    # 담당자 즉시 실행 항목 요약
    action_items = []
    for p in phases:
        phase_short = p["title"].split("—")[0].strip()
        for item in p["human"]:
            action_items.append((phase_short, item))

    action_html = ""
    if action_items:
        lis = "".join(
            f'<li><span class="phase-tag">{_esc(ph)}</span> {_esc(item[:100])}{"…" if len(item)>100 else ""}</li>'
            for ph, item in action_items
        )
        action_html = f'<div class="action-box"><h2>📋 지금 당장 필요한 담당자 실행 항목</h2><ul>{lis}</ul></div>'

    cards_html = "\n".join(build_card(p) for p in phases)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>표준류 시스템 — 프로젝트 현황</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Malgun Gothic',-apple-system,sans-serif;background:#0b1120;color:#e2e8f0;padding:24px 20px;min-height:100vh}}
a{{color:inherit}}
.wrap{{max-width:1200px;margin:0 auto}}

/* Header */
.hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}}
.hdr h1{{font-size:20px;font-weight:700;color:#f8fafc}}
.hdr .sub{{font-size:12px;color:#475569;margin-top:4px}}
.hdr .ts{{font-size:11px;color:#475569;text-align:right;line-height:1.6}}

/* Stat row */
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}}
.stat{{background:#1e293b;border:1px solid #2d3f55;border-radius:12px;padding:18px;text-align:center}}
.stat .val{{font-size:30px;font-weight:700}}
.stat .lbl{{font-size:11px;color:#64748b;margin-top:3px}}

/* Overall progress */
.overall{{background:#1e293b;border:1px solid #2d3f55;border-radius:12px;padding:18px;margin-bottom:20px}}
.overall .otitle{{font-size:13px;color:#94a3b8;margin-bottom:10px}}
.otrack{{background:#0b1120;border-radius:9999px;height:18px;overflow:hidden}}
.ofill{{height:100%;background:linear-gradient(90deg,#3b82f6,#22c55e);border-radius:9999px}}
.opct{{font-size:12px;color:#64748b;margin-top:6px;text-align:right}}

/* Action box */
.action-box{{background:#1a1208;border:1px solid #f59e0b50;border-radius:12px;padding:18px;margin-bottom:20px}}
.action-box h2{{font-size:14px;color:#fbbf24;margin-bottom:10px}}
.action-box ul{{padding-left:16px}}
.action-box li{{font-size:12px;color:#d6d3d1;padding:3px 0;line-height:1.5}}
.phase-tag{{background:#334155;color:#94a3b8;font-size:10px;padding:1px 6px;border-radius:4px;margin-right:6px}}

/* Filter */
.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}}
.fb{{padding:5px 14px;border-radius:9999px;border:1px solid #334155;background:#1e293b;
     color:#94a3b8;font-size:11px;cursor:pointer;font-family:inherit;transition:.15s}}
.fb:hover,.fb.on{{background:#334155;color:#f1f5f9}}

/* Grid */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}}

/* Card */
.card{{background:#1e293b;border:1px solid #2d3f55;border-radius:12px;padding:18px;transition:.2s}}
.card:hover{{border-color:#475569}}
.card[data-status=complete]{{border-color:#22c55e28}}
.card[data-status=partial]{{border-color:#f59e0b28}}
.card[data-status=optional]{{border-color:#a78bfa28}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px}}
.ctitle{{font-size:13px;font-weight:600;color:#f1f5f9;line-height:1.4}}
.badge{{font-size:10px;font-weight:600;padding:3px 8px;border-radius:9999px;white-space:nowrap;flex-shrink:0}}

/* Progress */
.prog-row{{display:flex;align-items:center;gap:8px;margin-bottom:12px}}
.prog-track{{flex:1;background:#0b1120;border-radius:9999px;height:5px;overflow:hidden}}
.prog-fill{{height:100%;border-radius:9999px}}
.prog-txt{{font-size:10px;color:#64748b;white-space:nowrap}}

/* Task list */
.tlist{{list-style:none;font-size:11px;line-height:1.6}}
.tlist li{{padding:2px 0;border-bottom:1px solid #0b112020}}
.t-done{{color:#64748b}}
.t-pend{{color:#94a3b8}}
.t-pre{{color:#fb923c}}
.t-human{{color:#fbbf24;font-weight:500}}
.t-todo{{color:#6b7280;font-style:italic}}
.sec-label{{font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.06em;
           padding-top:8px;margin-top:4px;border-top:1px solid #334155;list-style:none}}

@media(max-width:700px){{
  .stats{{grid-template-columns:repeat(2,1fr)}}
  .grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div class="wrap">

<div class="hdr">
  <div>
    <h1>🏭 표준류 자동생성 시스템 — 프로젝트 현황</h1>
    <div class="sub">자동차 부품 제조사용 FMEA · Control Plan · 작업표준서 · 자주검사항목 자동생성</div>
  </div>
  <div class="ts">🕐 {now}<br>구현계획.md 기준 자동 분석</div>
</div>

<div class="stats">
  <div class="stat">
    <div class="val" style="color:#22c55e">{complete_cnt}</div>
    <div class="lbl">완료된 Phase</div>
  </div>
  <div class="stat">
    <div class="val" style="color:#f59e0b">{inprog_cnt}</div>
    <div class="lbl">진행중 / 대기 Phase</div>
  </div>
  <div class="stat">
    <div class="val" style="color:#3b82f6">{done_tasks}</div>
    <div class="lbl">완료 태스크</div>
  </div>
  <div class="stat">
    <div class="val" style="color:#94a3b8">{total_tasks - done_tasks}</div>
    <div class="lbl">남은 태스크</div>
  </div>
</div>

<div class="overall">
  <div class="otitle">전체 구현 진행률</div>
  <div class="otrack"><div class="ofill" style="width:{pct_overall}%"></div></div>
  <div class="opct">{done_tasks} / {total_tasks} 항목 완료 &nbsp;|&nbsp; <strong>{pct_overall}%</strong></div>
</div>

{action_html}

<div class="filters">
  <button class="fb on" onclick="filter(this,'all')">전체 보기</button>
  <button class="fb" onclick="filter(this,'complete')">✅ 완료</button>
  <button class="fb" onclick="filter(this,'partial')">🔄 진행중</button>
  <button class="fb" onclick="filter(this,'pending')">⏳ 대기중</button>
  <button class="fb" onclick="filter(this,'optional')">⚙️ 선택사항</button>
</div>

<div class="grid" id="grid">
{cards_html}
</div>

</div><!-- .wrap -->
<script>
function filter(btn, status) {{
  document.querySelectorAll('.fb').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.card').forEach(c => {{
    c.style.display = (status === 'all' || c.dataset.status === status) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


def main():
    phases = parse_phases()
    if not phases:
        print("구현계획.md 파일을 찾을 수 없거나 Phase 섹션이 없습니다.")
        return

    html = generate_html(phases)
    out = BASE / "project_dashboard.html"
    out.write_text(html, encoding="utf-8")

    print(f"[OK] 대시보드 생성: {out}")
    print(f"     Phase {len(phases)}개 분석 완료")
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
