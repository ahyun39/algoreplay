"""GitHub-style contribution grid ("잔디") rendered as plain HTML/CSS from per-day counts."""
from datetime import timedelta

GRASS_COLORS = ["rgba(128,128,128,0.15)", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


def grass_level(attempts):
    return 0 if attempts == 0 else 1 if attempts == 1 else 2 if attempts <= 3 else 3 if attempts <= 5 else 4


def grass_html(act, weeks=53):
    """GitHub-style contribution grid: one column per week (Sun→Sat), one cell per day."""
    today = act["today"]
    start = today - timedelta(days=(today.weekday() + 1) % 7 + 7 * (weeks - 1))  # Sunday, `weeks` weeks ago
    cells, months = [], []
    for w in range(weeks):
        week_start = start + timedelta(days=7 * w)
        first_of_month = next((week_start + timedelta(days=i) for i in range(7)
                               if (week_start + timedelta(days=i)).day == 1), None)
        label = f"{first_of_month.month}월" if first_of_month and w < weeks - 1 else ""
        months.append(f'<span style="grid-column:{w + 1}">{label}</span>')
        for i in range(7):
            day = week_start + timedelta(days=i)
            if day > today:
                cells.append('<i style="visibility:hidden"></i>')
                continue
            stat = act["days"].get(day, {"attempts": 0, "passed": 0})
            tip = f"{day.isoformat()} · " + (f"{stat['attempts']}회 풀이 · 통과 {stat['passed']}" if stat["attempts"]
                                             else "기록 없음")
            cells.append(f'<i title="{tip}" style="background:{GRASS_COLORS[grass_level(stat["attempts"])]}"></i>')
    legend = "".join(f'<i style="background:{c}"></i>' for c in GRASS_COLORS)
    return f"""<div style="overflow-x:auto;padding-bottom:4px">
<style>.grass i{{display:block;width:11px;height:11px;border-radius:2px}}</style>
<div class="grass" style="display:inline-grid;grid-template-columns:auto auto;gap:4px 6px;font-size:11px;opacity:.95">
  <span></span>
  <div style="display:grid;grid-template-columns:repeat({weeks},11px);column-gap:3px;white-space:nowrap">{"".join(months)}</div>
  <div style="display:grid;grid-template-rows:repeat(7,11px);row-gap:3px;line-height:11px">
    <span></span><span>월</span><span></span><span>수</span><span></span><span>금</span><span></span></div>
  <div style="display:grid;grid-template-rows:repeat(7,11px);grid-auto-flow:column;grid-auto-columns:11px;gap:3px">
    {"".join(cells)}</div>
  <span></span>
  <div style="display:flex;gap:3px;align-items:center;justify-content:flex-end">적음 {legend} 많음</div>
</div></div>"""
