"""Deterministic HTML/SVG scene compiler. No LLM markup or coordinates."""
from __future__ import annotations

import html
import json
import math
import re

from app.services.studio.storyboard import Scene, Storyboard
from app.services.studio.code_layout import code_pages

THEMES = {
    "google": ("#F6F8F7", "#14365D", "#4F8CFF", "#FFFFFF"),
    "apple": ("#F5F5F7", "#1D1D1F", "#0071E3", "#FFFFFF"),
    "microsoft": ("#F4F7FB", "#14365D", "#0078D4", "#FFFFFF"),
    "nvidia": ("#101810", "#F2F8EE", "#76B900", "#1B271B"),
}
ROLES = {"input": "#4F8CFF", "output": "#49A574", "intermediate": "#D79A2F", "warning": "#D95F58"}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def label(x, y, w, h, text, *, css="node-label") -> str:
    return (f'<foreignObject x="{round(x)}" y="{round(y)}" width="{round(w)}" height="{round(h)}">'
            f'<div xmlns="http://www.w3.org/1999/xhtml" data-safe="{css}" class="{css}"><span>{esc(text)}</span></div></foreignObject>')


def box(x, y, w, h, text, role="input", step=0) -> str:
    color = ROLES.get(role, ROLES["input"])
    return (f'<g data-reveal="{step}"><rect data-node-boundary="true" x="{x}" y="{y}" width="{w}" height="{h}" rx="18" '
            f'fill="var(--panel)" stroke="{color}" stroke-width="3"/>'
            + label(x + 12, y + 8, w - 24, h - 16, text) + '</g>')


def connector(x1, y1, x2, y2, text="", step=0, label_rect=None, marker_id="arrow") -> str:
    # Label sits in a reserved band ABOVE a horizontal connector, or to its
    # side for vertical edges. A panel background also protects diagonal edges.
    vertical = abs(y2 - y1) > 20
    lx = (x1 + x2) / 2 + 12 if vertical else (x1 + x2) / 2 - 95
    ly = (y1 + y2) / 2 - 28 if vertical else (y1 + y2) / 2 - 125
    if label_rect:
        lx, ly = label_rect[:2]
    badge = label(lx, ly, 190, 56, text, css="edge-label") if text else ""
    leader = ""
    if text and label_rect:
        mx, my = (x1+x2)/2, (y1+y2)/2
        # A label may use another free band on the canvas. Preserve its
        # association with this edge instead of leaving detached text.
        ax, ay = max(lx, min(mx, lx+190)), max(ly, min(my, ly+56))
        if (ax-mx)**2+(ay-my)**2 > 30**2:
            leader = (f'<path data-label-leader="true" d="M {round(ax)} {round(ay)} L {round(mx)} {round(my)}" '
                      'fill="none" stroke="#65788C" stroke-width="1.5" stroke-dasharray="4 5"/>')
    return (f'<g data-reveal="{step}"><path d="M {round(x1)} {round(y1)} L {round(x2)} {round(y2)}" '
            f'fill="none" stroke="#65788C" stroke-width="3" marker-end="url(#{marker_id})"/>{leader}{badge}'
            f'<circle data-packet="{step}" data-x1="{round(x1)}" data-y1="{round(y1)}" data-x2="{round(x2)}" data-y2="{round(y2)}" r="8" fill="#4F8CFF"/></g>')


def allocate_label(x1, y1, x2, y2, width, height, obstacles):
    """Reserve a deterministic connector label slot outside all node/label bounds."""
    mx, my = (x1+x2)/2, (y1+y2)/2
    candidates = [(mx-95,my-125),(mx-95,my+69),(mx+12,my-28),(mx-202,my-28),(mx-95,my-28)]
    candidates += [(mx+dx,my+dy) for dy in (-210,-150,-90,45,105,165) for dx in (-300,-95,110)]
    def available(x, y):
        return (5 <= x <= width-195 and 5 <= y <= height-61
                and not any(x < bx+bw+6 and x+190 > bx-6 and y < by+bh+6 and y+56 > by-6 for bx,by,bw,bh in obstacles))
    for x,y in candidates:
        rect = (round(x),round(y),190,56)
        if available(rect[0], rect[1]):
            obstacles.append(rect)
            return rect
    # The local offsets above are only a fast path. They are not proof that a
    # diagram is full. Search free bands around obstacle boundaries and across
    # the canvas, retaining the same readable label size and collision padding.
    xs = {5, width-195, *range(5, width-194, 20)}
    ys = {5, height-61, *range(5, height-60, 20)}
    for bx, by, bw, bh in obstacles:
        xs.update((math.floor(bx-196), math.ceil(bx+bw+6)))
        ys.update((math.floor(by-62), math.ceil(by+bh+6)))
    slots = [(x,y) for y in sorted(ys) for x in sorted(xs) if available(x,y)]
    if slots:
        x,y = min(slots, key=lambda p: ((p[0]+95-mx)**2+(p[1]+28-my)**2, p[1], p[0]))
        rect = (x,y,190,56)
        obstacles.append(rect)
        return rect
    raise ValueError("No safe space for connector label; shorten labels or split the diagram")


