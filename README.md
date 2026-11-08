# upb-lecture-slide-declutterer

Python-Tool zum automatischen Entfernen wiederkehrender Design- und Layout-Elemente aus Vorlesungsfolien (PDF) der Universität Paderborn.

## Funktionen

- **UPB-Vorlagen-Erkennung:** Klassifiziert Folien anhand der Referenzvorlagen in `templates/` (z. B. *Title slide*, *Agenda*, *Separation page*, *Content*, *Contact*).
- **Custom-Template-Erkennung:** Erkennt auch auf abweichenden Lehrstuhl-Vorlagen automatisch sich wiederholende Elemente über alle Seiten hinweg.
- **Gezielte Bereinigung:** Entfernt UPB- und Lehrstuhl-Logos, farbige Deko-Dreiecke, Kopf-/Fußzeilenbalken, Hintergrund-Wasserzeichen, Fußzeilentexte sowie Foliennummern, ohne den eigentlichen Folieninhalt zu beschädigen.

## Voraussetzungen & Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pymupdf pillow numpy
```

## Verwendung

### 1. Einzelne PDF-Datei bereinigen

```bash
python clean_slides.py -i datei.pdf
```
Speichert die bereinigte Datei standardmäßig unter `clean/clean_datei.pdf`.

### 2. Ganzen Ordner bereinigen

```bash
python clean_slides.py -i pfad/zum/ordner
```
Verarbeitet alle PDFs im Ordner und legt die Ergebnisse in `pfad/zum/ordner/clean/` ab.

### 3. Vorschau-Modus (rote Markierungsrahmen statt Löschen)

```bash
python clean_slides.py -i datei.pdf --preview
```
Erzeugt eine Prüfdatei mit eingezeichneten Redaction-Bereichen und erkanntem Folientyp unter `preview/preview_datei.pdf`.

## Optionen

| Parameter | Beschreibung |
| :--- | :--- |
| `-i`, `--input` | Pfad zu einer einzelnen PDF-Datei oder einem Ordner mit PDFs |
| `-o`, `--output` | Optionaler Ausgabepfad (Datei oder Ordner). Standard: Unterordner `clean/` bzw. `preview/` |
| `--preview` | Zeichnet die erkannten Löschbereiche als rote Rahmen ein, ohne Inhalte zu entfernen |
| `--keep-slide-numbers` | Behält die Foliennummern auf den Folien bei |
| `--keep-footer-text` | Behält den Fußzeilentext (Veranstaltung, Dozent, Semester) bei |

