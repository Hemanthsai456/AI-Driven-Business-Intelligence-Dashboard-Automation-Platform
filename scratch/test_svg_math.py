import math

def generate_donut_svg(rows, dim_key="department", metric_key="marks", is_donut=True, width=320, height=220):
    if not rows:
        return "<svg></svg>"
        
    values = [max(0, float(r.get(metric_key, 0))) for r in rows]
    total = sum(values) or 1.0
    
    colors = ["#2F7F7A", "#5B7C99", "#C9A66B", "#B56576", "#9AA5B1", "#4E878C", "#D4A373", "#E07A5F"]
    
    cx = width / 2
    cy = height / 2
    r = min(cx, cy) - 15
    inner_r = r * 0.55 if is_donut else 0
    
    slices = []
    legend_items = []
    
    # If single slice (100%)
    if len(rows) == 1 or total <= 0:
        val = values[0] if values else 0
        dim_label = str(rows[0].get(dim_key, "Total")) if rows else "Total"
        color = colors[0]
        if is_donut:
            d = f"M {cx} {cy - r} A {r} {r} 0 1 1 {cx} {cy + r} A {r} {r} 0 1 1 {cx} {cy - r} M {cx} {cy - inner_r} A {inner_r} {inner_r} 0 1 0 {cx} {cy + inner_r} A {inner_r} {inner_r} 0 1 0 {cx} {cy - inner_r} Z"
            slices.append(f'<path d="{d}" fill="{color}" fill-rule="evenodd" />')
        else:
            slices.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" />')
            
        legend_items.append(f'<div style="display:flex;align-items:center;gap:6px;font-size:11px;"><span style="width:10px;height:10px;background:{color};border-radius:2px;"></span><span>{dim_label}</span><span style="margin-left:auto;font-family:monospace;">100%</span></div>')
    else:
        start_angle = -math.pi / 2
        for i, row in enumerate(rows[:8]):
            val = values[i]
            slice_angle = (val / total) * 2 * math.pi
            if slice_angle < 0.005:
                continue
            end_angle = start_angle + slice_angle
            color = colors[i % len(colors)]
            
            x1 = cx + r * math.cos(start_angle)
            y1 = cy + r * math.sin(start_angle)
            x2 = cx + r * math.cos(end_angle)
            y2 = cy + r * math.sin(end_angle)
            large_arc = 1 if slice_angle > math.pi else 0
            
            if inner_r > 0:
                ix1 = cx + inner_r * math.cos(end_angle)
                iy1 = cy + inner_r * math.sin(end_angle)
                ix2 = cx + inner_r * math.cos(start_angle)
                iy2 = cy + inner_r * math.sin(start_angle)
                d = f"M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f} L {ix1:.2f} {iy1:.2f} A {inner_r:.2f} {inner_r:.2f} 0 {large_arc} 0 {ix2:.2f} {iy2:.2f} Z"
            else:
                d = f"M {cx:.2f} {cy:.2f} L {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z"
                
            slices.append(f'<path d="{d}" fill="{color}" stroke="var(--surface, #161B22)" stroke-width="1.5" />')
            
            dim_label = str(row.get(dim_key, f"Item {i+1}"))
            pct = int(round((val / total) * 100))
            legend_items.append(f'<div style="display:flex;align-items:center;gap:6px;font-size:11px;margin-bottom:4px;"><span style="width:10px;height:10px;background:{color};border-radius:2px;flex-shrink:0;"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:140px;">{dim_label}</span><span style="margin-left:auto;font-family:monospace;color:var(--muted,#8B949E);">{pct}%</span></div>')
            start_angle = end_angle

    svg_content = f'''
    <div style="display:flex;align-items:center;justify-content:center;gap:16px;width:100%;flex-wrap:wrap;padding:8px 0;">
      <svg viewBox="0 0 {width} {height}" style="width:240px;max-height:220px;flex-shrink:0;" xmlns="http://www.w3.org/2000/svg">
        {''.join(slices)}
      </svg>
      <div style="flex:1;min-width:140px;max-width:260px;">
        {''.join(legend_items)}
      </div>
    </div>
    '''
    return svg_content

rows = [
  {"department": "Aids", "marks": 72.17},
  {"department": "Civil", "marks": 72.18},
  {"department": "Cse", "marks": 71.98},
  {"department": "Ece", "marks": 73.11},
  {"department": "Eee", "marks": 72.09},
  {"department": "MECH", "marks": 72.78}
]

res = generate_donut_svg(rows)
print("SVG Generated successfully, length:", len(res))
with open("scratch/verified_donut.html", "w") as f:
    f.write(f"<!DOCTYPE html><html><body style='background:#161B22; color:#fff;'>{res}</body></html>")
print("Saved scratch/verified_donut.html")
