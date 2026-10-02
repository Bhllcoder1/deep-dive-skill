"""Tiny Excalidraw document builder (stdlib only).

Produces valid Excalidraw v2 JSON: unique ids, seeds and versions on every element,
labels bound to their container through ``containerId`` / ``boundElements``, and arrows
bound to boxes through ``startBinding`` / ``endBinding``.
"""

import json
import zlib

PALETTE = {
    "entry":    {"stroke": "#1971c2", "bg": "#a5d8ff"},   # giriş: mavi
    "core":     {"stroke": "#2f9e44", "bg": "#b2f2bb"},   # çekirdek: yeşil
    "runtime":  {"stroke": "#e8590c", "bg": "#ffd8a8"},   # runtime: turuncu
    "external": {"stroke": "#495057", "bg": "#dee2e6"},   # dış servis: gri
    "problem":  {"stroke": "#e03131", "bg": "#ffc9c9"},   # sorun: kırmızı
    "boundary": {"stroke": "#6741d9", "bg": "transparent"},
    "plain":    {"stroke": "#1e1e1e", "bg": "transparent"},
}
FONT = 2  # Helvetica: has the Turkish glyphs (ş ğ ı İ ö ü ç) that hand-drawn Virgil lacks
CHAR_W = 0.56
LINE_H = 1.25


def text_size(text, font_size):
    lines = text.split("\n")
    return max(len(line) for line in lines) * font_size * CHAR_W, len(lines) * font_size * LINE_H


class Doc:
    def __init__(self, title):
        self.title = title
        self.elements = []
        self.by_id = {}
        self._seed = zlib.crc32(title.encode()) & 0x7FFFFFFF
        self.warnings = []

    # ── internals ──
    def _next_seed(self):
        self._seed = (self._seed * 1103515245 + 12345) & 0x7FFFFFFF
        return self._seed

    def _base(self, id_, type_, x, y, w, h, stroke, bg, dashed=False, stroke_w=2, opacity=100, rounded=True):
        if id_ in self.by_id:
            raise ValueError(f"duplicate id {id_}")
        el = {
            "id": id_, "type": type_, "x": round(x, 1), "y": round(y, 1),
            "width": round(w, 1), "height": round(h, 1), "angle": 0,
            "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
            "strokeWidth": stroke_w, "strokeStyle": "dashed" if dashed else "solid",
            "roughness": 0, "opacity": opacity, "groupIds": [], "frameId": None,
            "roundness": {"type": 3} if (rounded and type_ == "rectangle") else None,
            "seed": self._next_seed(), "version": 1, "versionNonce": self._next_seed(),
            "isDeleted": False, "boundElements": [], "updated": 1760000000000,
            "link": None, "locked": False,
        }
        self.elements.append(el)
        self.by_id[id_] = el
        return el

    def _bind(self, container_id, bound_id, kind):
        self.by_id[container_id]["boundElements"].append({"id": bound_id, "type": kind})

    def _text_el(self, id_, x, y, text, size, color, container=None, align="center", valign="middle"):
        w, h = text_size(text, size)
        el = self._base(id_, "text", x, y, w, h, color, "transparent", stroke_w=1, rounded=False)
        el.update({
            "text": text, "originalText": text, "fontSize": size, "fontFamily": FONT,
            "textAlign": align, "verticalAlign": valign, "containerId": container,
            "lineHeight": LINE_H, "autoResize": True, "baseline": round(size * 0.9),
        })
        return el

    # ── public builders ──
    def box(self, id_, x, y, w, h, label=None, kind="plain", dashed=False, size=15, valign="middle",
            stroke=None, bg=None, stroke_w=2, opacity=100, label_color=None):
        colors = PALETTE[kind]
        el = self._base(id_, "rectangle", x, y, w, h, stroke or colors["stroke"], bg or colors["bg"],
                        dashed=dashed, stroke_w=stroke_w, opacity=opacity)
        if label:
            tw, th = text_size(label, size)
            if tw > w - 14 or th > h - 6:
                self.warnings.append(f"label of {id_} may overflow ({tw:.0f}x{th:.0f} in {w:.0f}x{h:.0f})")
            tx = x + (w - tw) / 2
            ty = y + (6 if valign == "top" else (h - th) / 2)
            tid = f"{id_}__t"
            self._text_el(tid, tx, ty, label, size, label_color or "#1e1e1e", container=id_, valign=valign)
            self._bind(id_, tid, "text")
        return el

    def note(self, id_, x, y, text, size=14, color="#1e1e1e", align="left"):
        """Free-standing text (no container)."""
        return self._text_el(id_, x, y, text, size, color, container=None, align=align, valign="top")

    def marker(self, id_, cx, cy, number, r=15):
        """Red numbered circle used to flag a design violation."""
        el = self._base(id_, "ellipse", cx - r, cy - r, 2 * r, 2 * r, "#e03131", "#e03131", stroke_w=2, rounded=False)
        label = str(number)
        tw, th = text_size(label, 14)
        tid = f"{id_}__t"
        self._text_el(tid, cx - tw / 2, cy - th / 2, label, 14, "#ffffff", container=id_)
        self._bind(id_, tid, "text")
        return el

    @staticmethod
    def _anchor(el, side, frac=0.5):
        x, y, w, h = el["x"], el["y"], el["width"], el["height"]
        return {"t": (x + w * frac, y), "b": (x + w * frac, y + h),
                "l": (x, y + h * frac), "r": (x + w, y + h * frac)}[side]

    def arrow(self, id_, src, dst, src_side="b", dst_side="t", label=None, color="#1e1e1e",
              dashed=False, src_frac=0.5, dst_frac=0.5, size=12, stroke_w=2):
        a, b = self.by_id[src], self.by_id[dst]
        gap = 4
        x1, y1 = self._anchor(a, src_side, src_frac)
        x2, y2 = self._anchor(b, dst_side, dst_frac)
        off = {"t": (0, -gap), "b": (0, gap), "l": (-gap, 0), "r": (gap, 0)}
        x1, y1 = x1 + off[src_side][0], y1 + off[src_side][1]
        x2, y2 = x2 + off[dst_side][0], y2 + off[dst_side][1]
        el = self._base(id_, "arrow", x1, y1, abs(x2 - x1), abs(y2 - y1), color, "transparent",
                        dashed=dashed, stroke_w=stroke_w, rounded=False)
        el["roundness"] = {"type": 2}
        el.update({
            "points": [[0, 0], [round(x2 - x1, 1), round(y2 - y1, 1)]],
            "lastCommittedPoint": None, "startArrowhead": None, "endArrowhead": "arrow",
            "startBinding": {"elementId": src, "focus": round((src_frac - 0.5) * 2 * 0.9, 3), "gap": gap},
            "endBinding": {"elementId": dst, "focus": round((dst_frac - 0.5) * 2 * 0.9, 3), "gap": gap},
            "elbowed": False,
        })
        self._bind(src, id_, "arrow")
        self._bind(dst, id_, "arrow")
        if label:
            tw, th = text_size(label, size)
            tid = f"{id_}__t"
            self._text_el(tid, (x1 + x2) / 2 - tw / 2, (y1 + y2) / 2 - th / 2, label, size, color, container=id_)
            self._bind(id_, tid, "text")
        return el

    # ── output ──
    def to_dict(self):
        for el in self.elements:
            if not el["boundElements"]:
                el["boundElements"] = None
        return {
            "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=1)
