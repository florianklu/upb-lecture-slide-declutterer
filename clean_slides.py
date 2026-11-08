#!/usr/bin/env python3
"""
Vorlesungsfolien-Bereiniger (Slide Cleaner)
===========================================
Entfernt automatisch störende Design-Elemente (Logos, farbige Dreiecke)
und Seitennummern aus Vorlesungsfolien basierend auf Folientypen (siehe TEMPLATE_NAMES)

Verwendet:
  - Visuelles Template-Matching anhand von leeren Muster-Folien (PNGs)
  - Vektor- & Text-Redaction (PyMuPDF) zur restlosen Beseitigung inklusive Seitenzahlen
"""

import sys
from pathlib import Path
import re
from typing import Dict, Tuple, Optional, List
import numpy as np
from PIL import Image
import pymupdf


TEMPLATE_NAMES = [
    "Title_slide",
    "Agenda",
    "Separation_page",
    "Separation_page_large_triangles",
    "Title_slide_large_triangles",
    "Title_slide_with_image_A",
    "Title_slide_with_image_B",
    "Blue_design",
    "Blue_Design_large_triangles",
    "Contact",
    "Content",
    "Agenda_large_triangles",
]


class SlideCleaner:
    def __init__(self, template_dir: Optional[Path] = None):
        """
        Lädt die Muster-Vorlagen (PNGs) für visuelles Template-Matching
        standardmäßig aus dem Ordner 'templates/'.
        """
        if template_dir is None:
            template_dir = Path("templates")
            if not template_dir.exists():
                template_dir = Path(__file__).resolve().parent / "templates"

        self.templates: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self._load_templates(template_dir)

    def _load_templates(self, template_dir: Path):
        """Lädt und skaliert die Muster-PNGs auf ein Referenzgitter (320x180)."""
        target_size = (320, 180)
        for name in TEMPLATE_NAMES:
            png_file = template_dir / f"{name}.png"
            if not png_file.exists():
                print(f"Template {name} existiert nicht")
                # Groß-/Kleinschreibung ignorieren als Fallback
                matches = list(template_dir.glob(f"*{name}*.png"))
                if matches:
                    png_file = matches[0]

            if png_file.exists():
                try:
                    im = Image.open(png_file).convert("RGB").resize(target_size, Image.Resampling.BILINEAR)
                    arr = np.array(im)
                    # Maske aller Nicht-Weiß-Pixel (< 240 in mindestens einem Farbkanal)
                    mask = (arr < 240).any(axis=2)
                    self.templates[name] = (arr, mask)
                except Exception as e:
                    print(f"[Warnung] Konnte Template '{png_file.name}' nicht laden: {e}")

        if len(self.templates) == len(TEMPLATE_NAMES):
            print(f"-> Alle {len(self.templates)} Folien-Templates erfolgreich geladen.")
        else:
            print(f"-> {len(self.templates)}/{len(TEMPLATE_NAMES)} Folien-Templates geladen.")

    def classify_page(self, page: pymupdf.Page, page_idx: int, total_pages: int) -> str:
        """
        Klassifiziert den Folientyp einer PDF-Seite über
        visuelles Template-Matching mit den PNG-Vorlagen
        """

        if self.templates:
            w, h = page.rect.width, page.rect.height
            mat = pymupdf.Matrix(320 / w, 180 / h)
            pix = page.get_pixmap(matrix=mat)
            parr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((180, 320, pix.n))[:, :, :3]

            scores = {}
            for tname, (tarr, tmask) in self.templates.items():
                if np.sum(tmask) == 0:
                    continue
                diff = np.abs(parr[tmask].astype(int) - tarr[tmask].astype(int))
                scores[tname] = np.mean(diff)

            if scores:
                best_match = min(scores, key=scores.get)
                best_score = scores[best_match]

                # Prüfe zusätzlich den oberen linken Logo-Bereich des Content-Templates,
                # damit UPB-Content-Folien mit großen Bildern über den Dreiecken (wie Test_Slides S. 12)
                # weiterhin sicher als 'Content' erkannt werden.
                content_tl_diff = 999.0
                if "Content" in self.templates:
                    ct_arr, ct_mask = self.templates["Content"]
                    tl_mask = ct_mask.copy()
                    tl_mask[:, 60:] = False
                    tl_mask[30:, :] = False
                    if np.sum(tl_mask) > 0:
                        content_tl_diff = float(
                            np.mean(np.abs(parr[tl_mask].astype(int) - ct_arr[tl_mask].astype(int)))
                        )

                if best_score > 34.0 and not (best_match == "Content" and content_tl_diff <= 20.0):
                    best_match = "Custom"

                print(f"Page {page.number:3d} | {best_match[:30]:<30} | score: {best_score:6.0f}px")
                return best_match
            else:
                return "Unknown"

        return "Unknown"

    def get_redaction_rects(
        self,
        slide_type: str,
        w: float,
        h: float,
        page: Optional[pymupdf.Page] = None,
        remove_slide_numbers: bool = True,
        remove_footer_text: bool = True,
    ) -> List[pymupdf.Rect]:
        """
        Liefert die exakten Bereinigungs-Rechtecke für den jeweiligen Folientyp.
        """
        rects: List[pymupdf.Rect] = []

        if slide_type == "Title_slide":
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(26, 20, 232, 103))
            # Dreiecke oben rechts (gestuft entlang der Dreieckskontur)
            rects.append(pymupdf.Rect(816, 35, 850, 63))
            rects.append(pymupdf.Rect(848, 23, w, 100))
            # Dreiecke unten rechts (präzise gestuft entlang der einzelnen Dreiecke)
            rects.append(pymupdf.Rect(911, 281, 930, 308))
            rects.append(pymupdf.Rect(879, 330, 898, 357))
            rects.append(pymupdf.Rect(863, 379, w, h))
            rects.append(pymupdf.Rect(801, 428, 865, 529))
            rects.append(pymupdf.Rect(738, 489, 760, 517))
        elif slide_type == "Title_slide_large_triangles":
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(64, 65, 258, 125))
            # Große dunkelblaue/bunte Dreiecke oben rechts
            rects.append(pymupdf.Rect(655, 35, 785, 112))
            # Blauer Balken + Dreiecke auf der rechten Seite
            rects.append(pymupdf.Rect(w - 176, 0, w, h))
        elif slide_type == "Title_slide_with_image_A":
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(64, 46, 240, 105))
            # Farbige Dreiecke oben Mitte-Links
            rects.append(pymupdf.Rect(320, 35, 465, 113))
        elif slide_type == "Title_slide_with_image_B":
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(78, 81, 256, 140))
            # Farbige Dreiecke oben Mitte
            rects.append(pymupdf.Rect(464, 72, 608, 149))
        elif slide_type == "Content":
            # UPB-Logo oben links (endet weit vor Folientiteln ab y > 95)
            rects.append(pymupdf.Rect(16, 24, 158, 75))
            # Dreiecke oben rechts (präzise gestuft: links flacher, rechts bis y=75)
            rects.append(pymupdf.Rect(722, 11, 801, 51))
            rects.append(pymupdf.Rect(800, 11, w, 75))
            # Dreiecke unten rechts (unmittelbar rechts neben der Seitennummer)
            rects.append(pymupdf.Rect(w - 33, h - 88, w, h))

            # Seitennummern unten rechts (punktgenau um die Zahl, berührt NIE Content-Boxen)
            if remove_slide_numbers:
                found_word = False
                if page is not None:
                    # Suche die exakte Position der Seitenzahl im Text
                    for wd in page.get_text("words"):
                        # Seitenzahl steht rechts von x=880, unterhalb von y=490 und besteht aus Ziffern
                        if wd[0] > 880 and wd[1] > 490 and wd[4].isdigit():
                            # Punktgenaue Box mit 3 Pt Polsterung
                            rects.append(pymupdf.Rect(wd[0] - 3, wd[1] - 3, wd[2] + 3, wd[3] + 3))
                            found_word = True
                if not found_word:
                    # Präziser Fallback-Bereich ausschließlich für die Seitenzahl
                    rects.append(pymupdf.Rect(895, 498, 925, 526))
            if remove_footer_text:
                footer_rect = self._get_footer_rect(page, w, h)
                if footer_rect is not None:
                    rects.append(footer_rect)

        elif slide_type == "Agenda":
            # Vertikale Dreiecksleiste ganz links (gestuft entlang der Kontur)
            rects.append(pymupdf.Rect(0, 48, 97, 505))
            rects.append(pymupdf.Rect(95, 73, 112, 344))
            # Dreiecke unten rechts (präzise gestuft)
            rects.append(pymupdf.Rect(911, 281, 945, 308))
            rects.append(pymupdf.Rect(879, 330, 913, 357))
            rects.append(pymupdf.Rect(863, 379, w, h))
            rects.append(pymupdf.Rect(832, 465, 865, 517))
            rects.append(pymupdf.Rect(738, 489, 760, 517))
        elif slide_type == "Agenda_large_triangles":
            # Dreiecke oben rechts (gestuft)
            rects.append(pymupdf.Rect(784, 58, 865, 123))
            rects.append(pymupdf.Rect(864, 34, 929, 136))
        elif slide_type == "Separation_page":
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(24, 24, 158, 79))
            # Cyanfarbenes Rechteck oben rechts
            rects.append(pymupdf.Rect(w - 130, 0, w - 55, 92))
            # Farbige Dreiecks-Welle unten (präzise U-förmig gestuft, lässt die Folienmitte bis y=428 frei)
            rects.append(pymupdf.Rect(0, 281, 64, h))
            rects.append(pymupdf.Rect(62, 342, 158, h))
            rects.append(pymupdf.Rect(156, 391, 284, h))
            rects.append(pymupdf.Rect(282, 428, 645, h))
            rects.append(pymupdf.Rect(655, 440, 760, 517))
            rects.append(pymupdf.Rect(705, 367, 730, 395))
            rects.append(pymupdf.Rect(784, 403, 867, 529))
            rects.append(pymupdf.Rect(863, 379, w, h))
            rects.append(pymupdf.Rect(879, 330, 913, 358))
            rects.append(pymupdf.Rect(911, 281, 930, 309))
        elif slide_type == "Separation_page_large_triangles":
            # Blauer Balken + große Dreiecke auf der linken Seite (präzise gestuft)
            rects.append(pymupdf.Rect(0, 0, 176, h))
            rects.append(pymupdf.Rect(175, 366, 240, 517))
            rects.append(pymupdf.Rect(255, 391, 304, 443))
            # Blaue Dreiecke oben rechts (Kapitelnummer darin wird bewahrt und schwarz umgefärbt)
            rects.append(pymupdf.Rect(847, 23, w, 160))
        elif slide_type == "Contact":
            # Kontakt-Grafik/Icon oben
            rects.append(pymupdf.Rect(205, 50, 395, 112))
            # Dreiecke unten links (präzise gestuft)
            rects.append(pymupdf.Rect(0, 379, 97, h))
            rects.append(pymupdf.Rect(95, 452, 270, h))
            # Dreiecke unten rechts (präzise gestuft)
            rects.append(pymupdf.Rect(911, 281, 945, 308))
            rects.append(pymupdf.Rect(879, 330, 913, 357))
            rects.append(pymupdf.Rect(863, 379, w, h))
            rects.append(pymupdf.Rect(832, 465, 865, 517))
            rects.append(pymupdf.Rect(738, 489, 760, 517))
        elif slide_type in ["Blue_design", "Blue_Design_large_triangles"]:
            # UPB-Logo oben links
            rects.append(pymupdf.Rect(16, 24, 158, 75))
            # Blauer Balken und farbige Dreiecke auf der rechten Seite
            rects.append(pymupdf.Rect(w - 240, 0, w, h))
            if slide_type == "Blue_Design_large_triangles":
                # Große farbige Dreiecke links neben dem blauen Balken oben
                rects.append(pymupdf.Rect(624, 10, 721, 86))
        return rects

    def _get_footer_rect(
        self, page: Optional[pymupdf.Page], w: float, h: float
    ) -> Optional[pymupdf.Rect]:
        """
        Bestimmt dynamisch die exakte Position und Breite des Footer-Textes
        (inklusive des kleinen vertikalen Balkens links vor dem Footer-Text)
        auf Content-Folien.
        """
        if page is None:
            return pymupdf.Rect(30, h - 38, 600, h - 18)

        bar_rects: List[pymupdf.Rect] = []
        for d in page.get_drawings():
            r = d["rect"]
            # Kleiner vertikaler blauer Balken links vor dem Footer-Text (ca. x=31..38, y=504..528)
            if (
                25 <= r.x0 <= 45
                and (h - 42) <= r.y0 <= (h - 12)
                and r.y1 <= (h - 8)
                and r.width <= 6
                and r.height <= 25
            ):
                bar_rects.append(r)

        text_rects: List[pymupdf.Rect] = []
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                lx0, ly0, lx1, ly1 = line["bbox"]
                txt = "".join(span["text"] for span in line.get("spans", [])).strip()
                if not txt:
                    continue
                # Footer-Text beginnt direkt rechts neben dem vertikalen Balken (x0 ca. 40..65)
                if 35 <= lx0 <= 65 and (h - 42) <= ly0 <= (h - 12) and ly1 <= (h - 8):
                    text_rects.append(pymupdf.Rect(lx0, ly0, lx1, ly1))

        all_rects = bar_rects + text_rects
        if not all_rects:
            return None

        x0 = min(r.x0 for r in all_rects) - 2.0
        # Nur minimale Polsterung nach oben (0.5 Pt), damit tief sitzender Folieninhalt nicht berührt wird
        y0 = min(r.y0 for r in all_rects) - 0.5
        x1 = max(r.x1 for r in all_rects) + 2.0
        y1 = max(r.y1 for r in all_rects) + 1.5
        return pymupdf.Rect(x0, y0, x1, y1)

    @staticmethod
    def _merge_adjacent_rects(
        rects: List[pymupdf.Rect], max_gap: float = 4.0
    ) -> List[pymupdf.Rect]:
        """
        Fasst einander berührende oder eng benachbarte Rechtecke (Abstand <= max_gap)
        zu sauberen Bounding-Boxen zusammen (z. B. für mehrteilige Vektor-Logos oder Dreiecks-Cluster).
        """
        if not rects:
            return []
        merged = [pymupdf.Rect(r) for r in rects]
        changed = True
        while changed:
            changed = False
            new_merged: List[pymupdf.Rect] = []
            used = [False] * len(merged)
            for i in range(len(merged)):
                if used[i]:
                    continue
                cur = merged[i]
                for j in range(i + 1, len(merged)):
                    if used[j]:
                        continue
                    other = merged[j]
                    exp = pymupdf.Rect(
                        cur.x0 - max_gap,
                        cur.y0 - max_gap,
                        cur.x1 + max_gap,
                        cur.y1 + max_gap,
                    )
                    if exp.intersects(other):
                        cur = cur | other
                        used[j] = True
                        changed = True
                new_merged.append(cur)
            merged = new_merged
        return merged

    def _analyze_document_elements(
        self,
        doc: pymupdf.Document,
        slide_types: List[str],
        remove_slide_numbers: bool = True,
        remove_footer_text: bool = True,
    ) -> Tuple[Dict[int, List[str]], Dict[int, List[pymupdf.Rect]], Dict[int, bool]]:
        """
        Analysiert dokumentweit alle Seiten auf sich wiederholende Elemente:
          1. Form-XObjects (Meta*)
          2. Image-XObjects (wiederholte Logos in Header/Footer sowie Titelfolien-Logos/Dreiecke)
          3. Sich wiederholende Vektor-Zeichnungen (Logos, Balken, Banner, Dreiecks-Cluster in den Rändern)
          4. Sich wiederholende Textzeilen (Fußzeilen, vertikale Autorennamen, Header-Banner)
          5. Seitenzahlen auf Custom-Folien (unten rechts oder unten links)

        Rückgabe:
          - xobj_names_to_remove[page_idx]: XObject-Namen, deren '/Name Do' im Stream entfernt wird
          - extra_rects[page_idx]: Zusätzliche Redaction-/Preview-Rechtecke für diese Seite
          - remove_bg_watermark[page_idx]: Ob ein vollflächiges graues Vektor-Wasserzeichen im Stream liegt
        """
        num_pages = len(doc)
        content_pages = [i for i, st in enumerate(slide_types) if st == "Content"]
        num_content = len(content_pages)
        min_repeat = max(2, int(round(0.30 * num_pages))) if num_pages >= 2 else 1
        min_draw_repeat = max(3, int(round(0.30 * num_pages))) if num_pages >= 4 else min_repeat

        # ------------------------------------------------------------------
        # Pass 1: Dokumentweite Häufigkeiten sammeln
        # ------------------------------------------------------------------
        xobj_all_pages: Dict[int, set] = {}
        xobj_content_pages: Dict[int, set] = {}
        img_all_pages: Dict[int, set] = {}
        img_content_pages: Dict[int, set] = {}
        draw_rect_pages: Dict[Tuple[float, float, float, float], set] = {}
        repeating_header_fills: set = set()
        text_exact_pages: Dict[Tuple[int, int, str], set] = {}
        footer_slot_pages: Dict[Tuple[int, int, int], set] = {}
        repeating_author_strings: set = set()

        for page_idx, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            st = slide_types[page_idx]

            for xo in page.get_xobjects():
                xref = xo[0]
                xobj_all_pages.setdefault(xref, set()).add(page_idx)
                if st == "Content":
                    xobj_content_pages.setdefault(xref, set()).add(page_idx)

            for im in page.get_images():
                xref = im[0]
                img_all_pages.setdefault(xref, set()).add(page_idx)
                if st == "Content":
                    img_content_pages.setdefault(xref, set()).add(page_idx)

            for d in page.get_drawings():
                r = d["rect"]
                if r.x1 <= 0 or r.x0 >= w or r.y1 <= 0 or r.y0 >= h:
                    continue
                if r.width >= w - 20 and r.height >= h - 20:
                    continue
                key = (
                    round(r.x0 / 2.0) * 2.0,
                    round(r.y0 / 2.0) * 2.0,
                    round(r.x1 / 2.0) * 2.0,
                    round(r.y1 / 2.0) * 2.0,
                )
                draw_rect_pages.setdefault(key, set()).add(page_idx)

            tdict = page.get_text("dict")
            for b in tdict.get("blocks", []):
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    bx = line["bbox"]
                    txt = "".join(s["text"] for s in line.get("spans", [])).strip()
                    if not txt:
                        continue
                    low_txt = txt.lower().lstrip("(").strip()
                    if low_txt.startswith(("source:", "quelle:", "datenquelle:", "sources:", "quellen:")):
                        continue
                    # Prüfe Randbereiche: Oben (y1 <= 75), Unten (y0 >= h - 45) oder linker Rand vertikal (x1 <= 35, y0 >= h - 85)
                    in_top_banner = bx[0] >= 0.45 * w and bx[3] <= 75
                    in_bottom_footer = bx[1] >= h - 45
                    in_left_vertical = bx[2] <= 35 and bx[1] >= h - 85
                    if in_top_banner or in_bottom_footer or in_left_vertical:
                        tkey = (int(round(bx[0], -1)), int(round(bx[1], 0)), txt)
                        text_exact_pages.setdefault(tkey, set()).add(page_idx)
                        if in_bottom_footer and ("|" in txt or "–" in txt or "-" in txt or "©" in txt):
                            skey = (int(round(bx[0], -1)), int(round(bx[1], 0)), int(round(bx[3], 0)))
                            footer_slot_pages.setdefault(skey, set()).add(page_idx)

        # Merke Text-Strings, die sich dokumentweit wiederholen (z. B. 'Dr. Sonja Lück')
        for (_, _, txt), pgs in text_exact_pages.items():
            if len(pgs) >= min_repeat:
                repeating_author_strings.add(txt)

        # Merke Füllfarben sich wiederholender Header-Zeichnungen & Deko-Dreiecke (für verschobene/skalierte Logos & Rand-Dreiecke)
        repeating_triangle_fills: set = set()
        for page_idx, page in enumerate(doc):
            for d in page.get_drawings():
                r = d["rect"]
                key = (
                    round(r.x0 / 2.0) * 2.0,
                    round(r.y0 / 2.0) * 2.0,
                    round(r.x1 / 2.0) * 2.0,
                    round(r.y1 / 2.0) * 2.0,
                )
                freq = len(draw_rect_pages.get(key, set()))
                fill = d.get("fill")
                if not fill or fill == (1.0, 1.0, 1.0):
                    continue
                rfill = tuple(round(c, 3) for c in fill)
                if freq >= min_draw_repeat and r.y1 <= 100:
                    repeating_header_fills.add(rfill)
                if freq >= 3 and r.width <= 28 and r.height <= 28 and len(d.get("items", [])) <= 6:
                    repeating_triangle_fills.add(rfill)

        # ------------------------------------------------------------------
        # Pass 2: Seitenweise zu entfernende XObjects & Rechtecke bestimmen
        # ------------------------------------------------------------------
        xobj_names_to_remove: Dict[int, List[str]] = {i: [] for i in range(num_pages)}
        extra_rects: Dict[int, List[pymupdf.Rect]] = {i: [] for i in range(num_pages)}
        remove_bg_watermark: Dict[int, bool] = {i: False for i in range(num_pages)}

        for page_idx, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            st = slide_types[page_idx]
            page_clip = pymupdf.Rect(0, 0, w, h)

            cdata = ""
            for cxref in page.get_contents():
                cdata += doc.xref_stream(cxref).decode("latin1") + "\n"

            # 1. Form-XObjects (Meta*) prüfen
            for xo in page.get_xobjects():
                xref, name = xo[0], xo[1]
                bbox = xo[3]
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]

                total_freq = len(xobj_all_pages.get(xref, set()))
                content_freq = len(xobj_content_pages.get(xref, set()))

                artifact_calls = re.findall(
                    r"/Artifact\s+BMC\b(?:(?!\bEMC\b).)*?/" + re.escape(name) + r"\s+Do",
                    cdata,
                    flags=re.DOTALL,
                )
                content_calls = re.findall(
                    r"/P\s*<<[^>]*>>\s*BDC\b(?:(?!\bEMC\b).)*?/" + re.escape(name) + r"\s+Do",
                    cdata,
                    flags=re.DOTALL,
                )

                is_repeating_on_content = num_content >= 2 and (content_freq / num_content) >= 0.5
                is_master_layer = bw >= (w - 20) and bh >= (h - 20)
                is_top_left_logo_xobj = bbox[0] < 200 and bbox[1] < 100 and bbox[2] <= 300 and bbox[3] <= 130

                if not content_calls and (
                    bool(artifact_calls)
                    or is_repeating_on_content
                    or (total_freq >= 3 and (is_master_layer or is_top_left_logo_xobj))
                ):
                    xobj_names_to_remove[page_idx].append(name)

            # 2. Image-XObjects (Logos in Header/Footer & Titelfolien-Logos/Dreiecke) prüfen
            for im in page.get_images():
                xref, name = im[0], im[7]
                rects = page.get_image_rects(xref)
                total_freq = len(img_all_pages.get(xref, set()))
                content_freq = len(img_content_pages.get(xref, set()))
                is_repeating_on_content = num_content >= 2 and (content_freq / num_content) >= 0.5
                is_freq_img = total_freq >= min_repeat or total_freq >= 3 or is_repeating_on_content

                remove_img = False
                for r in rects:
                    # (a) Komplett außerhalb der sichtbaren Folie liegende Master-Artefakte
                    if r.x1 <= 0 or r.x0 >= w or r.y1 <= 0 or r.y0 >= h:
                        remove_img = True
                    # (b) Sich wiederholende Logos im oberen Header- oder unteren Footer-Randbereich
                    elif is_freq_img and (
                        (r.y0 < 100 and r.y1 <= 135 and r.width < 350 and r.height < 110 and (r.x0 < 380 or r.x0 > w - 300))
                        or (r.y0 >= h - 95 and r.width < 350 and r.height < 90)
                    ):
                        remove_img = True
                        if st == "Custom" or r.x1 > 160 or r.y0 >= h - 95:
                            extra_rects[page_idx].append(r & page_clip)
                    # (c) Titelfolien-spezifische Logos & Deko-Dreiecke (Seite 1)
                    elif page_idx == 0 and (
                        st
                        in (
                            "Title_slide",
                            "Title_slide_large_triangles",
                            "Title_slide_with_image_A",
                            "Title_slide_with_image_B",
                            "Custom",
                        )
                    ):
                        in_tl_logo = 0 <= r.x0 < 380 and r.x1 <= 460 and r.y0 < 100 and r.y1 <= 135 and r.width < 300 and r.height < 100
                        in_tr_deco = r.x0 >= w - 260 and r.y0 < 50 and r.y1 <= 90 and r.height < 85
                        in_br_logo = st == "Custom" and r.x0 >= w - 260 and r.y0 >= h - 200 and r.width < 260 and r.height < 180
                        if in_tl_logo or in_tr_deco or in_br_logo:
                            remove_img = True
                            if st == "Custom" or r.x1 > 160:
                                extra_rects[page_idx].append(r & page_clip)

                if remove_img:
                    xobj_names_to_remove[page_idx].append(name)

            # 3. Sich wiederholende Textzeilen (Footer & Header-Banner) ermitteln
            tdict = page.get_text("dict")
            page_lines: List[Tuple[pymupdf.Rect, str]] = []
            for b in tdict.get("blocks", []):
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    bx = line["bbox"]
                    txt = "".join(s["text"] for s in line.get("spans", [])).strip()
                    if txt:
                        page_lines.append((pymupdf.Rect(bx), txt))

            if remove_footer_text:
                for lrect, txt in page_lines:
                    low_txt = txt.lower().lstrip("(").strip()
                    if low_txt.startswith(("source:", "quelle:", "datenquelle:", "sources:", "quellen:")):
                        continue
                    tkey = (int(round(lrect.x0, -1)), int(round(lrect.y0, 0)), txt)
                    skey = (int(round(lrect.x0, -1)), int(round(lrect.y0, 0)), int(round(lrect.y1, 0)))
                    is_rep_line = (
                        len(text_exact_pages.get(tkey, set())) >= min_repeat
                        or len(footer_slot_pages.get(skey, set())) >= min_repeat
                        or (txt in repeating_author_strings and (lrect.y0 >= h - 45 or (lrect.x1 <= 35 and lrect.y0 >= h - 85)))
                    )
                    if is_rep_line and (st == "Custom" or lrect.x1 <= 80 or lrect.y1 <= 75):
                        padded_lrect = pymupdf.Rect(
                            max(0.0, lrect.x0 - 1.5),
                            max(0.0, lrect.y0 - 0.5),
                            min(w, lrect.x1 + 1.5),
                            min(h, lrect.y1 + 1.5),
                        )
                        extra_rects[page_idx].append(padded_lrect)

            # 4. Seitenzahlen auf Custom-Folien (oder falls außerhalb des Standard-Content-Bereichs)
            if remove_slide_numbers and st == "Custom":
                for wd in page.get_text("words"):
                    wx0, wy0, wx1, wy1, wtxt = wd[0], wd[1], wd[2], wd[3], wd[4].strip()
                    if wtxt.isdigit():
                        in_br_num = wx0 > w - 85 and wy0 > h - 48
                        in_bl_num = wx0 < 80 and wx1 < 85 and wy0 > h - 42
                        if in_br_num or in_bl_num:
                            extra_rects[page_idx].append(
                                pymupdf.Rect(
                                    max(0.0, wx0 - 3.0),
                                    max(0.0, wy0 - 3.0),
                                    min(w, wx1 + 3.0),
                                    min(h, wy1 + 3.0),
                                )
                            )

            # 5. Sich wiederholende Vektor-Zeichnungen (Logos, Balken, Banner, Dreiecke) prüfen
            #    (läuft auf Custom-Folien sowie für nicht vom Standard-Template abgedeckte Zusatz-Ränder wie in W1473)
            raw_draw_rects: List[pymupdf.Rect] = []
            for d in page.get_drawings():
                r = d["rect"]
                fill = d.get("fill")
                items_cnt = len(d.get("items", []))

                # (a) Vollflächiges hellgraues Vektor-Wasserzeichen im Hintergrund (wie 04_Der_Geld-_Finanzmarkt.pdf)
                if (
                    r.width > 0.75 * w
                    and r.height > 0.75 * h
                    and items_cnt > 400
                    and fill is not None
                    and all(0.85 <= c <= 0.96 for c in fill)
                ):
                    remove_bg_watermark[page_idx] = True
                    continue

                if r.x1 <= 0 or r.x0 >= w or r.y1 <= 0 or r.y0 >= h:
                    continue
                if r.width >= w - 20 and r.height >= h - 20:
                    continue

                # Nur auf Custom-Folien oder wenn die Zeichnung außerhalb der bereits vom UPB-Template
                # abgedeckten Bereiche liegt (wie das obere Logo / die oberen Dreiecke auf W1473 Agenda-Folien)
                if st not in ("Custom", "Agenda"):
                    continue

                key = (
                    round(r.x0 / 2.0) * 2.0,
                    round(r.y0 / 2.0) * 2.0,
                    round(r.x1 / 2.0) * 2.0,
                    round(r.y1 / 2.0) * 2.0,
                )
                freq = len(draw_rect_pages.get(key, set()))
                rfill = tuple(round(c, 3) for c in fill) if fill else None

                in_header_zone = r.y0 < 78 and r.y1 <= 105 and r.height <= 95
                in_footer_zone = r.y0 >= h - 90 and r.height <= 90
                in_corner_edge = r.x0 >= w - 50 or r.x1 <= 35

                is_rep_draw = freq >= min_draw_repeat and (in_header_zone or in_footer_zone or in_corner_edge)

                # Kleine Deko-Dreiecke in den typischen Dreiecks-Clustern (links, oben rechts, unten rechts),
                # die exakt die sich wiederholende Dreiecks-Farbpalette des Dokuments nutzen
                in_tri_cluster_zone = (
                    (r.x1 <= 115 and r.y0 >= 45)
                    or (r.x0 >= 640 and r.y1 <= 105)
                    or (r.x0 >= 735 and r.y0 >= 280)
                )
                is_cluster_triangle = (
                    in_tri_cluster_zone
                    and r.width <= 28
                    and r.height <= 28
                    and items_cnt <= 6
                    and rfill in repeating_triangle_fills
                )

                # Auf Seite 1 (Titelfolie) auch leicht verschobene/skalierte UPB-Vektorlogos & Dreiecke oben erkennen
                is_p1_header_logo_or_tri = False
                if page_idx == 0 and r.y1 <= 105 and (r.x1 < 400 or r.x0 > 640):
                    if rfill in repeating_header_fills or (
                        fill == (1.0, 1.0, 1.0) and r.x1 < 400 and r.y1 <= 100 and r.width > 100
                    ):
                        is_p1_header_logo_or_tri = True

                if not (is_rep_draw or is_cluster_triangle or is_p1_header_logo_or_tri):
                    continue

                # Schließe kleine Aufzählungs-Dreiecke ('►') unmittelbar links vor Überschriften aus (wie in W1473)
                if (
                    r.x1 < 85
                    and 58 <= r.y0 <= h - 90
                    and 4.0 <= r.width <= 30
                    and r.height <= 30
                    and items_cnt <= 6
                ):
                    has_heading_right = any(
                        r.x1 <= lrect.x0 <= r.x1 + 30
                        and lrect.y0 < r.y1
                        and lrect.y1 > r.y0
                        for lrect, _ in page_lines
                    )
                    if has_heading_right:
                        continue

                # Falls Footer-Text oder Seitenzahlen behalten werden sollen, lösche keine Hintergrundbalken,
                # auf denen dieser Text steht
                if not remove_footer_text and in_footer_zone and r.width > 200:
                    continue
                if not remove_footer_text and in_header_zone and r.x0 > 300 and any(r.intersects(lr) for lr, _ in page_lines):
                    continue

                top_pad = 8.0 if (in_header_zone and items_cnt > 50) else 1.0
                padded_dr = pymupdf.Rect(r.x0 - 1.0, r.y0 - top_pad, r.x1 + 1.0, r.y1 + 1.0)
                raw_draw_rects.append(padded_dr & page_clip)

            # Fasse benachbarte Vektor-Zeichnungen (z. B. Einzel-Dreiecke oder Buchstaben des Vektor-Logos)
            # zu sauberen gestuften Rechtecken zusammen
            merged_draw_rects = self._merge_adjacent_rects(raw_draw_rects, max_gap=4.0)
            extra_rects[page_idx].extend(merged_draw_rects)

        return xobj_names_to_remove, extra_rects, remove_bg_watermark

    @staticmethod
    def _recolor_chapter_number_in_stream(cdata: str) -> str:
        """
        Färbt auf 'Separation_page_large_triangles'-Folien die Kapitelnummer oben rechts
        (die im Original weiß/hellgrau auf dunkelblauem Dreieck steht, z. B. '0.949 g' oder
        '0.95 0.95 0.95 sc') in schwarze Schrift ('0 g' / '0 0 0 sc') um.
        """
        # Fall 1: PowerPoint-Vektor-Export (z. B. MODS2627: '923.66 447.49 Tm 0.949 g /GS8 gs 0.949 G')
        def _fix_bt_block(match: re.Match) -> str:
            block = match.group(0)
            # Prüfe, ob der Textblock im Bereich oben rechts (x >= 840, PDF-y >= 380) positioniert ist
            tm_matches = re.findall(
                r"([0-9.]+)\s+([0-9.]+)\s+Td|([0-9.]+)\s+([0-9.]+)\s+Tm", block
            )
            in_top_right = False
            for m in tm_matches:
                tx = float(m[0] or m[2])
                ty = float(m[1] or m[3])
                if tx >= 840 and ty >= 380:
                    in_top_right = True
                    break
            if not in_top_right:
                return block
            block = re.sub(r"\b0\.9\d*\s+g\b", "0 g", block)
            block = re.sub(r"\b0\.9\d*\s+G\b", "0 G", block)
            block = re.sub(r"\b1(?:\.0+)?\s+g\b", "0 g", block)
            block = re.sub(r"\b1(?:\.0+)?\s+G\b", "0 G", block)
            block = re.sub(
                r"\b(?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+rg\b",
                "0 0 0 rg",
                block,
            )
            block = re.sub(
                r"\b(?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+sc\b",
                "0 0 0 sc",
                block,
            )
            return block

        cdata = re.sub(r"BT\b.*?ET\b", _fix_bt_block, cdata, flags=re.DOTALL)

        # Fall 2: macOS Quartz PDFContext (z. B. Test_Slides.pdf P10: '0.95 0.95 0.95 sc ... 922.8325 444.5499 cm BT ... ET')
        cdata = re.sub(
            r"((?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+(?:0\.9\d*|1(?:\.0+)?)\s+sc)"
            r"(\s+/RelativeColorimetric\s+ri\s+q\s+1\s+0\s+0\s+1\s+9\d\d\.\d+\s+4\d\d\.\d+\s+cm\s+BT\b)",
            r"0 0 0 sc\2",
            cdata,
        )
        return cdata

    def clean_pdf(
        self,
        input_pdf_path: str,
        output_pdf_path: str,
        preview_mode: bool = False,
        remove_slide_numbers: bool = True,
        remove_footer_text: bool = True,
    ):
        """
        Bereinigt eine PDF-Datei vollständig.
        """
        in_path = Path(input_pdf_path)
        out_path = Path(output_pdf_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open(str(in_path))
        num_pages = len(doc)
        print(f"\n=======================================================")
        print(f"Verarbeite: {in_path.name} ({num_pages} Seiten)")
        print(f"Modus: {'Vorschau (rote Rahmen)' if preview_mode else 'Bereinigung'}")
        print(f"Seitennummern auf Content-Folien entfernen: {remove_slide_numbers}")
        print(f"Fußzeile auf Content-Folien entfernen: {remove_footer_text}")
        print(f"=======================================================")

        type_counts: Dict[str, int] = {}

        # 1. Alle Seiten klassifizieren
        slide_types: List[str] = []
        for page_idx, page in enumerate(doc):
            stype = self.classify_page(page, page_idx, num_pages)
            slide_types.append(stype)
            type_counts[stype] = type_counts.get(stype, 0) + 1

        # 2. Dokumentweite Analyse sich wiederholender Elemente (XObjects, Logos, Vektor-Clutter, Footer, Seitenzahlen)
        xobj_to_remove, extra_rects, remove_bg_watermark = self._analyze_document_elements(
            doc,
            slide_types,
            remove_slide_numbers=remove_slide_numbers,
            remove_footer_text=remove_footer_text,
        )

        for page_idx, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            stype = slide_types[page_idx]

            # Prüfe, ob die Folie ein vollflächiges Rasterbild als Hintergrund nutzt (wie in Test_Slides.pdf)
            has_full_page_raster = any(
                r.width >= w - 5 and r.height >= h - 5
                for im in page.get_images()
                for r in page.get_image_rects(im[0])
            )

            # Bei Separation_page_large_triangles auf Raster-Hintergrund (Test_Slides.pdf P10):
            # Kapitelnummer oben rechts vor der Redaction sichern, um sie danach schwarz einzufügen
            saved_chapter_spans: List[Tuple[pymupdf.Point, str, float]] = []
            if stype == "Separation_page_large_triangles" and has_full_page_raster:
                top_right_rect = pymupdf.Rect(847, 23, w, 160)
                tdict = page.get_text("dict")
                for b in tdict.get("blocks", []):
                    if b.get("type") != 0:
                        continue
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            sb = pymupdf.Rect(span["bbox"])
                            txt = span["text"].strip()
                            if txt and sb.intersects(top_right_rect):
                                origin = pymupdf.Point(span["origin"])
                                saved_chapter_spans.append((origin, txt, span["size"]))

            # 3. Content-Stream gezielt bereinigen (nur identifizierte Master-/Logo-XObjects & Hintergrund-Wasserzeichen entfernen)
            if not preview_mode:
                names = set(xobj_to_remove.get(page_idx, []))
                strip_wm = remove_bg_watermark.get(page_idx, False)
                c_xrefs = page.get_contents()
                if c_xrefs:
                    cdata = b"".join(doc.xref_stream(cx) for cx in c_xrefs).decode("latin1")
                    cdata_new = cdata

                    for xname in names:
                        cdata_new = re.sub(
                            r"/" + re.escape(xname) + r"\s+Do\b", "", cdata_new
                        )

                    if strip_wm:
                        cdata_new = re.sub(
                            r"0\.9\d+\s+g\s+q\s+1\s+0\s+0\s+1\s+.*?\bf\*?\s+Q",
                            "",
                            cdata_new,
                            flags=re.DOTALL,
                        )

                    if stype == "Separation_page_large_triangles":
                        cdata_new = self._recolor_chapter_number_in_stream(cdata_new)

                    if cdata_new != cdata:
                        doc.update_stream(c_xrefs[0], cdata_new.encode("latin1"))
                        for extra_cx in c_xrefs[1:]:
                            doc.update_stream(extra_cx, b"")

            # 4. Spezifische Redaction-Bereiche (inkl. erkannter sich wiederholender Elemente) ermitteln
            rects = self.get_redaction_rects(
                stype,
                w,
                h,
                page=page,
                remove_slide_numbers=remove_slide_numbers,
                remove_footer_text=remove_footer_text,
            )
            for er in extra_rects.get(page_idx, []):
                if not any(
                    abs(er.x0 - existing.x0) < 4
                    and abs(er.y0 - existing.y0) < 4
                    and abs(er.x1 - existing.x1) < 4
                    and abs(er.y1 - existing.y1) < 4
                    for existing in rects
                ):
                    rects.append(er)

            # Entferne Rechtecke, die bereits vollständig in einem größeren Rechteck derselben Seite liegen
            filtered_rects: List[pymupdf.Rect] = []
            for i, r1 in enumerate(rects):
                is_contained = False
                for j, r2 in enumerate(rects):
                    if i == j:
                        continue
                    if (
                        r2.x0 - 1.0 <= r1.x0
                        and r2.y0 - 1.0 <= r1.y0
                        and r2.x1 + 1.0 >= r1.x1
                        and r2.y1 + 1.0 >= r1.y1
                        and (r2.width * r2.height > r1.width * r1.height + 1.0 or j < i)
                    ):
                        is_contained = True
                        break
                if not is_contained:
                    filtered_rects.append(r1)
            rects = filtered_rects

            if preview_mode:
                # Vorschau: rote Rahmen zeichnen
                for r in rects:
                    page.draw_rect(r, color=(1, 0, 0), width=1.5)
                # Folientyp als Textmarker oben links einblenden
                page.insert_text(
                    pymupdf.Point(10, 15),
                    f"Typ: {stype} (Seite {page_idx+1})",
                    fontsize=10,
                    color=(1, 0, 0),
                )
            else:
                # Erweitere Rand-Rechtecke minimal über die Folienkante hinaus, damit auch
                # Dreiecke oder Balken exakt auf der Kante (z. B. x0=0.1, x1=959.9 oder y1=539.9)
                # durch PDF_REDACT_LINE_ART_REMOVE_IF_COVERED vollständig als abgedeckt gelten.
                padded_rects: List[pymupdf.Rect] = []
                for r in rects:
                    padded_rects.append(
                        pymupdf.Rect(
                            -2.0 if r.x0 <= 1.5 else r.x0,
                            -2.0 if r.y0 <= 1.5 else r.y0,
                            w + 2.0 if r.x1 >= w - 1.5 else r.x1,
                            h + 2.0 if r.y1 >= h - 1.5 else r.y1,
                        )
                    )

                # Gruppiere nicht-überlappende Rechtecke in Durchgänge, damit PyMuPDF
                # überlappende Redaction-Bereiche nicht an den Schnittkanten zerteilt.
                passes: List[List[pymupdf.Rect]] = []
                for pr in padded_rects:
                    placed = False
                    for p_group in passes:
                        if not any(pr.intersects(existing) for existing in p_group):
                            p_group.append(pr)
                            placed = True
                            break
                    if not placed:
                        passes.append([pr])

                # Auf Vektor-Folien (ohne vollflächiges Hintergrund-Rasterbild) verwenden wir fill=False:
                # Dadurch werden die abgedeckten Vektor-Dreiecke restlos gelöscht, aber NIEMALS weiße
                # Rechtecke über Inhalts-Grafiken oder Bilder gemalt, die über den Dreiecken liegen!
                redact_fill = (1, 1, 1) if has_full_page_raster else False

                for p_group in passes:
                    # Bestimme, ob in dieser Gruppe Text gelöscht werden soll:
                    # Auf Separation_page_large_triangles soll die Kapitelnummer oben rechts erhalten bleiben.
                    # Ebenso soll auf Separation_page oder bei reinen Dreiecks-Rechtecken kein Inhalts-Text
                    # (wie 'Switching' / 'Asset' auf Kap3_IMM S. 109/114) gelöscht werden.
                    keep_text_in_group = False
                    if stype == "Separation_page_large_triangles":
                        keep_text_in_group = True
                    elif stype == "Separation_page":
                        # Auf Separation_page enthält nur das UPB-Logo oben links (y1 <= 90, x0 < 200) ggf. Logo-Text
                        if all(not (pr.x0 < 200 and pr.y1 <= 90) for pr in p_group):
                            keep_text_in_group = True

                    for pr in p_group:
                        page.add_redact_annot(pr, fill=redact_fill)

                    page.apply_redactions(
                        images=pymupdf.PDF_REDACT_IMAGE_NONE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                        text=(
                            pymupdf.PDF_REDACT_TEXT_NONE
                            if keep_text_in_group
                            else pymupdf.PDF_REDACT_TEXT_REMOVE
                        ),
                    )

                # Falls Separation_page_large_triangles auf einer Raster-Folie lag (Test_Slides.pdf P10),
                # schreibe die gesicherte Kapitelnummer in Schwarz wieder an ihre Originalposition.
                for origin, txt, fsize in saved_chapter_spans:
                    page.insert_text(
                        origin,
                        txt,
                        fontsize=fsize,
                        fontname="helv",
                        color=(0, 0, 0),
                    )

        # Zusammenfassung
        print("\nErkannte Folientypen:")
        for tname in TEMPLATE_NAMES + ["Custom"]:
            cnt = type_counts.get(tname, 0)
            if cnt > 0:
                print(f"  - {tname:32s}: {cnt:2d} Folien")

        if not preview_mode:
            doc.save(str(out_path), garbage=4, deflate=True)
            print(f"\n[OK] Bereinigte Datei gespeichert: {out_path}")
        else:
            doc.save(str(out_path))
            print(f"\n[OK] Vorschau-Datei gespeichert: {out_path}")

        doc.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Bereinigt Vorlesungsfolien basierend auf Folientypen (Logos, Dreiecke, Seitennummern)."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="examplePDFs/Test_Slides.pdf",
        help="Pfad zur Eingabe-PDF oder zum Ordner mit PDFs",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Pfad zur Ausgabe-PDF oder zum Ausgabeordner (optional, Standard: 'clean/' bzw. 'preview/')",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Erzeugt eine Vorschau mit roten Markierungsrahmen und Folientyp-Anzeige (Standard-Ausgabeordner: 'preview/')",
    )
    parser.add_argument(
        "--keep-slide-numbers",
        action="store_true",
        help="Seitennummern auf Content-Folien NICHT entfernen",
    )
    parser.add_argument(
        "--keep-footer-text",
        action="store_true",
        help="Fußzeile auf Content-Folien NICHT entfernen",
    )

    args = parser.parse_args()
    cleaner = SlideCleaner()

    in_target = Path(args.input)
    remove_nums = not args.keep_slide_numbers
    remove_footer = not args.keep_footer_text
    default_folder_name = "preview" if args.preview else "clean"
    prefix = "preview_" if args.preview else "clean_"

    if in_target.is_dir():
        out_target = Path(args.output) if args.output else in_target / default_folder_name
        out_target.mkdir(parents=True, exist_ok=True)
        for pdf_file in sorted(in_target.glob("*.pdf")):
            if pdf_file.name.startswith("clean_") or pdf_file.name.startswith("preview_"):
                continue
            out_pdf = out_target / f"{prefix}{pdf_file.name}"
            cleaner.clean_pdf(
                str(pdf_file),
                str(out_pdf),
                preview_mode=args.preview,
                remove_slide_numbers=remove_nums,
                remove_footer_text=remove_footer,
            )
    elif in_target.is_file():
        if args.output:
            out_arg = Path(args.output)
            if out_arg.is_dir() or str(args.output).endswith("/"):
                out_arg.mkdir(parents=True, exist_ok=True)
                out_pdf = out_arg / f"{prefix}{in_target.name}"
            else:
                out_pdf = out_arg
        else:
            out_dir = in_target.parent / default_folder_name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_pdf = out_dir / f"{prefix}{in_target.name}"
        cleaner.clean_pdf(
            str(in_target),
            str(out_pdf),
            preview_mode=args.preview,
            remove_slide_numbers=remove_nums,
            remove_footer_text=remove_footer,
        )
    else:
        print(f"Fehler: Pfad '{args.input}' existiert nicht.")
        sys.exit(1)


if __name__ == "__main__":
    main()
