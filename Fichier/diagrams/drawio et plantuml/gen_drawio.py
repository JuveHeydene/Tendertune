#!/usr/bin/env python3
"""Génère l'architecture technique en .drawio (géométrie explicite) + un aperçu PNG
rendu depuis le MÊME modèle, pour vérifier la lisibilité avant livraison."""
import html
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# --------------------------------------------------------------- palette
PAL = {
    "ui":     ("#DCE9F7", "#2E5F8A", "#123449"),
    "api":    ("#D6E4F0", "#1F4E79", "#10314D"),
    "orch":   ("#E8DCEF", "#6B3E86", "#3A1D4D"),
    "trait":  ("#DDEBD3", "#4B7A32", "#274318"),
    "model":  ("#F7DBE0", "#A83A50", "#5C1A26"),
    "store":  ("#CFE8F8", "#1B7FB0", "#123449"),
    "store2": ("#E4EDC9", "#6C8B2A", "#33420F"),
    "store3": ("#FBE7C6", "#B5822A", "#5A3F10"),
    "store4": ("#F2DCD2", "#B25B2E", "#5C2E14"),
    "bus":    ("#EFEFEF", "#5A6472", "#2C333D"),
    "gpu":    ("#EDE3F5", "#6B3E86", "#3A1D4D"),
}
BAND = {
    "ui":    ("#2E5F8A", "#FFFFFF"),
    "api":   ("#1F4E79", "#FFFFFF"),
    "orch":  ("#6B3E86", "#FFFFFF"),
    "trait": ("#4B7A32", "#FFFFFF"),
    "store": ("#1B7FB0", "#FFFFFF"),
}