def _matrix(scene: Scene, portrait: bool) -> str:
    size = 62 if portrait else 60
    positions = [(30, 90), (400, 90), (200, 510)] if portrait else [(20, 110), (420, 110), (820, 110)]
    symbols = [scene.visual_spec.matrix_a, scene.visual_spec.matrix_b, []]
    result = []
    for m, (x, y) in enumerate(positions):
        name, role = [("A", "input"), ("B", "intermediate"), ("C", "output")][m]
        result.append(label(x, y - 70, 240, 64, name, css="matrix-name"))
        dimension = 4 if scene.visual_type == "matrix_tiling" else 3
        values = symbols[m] or [[f"{name.lower()}{i+1}{j+1}" for j in range(dimension)] for i in range(dimension)]
        for i, row in enumerate(values):
            for j, value in enumerate(row):
                active = (i < 2 and j < 2) if scene.visual_type == "matrix_tiling" else ((m == 0 and i == 0) or (m == 1 and j == 0) or (m == 2 and i == j == 0))
                fill = ROLES[role] if active else "var(--panel)"
                step = m if active else 0
                result.append(f'<g data-reveal="{step}"><rect x="{x+j*size}" y="{y+i*size}" width="{size-3}" height="{size-3}" rx="5" fill="{fill}" stroke="#65788C"/>'
                              + label(x+j*size+2, y+i*size+2, size-7, size-7, value, css="cell-label active" if active else "cell-label") + '</g>')
    equation = scene.visual_spec.equation or ("Cᵢⱼ += Aᵢₖ Bₖⱼ · block GEMM" if scene.visual_type == "matrix_tiling" else "Cᵢⱼ = Σₖ Aᵢₖ Bₖⱼ")
    if scene.visual_type == "matrix_dot_product":
        result.append(f'<g data-reveal="2">{label(20,350 if portrait else 340,720 if portrait else 1120,80,"aᵢ₁b₁ⱼ + aᵢ₂b₂ⱼ + …",css="equation")}</g>')
    result.append(f'<g data-reveal="3">{label(20, 780 if portrait else 460, 720 if portrait else 1120, 100, equation, css="equation")}</g>')
    return "".join(result)


