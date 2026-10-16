from __future__ import annotations

import datetime
import os
from fractions import Fraction

from PIL.ExifTags import TAGS

from core.constants import EXIF_IFD, GPS_IFD, MODE_NAMES
from core.document import Document
from utils.helpers import human_size


def _clean_value(v):
    if isinstance(v, bytes):
        if len(v) > 80:
            return f"<binary data: {len(v):,} bytes>"
        v = v.decode("utf-8", "ignore").strip("\x00 \t\r\n")
    elif isinstance(v, (tuple, list)):
        v = ", ".join(str(_clean_value(x)) for x in v)
    else:
        v = str(v)
    v = v.strip()
    return (v[:200] + "…") if len(v) > 200 else (v or None)


def _gps_deg(vals, ref):
    try:
        d, m, s = (float(x) for x in vals)
        deg = d + m / 60 + s / 3600
        if isinstance(ref, bytes):
            ref = ref.decode(errors="ignore")
        return -deg if str(ref).upper().startswith(("S", "W")) else deg
    except Exception:
        return None


def exif_sections(exif):
    camera, gps_rows, other = [], [], []
    if not exif:
        return camera, gps_rows, other
    merged = {}
    try:
        merged.update(dict(exif.items()))
        merged.update(exif.get_ifd(EXIF_IFD))
    except Exception:
        pass
    try:
        merged.update({f"GPS {k}": v for k, v in exif.get_ifd(GPS_IFD).items()})
    except Exception:
        pass
    named = {TAGS.get(k, f"Tag 0x{k:04X}"): v for k, v in merged.items()}

    def num(v):
        try:
            return float(v)
        except Exception:
            return None

    def fmt_exposure(v):
        f = num(v)
        if f is None: return _clean_value(v)
        return f"1/{round(1 / f)} s" if 0 < f < 1 else f"{f:g} s"

    nice = [
        ("Camera make", "Make", None), ("Camera model", "Model", None), ("Lens", "LensModel", None),
        ("Date taken", "DateTimeOriginal", None), ("Exposure time", "ExposureTime", fmt_exposure),
        ("Aperture", "FNumber", lambda v: f"f/{num(v):g}" if num(v) is not None else _clean_value(v)),
        ("ISO", "ISOSpeedRatings", None), ("Focal length", "FocalLength",
         lambda v: f"{num(v):g} mm" if num(v) is not None else _clean_value(v)),
        ("Focal length (35 mm eq.)", "FocalLengthIn35mmFilm", lambda v: f"{v} mm"),
        ("Exposure bias", "ExposureBiasValue",
         lambda v: f"{num(v):+.2f} EV" if num(v) is not None else _clean_value(v)),
        ("Flash", "Flash", lambda v: "Fired" if int(v) & 1 else "Did not fire"),
        ("Software", "Software", None), ("Artist", "Artist", None), ("Copyright", "Copyright", None),
    ]
    used = set()
    for label, tag, fmt in nice:
        if tag in named:
            used.add(tag)
            try:
                val = fmt(named[tag]) if fmt else _clean_value(named[tag])
            except Exception:
                val = _clean_value(named[tag])
            if val:
                camera.append((label, val))
    for tag, v in sorted(named.items()):
        if tag in used:
            continue
        val = _clean_value(v)
        if val:
            other.append((tag, val))
    try:
        g = exif.get_ifd(GPS_IFD)
        if g:
            lat, lon = _gps_deg(g.get(2), g.get(1)), _gps_deg(g.get(4), g.get(3))
            if lat is not None and lon is not None:
                gps_rows.append(("Coordinates", f"{lat:.6f}, {lon:.6f}"))
            if 6 in g and num(g[6]) is not None:
                gps_rows.append(("Altitude", f"{num(g[6]):.1f} m"))
    except Exception:
        pass
    return camera, gps_rows, other


def _embedded_metadata(info):
    rows = []
    for key, value in sorted(info.items(), key=lambda item: str(item[0]).lower()):
        value = _clean_value(value)
        if value:
            rows.append((str(key), value))
    return rows


def collect_details(doc: Document, folder_pos: str):
    img, meta, path = doc.image, doc.meta, doc.path
    sections = []
    rows = []
    if path:
        rows += [("Name", os.path.basename(path)), ("Folder", os.path.dirname(path))]
        try:
            st = os.stat(path)
            rows.append(("File size", f"{human_size(st.st_size)}  ({st.st_size:,} bytes)"))
            rows.append(("Modified", datetime.datetime.fromtimestamp(st.st_mtime)
                         .strftime("%Y-%m-%d %H:%M:%S")))
        except OSError:
            pass
    if meta:
        rows.append(("Format", meta.format or "Unknown"))
    if folder_pos:
        rows.append(("Position in folder", folder_pos))
    sections.append(("File", rows))

    w, h = img.size
    fr = Fraction(w, h).limit_denominator(30)
    ratio = f"{fr.numerator}:{fr.denominator}" if fr.denominator <= 30 and \
        abs(fr.numerator / fr.denominator - w / h) < 0.01 else f"{w / h:.3f}:1"
    rows = [("Dimensions", f"{w} × {h} pixels"), ("Megapixels", f"{w * h / 1e6:.2f} MP"),
            ("Aspect ratio", ratio)]
    if meta:
        if meta.orig_size != img.size:
            rows.append(("Original dimensions", f"{meta.orig_size[0]} × {meta.orig_size[1]} pixels"))
        rows.append(("Colour mode (file)", MODE_NAMES.get(meta.mode, meta.mode)))
        rows.append(("Transparency", "Yes" if img.mode == "RGBA" else "No"))
        rows.append(("Frames", f"{meta.frames} (animated — only the first frame is shown)"
                     if meta.animated else str(meta.frames)))
        if meta.dpi:
            rows.append(("Resolution", f"{meta.dpi[0]:g} × {meta.dpi[1]:g} dpi"))
        rows.append(("Embedded colour profile", "Yes" if meta.has_icc else "No"))
    sections.append(("Image", rows))
    sections.append(("Editing", [("Unsaved changes", "Yes" if doc.dirty else "No"),
                                 ("Undo steps available", str(doc.undo_depth))]))
    if meta:
        cam, gps, other = exif_sections(meta.exif)
        sections += [
            ("Camera & exposure", cam),
            ("Location (GPS)", gps),
            ("EXIF metadata (all tags)", other),
            ("Embedded metadata", _embedded_metadata(meta.info)),
        ]
    return sections