class Model:
    def __init__(self, w, h, title):
        self.W, self.H, self.title = w, h, title
        self.nodes = []   # dict(id,x,y,w,h,label,sub,kind,shape)
        self.edges = []   # dict(src,dst,label,style,points,exit,entry)
        self.groups = []  # dict(x,y,w,h,label)

    def node(self, nid, x, y, w, h, label, sub="", kind="ui", shape="rect"):
        self.nodes.append(dict(id=nid, x=x, y=y, w=w, h=h, label=label,
                               sub=sub, kind=kind, shape=shape))
        return nid

    def band(self, nid, x, y, w, label, kind, h=32):
        self.nodes.append(dict(id=nid, x=x, y=y, w=w, h=h, label=label,
                               sub="", kind=kind, shape="band"))
        return nid

    def edge(self, src, dst, label="", dashed=False, points=None,
             exit=None, entry=None, color="#4A5A72"):
        self.edges.append(dict(src=src, dst=dst, label=label, dashed=dashed,
                               points=points or [], exit=exit, entry=entry,
                               color=color))

    def get(self, nid):
        for n in self.nodes:
            if n["id"] == nid:
                return n
        raise KeyError(nid)

    # ------------------------------------------------------------ aperçu
    def preview(self, path, scale=1):
        img = Image.new("RGB", (int(self.W * scale), int(self.H * scale)), "white")
        d = ImageDraw.Draw(img)
        f_t = ImageFont.truetype(FONTB, int(15 * scale))
        f_b = ImageFont.truetype(FONTB, int(11 * scale))
        f_s = ImageFont.truetype(FONT, int(9 * scale))
        f_e = ImageFont.truetype(FONT, int(9 * scale))

        d.text((self.W * scale / 2, 14 * scale), self.title, fill="#1F2F55",
               font=f_t, anchor="mm")

        for g in self.groups:
            d.rounded_rectangle([g["x"] * scale, g["y"] * scale,
                                 (g["x"] + g["w"]) * scale, (g["y"] + g["h"]) * scale],
                                radius=6 * scale, outline="#9AA5B1", width=1)
            d.text(((g["x"] + 10) * scale, (g["y"] + 11) * scale), g["label"],
                   fill="#5A6472", font=f_s, anchor="lm")

        for n in self.nodes:
            x, y, w, h = [v * scale for v in (n["x"], n["y"], n["w"], n["h"])]
            if n["shape"] == "band":
                bg, fg = BAND[n["kind"]]
                d.rounded_rectangle([x, y, x + w, y + h], radius=4 * scale, fill=bg)
                d.text((x + 12 * scale, y + h / 2), n["label"], fill=fg, font=f_b,
                       anchor="lm")
                continue
            fill, stroke, fc = PAL[n["kind"]]
            if n["shape"] == "cyl":
                ry = 7 * scale
                d.ellipse([x, y, x + w, y + 2 * ry], fill=fill, outline=stroke)
                d.rectangle([x, y + ry, x + w, y + h - ry], fill=fill, outline=None)
                d.line([x, y + ry, x, y + h - ry], fill=stroke)
                d.line([x + w, y + ry, x + w, y + h - ry], fill=stroke)
                d.ellipse([x, y + h - 2 * ry, x + w, y + h], fill=fill, outline=stroke)
            elif n["shape"] == "hex":
                c = 12 * scale
                d.polygon([(x + c, y), (x + w - c, y), (x + w, y + h / 2),
                           (x + w - c, y + h), (x + c, y + h), (x, y + h / 2)],
                          fill=fill, outline=stroke)
            elif n["shape"] == "tape":
                d.rounded_rectangle([x, y, x + w, y + h], radius=3 * scale,
                                    fill=fill, outline=stroke)
            elif n["shape"] == "text":
                pass
            else:
                d.rounded_rectangle([x, y, x + w, y + h], radius=4 * scale,
                                    fill=fill, outline=stroke)
            cy = y + h / 2 - (6 * scale if n["sub"] else 0)
            d.text((x + w / 2, cy), n["label"], fill=fc, font=f_b, anchor="mm")
            if n["sub"]:
                for i, line in enumerate(n["sub"].split("\n")):
                    d.text((x + w / 2, cy + (11 + 10 * i) * scale), line,
                           fill="#5A6472", font=f_s, anchor="mm")

        for e in self.edges:
            pts = self._route(e)
            pts = [(p[0] * scale, p[1] * scale) for p in pts]
            for i in range(len(pts) - 1):
                d.line([pts[i], pts[i + 1]], fill=e["color"], width=max(1, int(1.6 * scale)))
            ex, ey = pts[-1]
            px, py = pts[-2]
            dx, dy = ex - px, ey - py
            n = max((dx * dx + dy * dy) ** .5, 1e-6)
            ux, uy = dx / n, dy / n
            s = 5 * scale
            d.polygon([(ex, ey), (ex - s * ux + s * .6 * uy, ey - s * uy - s * .6 * ux),
                       (ex - s * ux - s * .6 * uy, ey - s * uy + s * .6 * ux)],
                      fill=e["color"])
            if e["label"]:
                mid = pts[len(pts) // 2]
                d.text((mid[0] + 5 * scale, mid[1] - 6 * scale), e["label"],
                       fill="#33465C", font=f_e, anchor="lm")
        img.save(path)
        return img.size

    def _anchor(self, n, spec):
        if spec is None:
            return None
        fx, fy = spec
        return (n["x"] + n["w"] * fx, n["y"] + n["h"] * fy)

    def _route(self, e):
        a, b = self.get(e["src"]), self.get(e["dst"])
        p0 = self._anchor(a, e["exit"]) or (a["x"] + a["w"] / 2, a["y"] + a["h"])
        p1 = self._anchor(b, e["entry"]) or (b["x"] + b["w"] / 2, b["y"])
        return [p0] + e["points"] + [p1]

    # ------------------------------------------------------------ drawio
    def drawio(self, path, name):
        def esc(s):
            return html.escape(s).replace("\n", "&#10;")
        out = ['<mxfile host="local">',
               f'  <diagram name="{esc(name)}" id="d1">',
               f'    <mxGraphModel dx="1400" dy="1200" grid="0" gridSize="10" guides="1" '
               f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
               f'pageWidth="{self.W}" pageHeight="{self.H}" background="#FFFFFF" math="0" shadow="0">',
               '      <root>', '        <mxCell id="0"/>', '        <mxCell id="1" parent="0"/>']
        out.append(f'        <mxCell id="title" value="{esc(self.title)}" '
                   f'style="text;html=1;align=center;verticalAlign=middle;fontSize=17;'
                   f'fontStyle=1;fontColor=#1F2F55;" vertex="1" parent="1">'
                   f'<mxGeometry x="0" y="8" width="{self.W}" height="26" as="geometry"/></mxCell>')
        for i, g in enumerate(self.groups):
            out.append(
                f'        <mxCell id="g{i}" value="{esc(g["label"])}" '
                f'style="rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=none;'
                f'strokeColor=#9AA5B1;dashed=1;verticalAlign=top;align=left;spacingLeft=10;'
                f'spacingTop=6;fontSize=11;fontColor=#5A6472;" vertex="1" parent="1">'
                f'<mxGeometry x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" as="geometry"/></mxCell>')
        for n in self.nodes:
            if n["shape"] == "band":
                bg, fg = BAND[n["kind"]]
                st = (f'rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor={bg};'
                      f'strokeColor=none;fontColor={fg};fontSize=13;fontStyle=1;'
                      f'align=left;spacingLeft=14;verticalAlign=middle;')
                val = n["label"]
            else:
                fill, stroke, fc = PAL[n["kind"]]
                base = f'whiteSpace=wrap;html=1;shadow=1;fillColor={fill};strokeColor={stroke};fontColor={fc};'
                if n["shape"] == "cyl":
                    st = f'shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=8;{base}fontSize=11;fontStyle=1;verticalAlign=middle;align=center;'
                elif n["shape"] == "hex":
                    st = f'shape=hexagon;perimeter=hexagonPerimeter2;{base}fontSize=11;fontStyle=1;align=center;verticalAlign=middle;'
                elif n["shape"] == "tape":
                    st = f'shape=tape;{base}fontSize=11;fontStyle=1;align=center;verticalAlign=middle;'
                elif n["shape"] == "text":
                    st = f'text;html=1;align=center;verticalAlign=middle;fontSize=11;fontColor={fc};fontStyle=2;'
                elif n["shape"] == "comp":
                    st = f'shape=module;jettyWidth=14;jettyHeight=4;{base}fontSize=11;fontStyle=1;align=center;verticalAlign=middle;spacingLeft=6;'
                else:
                    st = f'rounded=1;arcSize=8;{base}fontSize=11;fontStyle=1;align=center;verticalAlign=middle;'
                val = n["label"]
                if n["sub"]:
                    val = (f'<b>{esc(n["label"])}</b><br><font style="font-size:9px" color="#5A6472">'
                           + esc(n["sub"]).replace("&#10;", "<br>") + '</font>')
                    out.append(
                        f'        <mxCell id="{n["id"]}" value="{val}" style="{st}html=1;" '
                        f'vertex="1" parent="1"><mxGeometry x="{n["x"]}" y="{n["y"]}" '
                        f'width="{n["w"]}" height="{n["h"]}" as="geometry"/></mxCell>')
                    continue
            out.append(
                f'        <mxCell id="{n["id"]}" value="{esc(val)}" style="{st}" '
                f'vertex="1" parent="1"><mxGeometry x="{n["x"]}" y="{n["y"]}" '
                f'width="{n["w"]}" height="{n["h"]}" as="geometry"/></mxCell>')
        for i, e in enumerate(self.edges):
            st = (f'edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;'
                  f'endSize=7;strokeWidth=1.8;strokeColor={e["color"]};fontColor=#33465C;fontSize=10;'
                  f'jumpStyle=arc;jumpSize=8;'
                  + ('dashed=1;' if e["dashed"] else ''))
            if e["exit"]:
                st += f'exitX={e["exit"][0]};exitY={e["exit"][1]};exitDx=0;exitDy=0;'
            if e["entry"]:
                st += f'entryX={e["entry"][0]};entryY={e["entry"][1]};entryDx=0;entryDy=0;'
            geo = '<mxGeometry relative="1" as="geometry">'
            if e["points"]:
                geo += '<Array as="points">' + "".join(
                    f'<mxPoint x="{p[0]}" y="{p[1]}"/>' for p in e["points"]) + '</Array>'
            geo += '</mxGeometry>'
            out.append(
                f'        <mxCell id="e{i}" value="{esc(e["label"])}" style="{st}" '
                f'edge="1" parent="1" source="{e["src"]}" target="{e["dst"]}">{geo}</mxCell>')
        out += ['      </root>', '    </mxGraphModel>', '  </diagram>', '</mxfile>', '']
        open(path, "w").write("\n".join(out))