def diagram(scene: Scene, portrait: bool, *, code_page: int | None = None) -> str:
    width, height = (800, 900) if portrait else (1180, 650)
    kind = scene.visual_type
    if kind.startswith("matrix_"):
        content = _matrix(scene, portrait)
    elif kind == "code_execution":
        pages = code_pages(scene.visual_spec.code, portrait)
        selected = list(enumerate(pages)) if code_page is None else [(code_page, pages[code_page])]
        parts = []
        for local_page, (page_index, rows) in enumerate(selected):
            heading = f"Code · {page_index+1}/{len(pages)}"
            if rows:
                heading += f" · L{rows[0].source_line}–{rows[-1].source_line}"
            lines = []
            for i, row in enumerate(rows):
                number = "↳" if row.continuation else str(row.source_line)
                lines.append(f'<foreignObject x="20" y="{70+i*44}" width="{width-40}" height="44">'
                             '<div xmlns="http://www.w3.org/1999/xhtml" class="code-row">'
                             f'<span class="code-number" data-safe="code-number">{number}</span>'
                             f'<pre data-safe="code" class="code-line">{esc(row.text or " ")}</pre></div></foreignObject>')
            parts.append(f'<g data-code-page="{local_page}" style="display:{"none" if local_page else "inline"}">'
                         + label(20,10,width-40,40,heading,css="code-heading") + ''.join(lines) + '</g>')
        content = ''.join(parts)
    else:
        nodes = scene.visual_spec.nodes
        if not nodes:
            from app.services.studio.plan_schema import VisualNode
            nodes = [VisualNode(id=f"n{i}", label=text) for i, text in enumerate(scene.labels[:6])]
        n = len(nodes)
        coords = {}
        tree = kind in {"hierarchy", "reduction_tree", "broadcast_tree", "algorithm_tree"}
        grid = kind in {"network_topology", "process_grid", "architecture", "collective_communication"}
        bw, bh = (230, 112) if portrait else (270, 112)
        if tree:
            # Four portrait leaves require narrow nodes. Give their wrapped
            # labels three readable lines rather than shrinking the font.
            if portrait:
                bh = 144
                row_counts = [min(2**level,n-(2**level-1)) for level in range(int(math.log2(n))+1)] if n else [1]
                bw = min(230, math.floor(width/max(row_counts))-30)
            levels = int(math.log2(n)) if n else 0
            usable_height = height-100 if scene.visual_spec.equation else height-5
            level_gap = min(245, (usable_height-45-bh)/max(1,levels))
            for i, node in enumerate(nodes):
                level = int(math.log2(i + 1))
                offset = i - (2**level - 1)
                row_count = min(2**level,n-(2**level-1)) if portrait else 2**level
                coords[node.id] = ((offset + 0.5) * width / row_count - bw/2, 45 + level * level_gap)
            if n > 7:
                raise ValueError("Tree scene supports at most 7 nodes; split the explanation")
        elif kind == "memory_hierarchy":
            for i, node in enumerate(nodes):
                coords[node.id] = (50, 30 + i * 160)
            bw = width - 100
            bh = 80
            if n > (5 if portrait else 4):
                raise ValueError("Split memory hierarchy into fewer levels")
        elif kind == "process_grid":
            cols = math.ceil(math.sqrt(n)) if n else 1
            bw = (width-100)/cols-30
            bh = 135 if portrait else 110
            for i,node in enumerate(nodes):
                row,col = divmod(i,cols)
                coords[node.id] = (50+col*(bw+30),130+row*(bh+90))
        elif kind in {"queue", "pipeline", "data_path", "flow", "cycle", "auto"}:
            cols = 2 if portrait else 3
            for i, node in enumerate(nodes):
                row, col = divmod(i, cols)
                coords[node.id] = (35 + col * (width-70) / cols, 130 + row * (230 if portrait else 260))
        elif kind in {"timeline", "resource_timeline"}:
            bw = width - 200
            bh = 85
            for i, node in enumerate(nodes):
                coords[node.id] = (110, 20 + i * 125)
            if n > (6 if portrait else 4):
                raise ValueError("Timeline too dense; split the scene")
        else:
            cols = 2 if portrait or not grid else 3
            for i, node in enumerate(nodes):
                row, col = divmod(i, cols)
                coords[node.id] = (30 + col * width / cols, 130 + row * 240)
        parts = []
        obstacles = [(x,y,bw,bh) for x,y in coords.values()]
        if any(x < 0 or y < 0 or x+bw > width or y+bh > height for x,y in coords.values()):
            raise ValueError("Diagram too dense for this aspect ratio; split nodes across scenes")
        if scene.visual_spec.equation:
            equation_rect = (10,height-85,width-20,80)
            if any(y+bh > equation_rect[1] and x < width-10 and x+bw > 10 for x,y in coords.values()):
                raise ValueError("Diagram nodes occupy the equation band; split nodes across scenes")
            obstacles.append(equation_rect)
        # Render connectors before nodes; endpoints terminate at the boundary.
        for i, edge in enumerate(scene.visual_spec.edges):
            sx, sy = coords[edge.source]; tx, ty = coords[edge.target]
            if abs(ty-sy) > 50:
                x1, y1, x2, y2 = sx+bw/2, sy+(bh if ty>sy else 0), tx+bw/2, ty+(0 if ty>sy else bh)
            else:
                x1, y1, x2, y2 = sx+(bw if tx>sx else 0), sy+bh/2, tx+(0 if tx>sx else bw), ty+bh/2
            slot = allocate_label(x1,y1,x2,y2,width,height,obstacles) if edge.label else None
            parts.append(connector(x1,y1,x2,y2,edge.label,step=min(i+1,len(scene.animation_steps)-1),label_rect=slot,marker_id=f"arrow_{scene.id}"))
        for i, node in enumerate(nodes):
            x,y = coords[node.id]
            if y+bh > height:
                raise ValueError("Diagram too dense for this aspect ratio; split nodes across scenes")
            parts.append(box(round(x),round(y),bw,bh,node.label,node.role,step=min(i,len(scene.animation_steps)-1)))
            if kind in {"timeline", "resource_timeline"}:
                # Equal-width schematic bars show ordering, never invented benchmark times.
                parts.append(label(0,y,95,bh,f"{i+1:02d}",css="matrix-name"))
                parts.append(f'<g data-reveal="{min(i,len(scene.animation_steps)-1)}"><rect x="{round(x)}" y="{round(y+bh-12)}" width="{bw}" height="8" fill="#E7ECEA"/><rect data-progress-bar="{i}" data-max-width="{bw}" x="{round(x)}" y="{round(y+bh-12)}" height="8" width="0" fill="{ROLES[node.role]}"/></g>')
        if scene.visual_spec.equation:
            parts.append(label(10,height-85,width-20,80,scene.visual_spec.equation,css="equation"))
        content = ''.join(parts)
    return (f'<svg class="diagram" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(scene.learning_goal or scene.topic)}">'
            f'<defs><marker id="arrow_{scene.id}" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,3 L0,6" fill="#65788C"/></marker></defs>' + content + '</svg>')


