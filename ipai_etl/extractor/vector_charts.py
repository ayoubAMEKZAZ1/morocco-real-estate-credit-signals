"""Low-level geometry of the IPAI bar charts.

Bars are read as vector rectangles in the PDF (exact heights, not an image). charts.py calibrates
them against the y-axis tick labels and reads the full window of quarters shown in each bulletin.
"""
from collections import Counter


def get_bar_groups(page, region_bbox, gap_threshold=1.2, min_height=1.0):
    """region_bbox = (x0, top0, x1, top1). Return (groups, baseline_top), where groups is a list
    of lists of rectangles (sorted by x0), one list per quarter, and baseline_top is the bars'
    shared bottom (the x axis, value 0)."""
    x0b, top0b, x1b, top1b = region_bbox
    rects = [r for r in page.rects
             if top0b <= r["top"] and r["bottom"] <= top1b and x0b <= r["x0"] <= x1b]
    if not rects:
        return [], None
    # Several 'bottom' values can appear if the region slightly overlaps the chart above it.
    # Keep only groups large enough to be a real set of bars (at least 10, i.e. 2-3 years of
    # quarters) and take the LOWEST one: the target chart is the first complete block below its
    # title, and its axis sits below any leftover of the chart above.
    bottom_counts = Counter(round(r["bottom"], 1) for r in rects if r["height"] > min_height)
    if not bottom_counts:
        return [], None
    plausible = [b for b, n in bottom_counts.items() if n >= 10]
    baseline = max(plausible) if plausible else bottom_counts.most_common(1)[0][0]
    bars = [r for r in rects if abs(r["bottom"] - baseline) < 1.0 and r["height"] > min_height]
    if not bars:
        return [], baseline
    bars.sort(key=lambda r: r["x0"])
    groups = [[bars[0]]]
    for b in bars[1:]:
        if b["x0"] - groups[-1][-1]["x1"] > gap_threshold:
            groups.append([b])
        else:
            groups[-1].append(b)
    return groups, baseline


def get_horizontal_gridlines(page, region_bbox, bars_x0):
    """Find the 'top' positions of the y-axis ticks from the horizontal gridlines (dotted or
    solid) that cross the chart to the left of the first bar. Return (tops, axis_x), where axis_x
    is the chart frame's left edge, used to place the tick-label reading."""
    x0b, top0b, x1b, top1b = region_bbox
    candidates = [l for l in page.lines
                  if top0b - 2 <= l["top"] <= top1b + 2 and l["x0"] < bars_x0 and (l["x1"] - l["x0"]) > 50]
    if not candidates:
        return [], None
    axis_x = min(round(l["x0"], 1) for l in candidates)
    tops = sorted({round(l["top"], 1) for l in candidates if abs(l["x0"] - axis_x) < 3})
    return _keep_uniform_run(tops), axis_x


def _keep_uniform_run(tops, tol=0.35):
    """Ticks on one axis are evenly spaced. If the search box overlaps a neighbouring chart, a few
    foreign gridlines with a different spacing can slip in. Keep the longest run of consecutive
    points with the regular spacing (almost always the target chart's ticks)."""
    if len(tops) < 3:
        return tops
    diffs = [round(tops[i + 1] - tops[i], 1) for i in range(len(tops) - 1)]
    counts = Counter(round(d) for d in diffs)          # most frequent spacing, to within 1 pt
    mode_bucket = counts.most_common(1)[0][0]
    candidate_diffs = [d for d in diffs if round(d) == mode_bucket]
    step = sum(candidate_diffs) / len(candidate_diffs)

    best_run = [tops[0]]
    cur_run = [tops[0]]
    for i in range(1, len(tops)):
        if abs((tops[i] - cur_run[-1]) - step) <= tol * step:
            cur_run.append(tops[i])
        else:
            if len(cur_run) > len(best_run):
                best_run = cur_run
            cur_run = [tops[i]]
    if len(cur_run) > len(best_run):
        best_run = cur_run
    return best_run
