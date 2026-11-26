"""Import item photographs into ERPNext and set Item.image (idempotent).

Runs inside the bench as Administrator (see import-item-images.ps1). Every file in the image folder is
matched to an Item by exact code, exact name, normalised name or the approved manual mapping in
item_images.yaml. Ambiguous and unmatched files are never assigned. Each match is uploaded as a public
File attached to the Item's image field, and Item.image is set to that file's URL.

Usage: python import_item_images.py <image_dir> <item_images.yaml> <report_dir> [--dry-run]
"""
import json
import os
import re
import sys
import unicodedata

import frappe
import yaml

img_dir, map_path, report_dir = sys.argv[1], sys.argv[2], sys.argv[3]
dry_run = "--dry-run" in sys.argv[4:]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def match(stem, items, mapping, fn):
    if fn in mapping.get("manual", {}):
        code = mapping["manual"][fn]
        if code not in items:
            return None, "manual", "mapped item %s does not exist" % (code,)
        return code, "manual (approved)", ""
    if fn in mapping.get("hold", {}):
        return None, "held", mapping["hold"][fn]
    for label, test in (
        ("exact code", lambda c, n: c.lower() == stem.lower()),
        ("exact name", lambda c, n: n.lower() == stem.lower()),
        ("normalised name", lambda c, n: norm(stem) in (norm(c), norm(n))),
    ):
        hits = [c for c, n in items.items() if test(c, n)]
        if len(hits) == 1:
            return hits[0], label, ""
        if len(hits) > 1:
            return None, "ambiguous", "%s matches %s" % (label, ", ".join(sorted(hits)))
    return None, "unmatched", "no item code or name matches the filename"


def attach(code, fn, path):
    item = frappe.get_doc("Item", code)
    if item.image:
        existing = frappe.db.get_value(
            "File", {"file_url": item.image, "attached_to_doctype": "Item", "attached_to_name": code}, "file_name")
        if existing == fn:
            return item.image, "unchanged"
    with open(path, "rb") as fh:
        content = fh.read()
    f = frappe.get_doc({
        "doctype": "File",
        "file_name": fn,
        "attached_to_doctype": "Item",
        "attached_to_name": code,
        "attached_to_field": "image",
        "is_private": 0,
        "content": content,
    })
    f.insert()
    item.image = f.file_url
    item.save()
    if not os.path.exists(f.get_full_path()):
        raise Exception("uploaded file missing on disk: %s" % (f.file_url,))
    return f.file_url, "imported"


frappe.init(site=os.environ.get("FRAPPE_SITE", "frontend"), sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
with open(map_path, encoding="utf-8") as fh:
    mapping = yaml.safe_load(fh) or {}
items = {r.name: r.item_name or "" for r in frappe.get_all("Item", fields=["name", "item_name"], filters={"disabled": 0})}

rows = []
for fn in sorted(os.listdir(img_dir)):
    stem, ext = os.path.splitext(fn)
    if ext.lower() not in IMAGE_EXT:
        continue
    code, how, note = match(stem, items, mapping, fn)
    row = {"file": fn, "item_code": code or "", "item_name": items.get(code, "") if code else "",
           "match": how, "upload": "skipped", "file_url": "", "error": note}
    if code and not dry_run:
        try:
            row["file_url"], row["upload"] = attach(code, fn, os.path.join(img_dir, fn))
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            row["upload"] = "failed"
            row["error"] = str(e)[:300]
    elif code:
        row["upload"] = "dry run"
    rows.append(row)
frappe.destroy()

os.makedirs(report_dir, exist_ok=True)
with open(os.path.join(report_dir, "item-image-import.json"), "w", encoding="utf-8") as fh:
    json.dump(rows, fh, indent=1)
counts = {}
for r in rows:
    counts[r["upload"]] = counts.get(r["upload"], 0) + 1
lines = ["# Item image import report", "",
         "Files: %d. %s" % (len(rows), ", ".join("%s: %d" % kv for kv in sorted(counts.items()))), "",
         "| Image file | Item code | Item name | Match | Upload | File URL | Error or note |", "|---|---|---|---|---|---|---|"]
for r in rows:
    lines.append("| %s |" % " | ".join(str(r[k]).replace("|", "/") for k in ("file", "item_code", "item_name", "match", "upload", "file_url", "error")))
with open(os.path.join(report_dir, "item-image-import.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
for r in rows:
    print("%-28s %-16s %-18s %-9s %s" % (r["file"][:28], r["item_code"], r["match"], r["upload"], r["error"][:60]))
if any(r["upload"] == "failed" for r in rows):
    sys.exit(1)