def render_html(storyboard: Storyboard, theme: str = "google", *, video: bool = False) -> str:
    v = storyboard.video
    portrait = v.aspectRatio == "9:16"
    palette = THEMES.get(theme, THEMES["google"])
    bg, ink, accent, panel = palette
    scale = v.width / (1080 if portrait else 1920)
    markup = []
    # PDF/slide HTML shows every code page as a separate sheet. Video retains
    # one semantic scene and one narration file, switching code pages in place.
    views = []
    for scene in storyboard.scenes:
        pages = code_pages(scene.visual_spec.code, portrait) if scene.visual_type == "code_execution" else [[]]
        if not video and len(pages) > 1:
            views.extend((scene.model_copy(update={"id": f"{scene.id}_code_{i+1:02d}"}), i, 1) for i in range(len(pages)))
        else:
            views.append((scene, None, len(pages)))
    for i, (scene, code_page, page_count) in enumerate(views):
        try:
            visual = diagram(scene, portrait, code_page=code_page)
        except ValueError as exc:
            raise ValueError(f"{scene.id} ({scene.topic}): {exc}") from exc
        points = ''.join(f'<li data-safe="point">{esc(p)}</li>' for p in scene.points)
        markup.append(f'<section class="scene" data-scene="{i}" data-code-pages="{page_count}" data-steps="{len(scene.animation_steps)}">'
                      f'<header><div class="eyebrow" data-safe="eyebrow">{i+1:02d} / {len(views):02d} · {esc(scene.grounding)}</div>'
                      f'<h1 data-safe="title">{esc(scene.topic)}</h1></header>'
                      f'<main><div class="visual">{visual}</div><aside><ul>{points}</ul></aside></main>'
                      '<footer><div class="caption" data-safe="caption"></div>'
                      f'<div class="metadata" data-safe="metadata">{esc(" · ".join(scene.source_refs))}</div></footer></section>')
    # Escaping < protects script boundaries even if source narration includes HTML.
    display_board = {**storyboard.model_dump(), "scenes": [scene.model_dump() for scene, _, _ in views]}
    data = json.dumps(display_board, ensure_ascii=False).replace('<', '\\u003c')
    css = f"""
    *{{box-sizing:border-box}}html,body{{margin:0;background:{bg};color:{ink};font-family:'DejaVu Sans',Arial,sans-serif}}
    :root{{--panel:{panel};--accent:{accent}}}
    .scene{{width:{v.width}px;height:{v.height}px;padding:{round(70*scale)}px {round((60 if portrait else 90)*scale)}px {round((90 if portrait else 40)*scale)}px;
      padding-right:{round((150 if portrait else 90)*scale)}px;display:grid;grid-template-rows:{'17% 61% 22%' if portrait else '21% 63% 16%'};overflow:hidden;break-after:page}}
    header,main,aside,.visual,footer{{min-width:0;min-height:0;overflow:hidden}}
    .eyebrow{{font-size:{round(22*scale)}px;letter-spacing:3px;line-height:1.4;max-height:{round(36*scale)}px;overflow:hidden;color:{accent}}}
    h1{{font-size:{round((55 if portrait else 60)*scale)}px;line-height:1.15;font-weight:650;max-height:{round(140*scale)}px;max-width:100%;margin:{round(18*scale)}px 0;overflow:hidden;overflow-wrap:anywhere}}
    main{{display:flex;flex-direction:{'column' if portrait else 'row'};gap:{round(40*scale)}px}}
    .visual{{flex:{'0 0 76%' if portrait else '1 1 70%'};display:flex;align-items:center}}
    .diagram{{display:block;width:100%;height:100%;overflow:hidden}}
    aside{{flex:1;display:flex;align-items:center}}ul{{list-style:none;margin:0;padding:0;width:100%;overflow:hidden}}
    li{{font-size:{round((30 if portrait else 32)*scale)}px;line-height:1.4;max-height:{round((92 if portrait else 140)*scale)}px;overflow:hidden;overflow-wrap:anywhere;margin:0 0 {round(20*scale)}px;border-left:4px solid {accent};padding-left:{round(20*scale)}px}}
    footer{{border-top:1px solid #65788C;padding-top:{round(22*scale)}px;display:grid;grid-template-rows:1fr {round(40*scale)}px;gap:{round(12*scale)}px}}
    .caption{{font-size:{round((34 if portrait else 29)*scale)}px;line-height:1.4;max-width:100%;height:100%;overflow:hidden;overflow-wrap:anywhere}}
    .metadata{{font-size:{round(19*scale)}px;line-height:1.4;max-height:{round(35*scale)}px;overflow:hidden;color:#65788C}}
    .node-label,.edge-label,.cell-label,.equation,.matrix-name{{height:100%;width:100%;display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.25;overflow:hidden;overflow-wrap:anywhere;font-size:29px;padding:4px;color:{ink}}}
    .node-label>span,.edge-label>span,.cell-label>span,.equation>span,.matrix-name>span{{display:block;min-width:0;max-width:100%;overflow-wrap:anywhere}}
    .edge-label{{background:var(--panel);font-size:{26 if portrait else 21}px;border-radius:6px}}.cell-label{{font-size:{24 if portrait else 20}px}}.active{{color:#102236}}.equation{{font-size:{42 if portrait else 40}px}}.matrix-name{{font-size:36px;font-weight:bold}}
    .code-heading{{height:100%;width:100%;font-size:22px;line-height:1.4;overflow:hidden;color:#65788C}}
    .code-row{{height:100%;width:100%;display:grid;grid-template-columns:52px minmax(0,1fr);overflow:hidden}}
    .code-number{{font:20px/44px 'DejaVu Sans Mono',monospace;color:#65788C;overflow:hidden;text-align:right;padding-right:12px}}
    .code-line{{height:100%;width:100%;min-width:0;margin:0;font:26px/44px 'DejaVu Sans Mono',monospace;overflow:hidden;white-space:pre}}
    @page{{size:{v.width}px {v.height}px;margin:0}}
    @media print{{.scene{{break-inside:avoid;print-color-adjust:exact}}}}
    """
    script = """
    const board=__DATA__;
    window.studioSceneViews=board.scenes.map((scene,index)=>({id:scene.id,codePages:Number(document.querySelector('[data-scene="'+index+'"]').dataset.codePages)}));
    window.seekScene=(index,progress=1)=>{
      for(const scene of document.querySelectorAll('[data-scene]')){
        const active=Number(scene.dataset.scene)===index;
        scene.style.display=active?'grid':'none';
        if(!active)continue;
        const codePage=Math.min(Number(scene.dataset.codePages)-1,Math.floor(Math.max(0,progress)*Number(scene.dataset.codePages)));
        scene.querySelectorAll('[data-code-page]').forEach(el=>el.style.display=Number(el.dataset.codePage)===codePage?'inline':'none');
        const count=Number(scene.dataset.steps), stage=Math.min(count-1,Math.floor(Math.max(0,progress)*count));
        scene.querySelectorAll('[data-reveal]').forEach(el=>el.style.opacity=Number(el.dataset.reveal)<=stage?'1':'0');
        scene.querySelectorAll('[data-packet]').forEach(el=>{
          const step=Number(el.dataset.packet),p=Math.max(0,Math.min(1,progress*count-step));
          el.setAttribute('cx',Math.round(Number(el.dataset.x1)+(Number(el.dataset.x2)-Number(el.dataset.x1))*p));
          el.setAttribute('cy',Math.round(Number(el.dataset.y1)+(Number(el.dataset.y2)-Number(el.dataset.y1))*p));
          el.style.opacity=p>0&&p<1?'1':'0';
        });
        scene.querySelectorAll('[data-progress-bar]').forEach(el=>{
          const p=Math.max(0,Math.min(1,progress*count-Number(el.dataset.progressBar)));
          el.setAttribute('width',Math.round(Number(el.dataset.maxWidth)*p));
        });
        const chunks=(board.scenes[index].narration.match(/[^.!?。]+[.!?。]?/g)||[]).flatMap(sentence=>{
          const words=sentence.trim().split(/\\s+/),out=[];let part='';
          for(const word of words){if((part+' '+word).length>85){out.push(part);part=word}else part+=(part?' ':'')+word}
          if(part)out.push(part);return out;
        });
        scene.querySelector('.caption').textContent=__VIDEO__?(chunks[Math.min(chunks.length-1,Math.floor(progress*chunks.length))]||''):board.scenes[index].key_message;
      }
    };
    window.inspectLayout=()=>{
      const errors=[];
      const elements=[...document.querySelectorAll('[data-safe]')].filter(el=>el.getBoundingClientRect().width>0);
      for(const el of elements){
        const r=el.getBoundingClientRect();
        if(el.scrollWidth>el.clientWidth+1||el.scrollHeight>el.clientHeight+1)errors.push('overflow: '+el.dataset.safe+': '+el.textContent);
        const scene=el.closest('.scene'),footer=scene.querySelector('footer').getBoundingClientRect(),main=scene.querySelector('main').getBoundingClientRect();
        if(el.closest('main')&&(r.bottom>main.bottom+1||r.right>main.right+1||r.top<main.top-1||r.left<main.left-1))errors.push('outside content: '+el.textContent);
        if(el.closest('main')&&r.bottom>footer.top)errors.push('caption collision: '+el.textContent);
        if(el.dataset.safe==='edge-label')for(const box of el.closest('svg').querySelectorAll('[data-node-boundary]')){
          const b=box.getBoundingClientRect();
          if(r.left<b.right-2&&r.right>b.left+2&&r.top<b.bottom-2&&r.bottom>b.top+2)errors.push('connector label overlaps node: '+el.textContent);
        }
      }
      const labels=elements.filter(el=>['node-label','edge-label','equation'].includes(el.dataset.safe));
      for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){
        const a=labels[i].getBoundingClientRect(),b=labels[j].getBoundingClientRect();
        if(a.left<b.right-2&&a.right>b.left+2&&a.top<b.bottom-2&&a.bottom>b.top+2)errors.push('label overlap: '+labels[i].textContent+' / '+labels[j].textContent);
      }
      return errors;
    };
    if(__VIDEO__){window.seekScene(0,0);
      // The exported HTML player follows actual audio.currentTime, not a second clock.
      const audio=new Audio();let index=0,playing=false;
      window.playVideo=async()=>{if(playing){audio.pause();playing=false;return}if(!audio.src){audio.src='narration/'+board.scenes[index].id+'.mp3'}await audio.play();playing=true;requestAnimationFrame(tick)};
      audio.onended=async()=>{if(index<board.scenes.length-1){index++;audio.src='narration/'+board.scenes[index].id+'.mp3';await audio.play();requestAnimationFrame(tick)}else{playing=false;index=0;audio.src=''}};
      function tick(){window.seekScene(index,Math.min(1,audio.currentTime/(board.scenes[index].duration||1)));if(playing&&!audio.paused)requestAnimationFrame(tick)}
      const button=document.createElement('button');button.textContent='▶ / ⏸';button.setAttribute('aria-label','Play or pause narration');button.style.cssText='position:fixed;left:8px;bottom:8px;z-index:2';button.onclick=()=>window.playVideo();document.body.append(button);
    }else{
      document.querySelectorAll('[data-packet]').forEach(el=>el.style.opacity='0');
      document.querySelectorAll('[data-progress-bar]').forEach(el=>el.setAttribute('width',el.dataset.maxWidth));
      document.querySelectorAll('[data-scene]').forEach(el=>el.querySelector('.caption').textContent=board.scenes[Number(el.dataset.scene)].key_message);
    }
    """.replace('__DATA__', data).replace('__VIDEO__', 'true' if video else 'false')
    return f'<!doctype html><html lang="{v.language}"><head><meta charset="utf-8"><title>{esc(v.title)}</title><style>{css}</style></head><body>{"".join(markup)}<script>{script}</script></body></html>'
