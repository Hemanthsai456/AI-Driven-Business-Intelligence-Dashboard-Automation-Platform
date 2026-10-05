import json
import math

rows = [
  {"department": "Aids", "marks": 72.17},
  {"department": "Civil", "marks": 72.18},
  {"department": "Cse", "marks": 71.98},
  {"department": "Ece", "marks": 73.11},
  {"department": "Eee", "marks": 72.09},
  {"department": "MECH", "marks": 72.78}
]

colors = ["#58A6FF", "#3FB950", "#D29922", "#F85149", "#A371F7", "#2F7F7A"]

def render_donut_svg(rows, is_donut=True):
    total = sum(r["marks"] for r in rows) or 1
    cx = 140
    height = 240
    cy = height / 2
    r = min(cx, cy) - 25
    inner_r = r * 0.55 if is_donut else 0
    
    start_angle = -math.pi / 2
    slices = []
    
    for i, row in enumerate(rows):
        val = row["marks"]
        slice_angle = (val / total) * 2 * math.pi
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
            d = f"M {x1:.1f} {y1:.1f} A {r:.1f} {r:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} L {ix1:.1f} {iy1:.1f} A {inner_r:.1f} {inner_r:.1f} 0 {large_arc} 0 {ix2:.1f} {iy2:.1f} Z"
        else:
            d = f"M {cx} {cy} L {x1:.1f} {y1:.1f} A {r:.1f} {r:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} Z"
            
        slices.append(f'<path d="{d}" fill="{color}" stroke="#161B22" stroke-width="1.5" />')
        start_angle = end_angle
        
    svg = f'<svg viewBox="0 0 280 {height}" width="260" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(slices)}</svg>'
    return svg

html_page = f"""<!DOCTYPE html>
<html>
<head><title>Test Donut</title></head>
<body style="background:#0D1117; padding:20px; color:#fff;">
<h2>Generated Donut</h2>
{render_donut_svg(rows, is_donut=True)}
</body>
</html>
"""

with open("scratch/test_donut_render.html", "w") as f:
    f.write(html_page)

print("Saved scratch/test_donut_render.html")
