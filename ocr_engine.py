try:
    import bidi
    if not hasattr(bidi, "get_display"):
        from bidi.algorithm import get_display
        bidi.get_display = get_display
except Exception:
    pass

from difflib import SequenceMatcher

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = " ".join(text.split())
    clean = ""
    for c in text:
        if c.isalnum() or c in "çğışöüÇĞİŞÖÜ ":
            clean += c
    return clean.strip()


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na, nb = normalize_text(a), normalize_text(b)
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def process_image(image_path: str, reader, mode: str = "hybrid") -> tuple:
    from PIL import Image
    import numpy as np

    text = ""
    img = None
    if mode != "visual" and reader is not None:
        try:
            img = Image.open(image_path)
            img_rgb = img.convert("RGB")
            img_np = np.array(img_rgb)
            lines = reader.readtext(img_np, detail=0, paragraph=True)
            text = " ".join(lines).strip()
        except Exception as e:
            raise e

    dhash_val = None
    if mode != "text":
        try:
            if img is None:
                img = Image.open(image_path)
            img_gray = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = np.array(img_gray)
            diff = pixels[:, 1:] > pixels[:, :-1]
            dhash_val = diff.tolist()
        except Exception:
            pass

    return text, dhash_val


def dhash_similarity(hash1: list, hash2: list) -> float:
    if not hash1 or not hash2:
        return 0.0
    import numpy as np
    try:
        arr1 = np.array(hash1, dtype=bool)
        arr2 = np.array(hash2, dtype=bool)
        if arr1.shape != arr2.shape:
            return 0.0
        return float(1.0 - (np.count_nonzero(arr1 != arr2) / arr1.size))
    except Exception:
        return 0.0


def check_is_similar(item1: dict, item2: dict, mode: str = "hybrid") -> bool:
    text1 = item1.get("text", "")
    text2 = item2.get("text", "")

    has_text1 = len(normalize_text(text1)) >= 3
    has_text2 = len(normalize_text(text2)) >= 3

    text_sim = 0.0
    if mode != "visual" and has_text1 and has_text2:
        text_sim = similarity(text1, text2)
        if mode == "text" and text_sim >= 0.70:
            return True

    hash1 = item1.get("dhash")
    hash2 = item2.get("dhash")

    visual_sim = 0.0
    if mode != "text" and hash1 is not None and hash2 is not None:
        visual_sim = dhash_similarity(hash1, hash2)
        if mode == "visual" and visual_sim >= 0.88:
            return True

    if mode == "hybrid":
        if text_sim >= 0.70:
            return True
        if visual_sim >= 0.88:
            return True
        if has_text1 and has_text2:
            if text_sim >= 0.55 and visual_sim >= 0.82:
                return True

    return False


def find_best_index(paths: list) -> int:
    """Return index of the highest-resolution image (largest pixel area)."""
    from PIL import Image

    best_idx = 0
    best_area = -1
    for i, path in enumerate(paths):
        if not path:
            continue
        try:
            with Image.open(path) as img:
                area = img.width * img.height
                if area > best_area:
                    best_area = area
                    best_idx = i
        except Exception:
            pass
    return best_idx


def find_groups(results: list, threshold: float = None, mode: str = "hybrid") -> dict:
    assigned = set()
    groups = []
    
    for i, r in enumerate(results):
        if i in assigned:
            continue
        group = [r]
        assigned.add(i)
        for j, s in enumerate(results):
            if j in assigned or j == i:
                continue
            if check_is_similar(r, s, mode):
                group.append(s)
                assigned.add(j)
        groups.append(group)

    duplicates = [g for g in groups if len(g) > 1]
    unique = [g[0] for g in groups if len(g) == 1]

    has_paths = any(r.get("path") for r in results)

    def _group_paths(group):
        return [item.get("path", "") for item in group]

    return {
        "total": len(results),
        "duplicate_group_count": len(duplicates),
        "unique_count": len(unique),
        "error_count": 0,
        "has_paths": has_paths,
        "duplicate_groups": [
            {
                "files": [item["file"] for item in group],
                "paths": _group_paths(group) if has_paths else [],
                "best_index": find_best_index(_group_paths(group)) if has_paths else 0,
                "deleted": False,
                "kept_file": None,
                "text_preview": (group[0]["text"] or "")[:200],
                "full_text": group[0]["text"] or "",
            }
            for group in duplicates
        ],
        "unique_items": [
            {
                "file": item["file"],
                "path": item.get("path", ""),
                "text_preview": (item["text"] or "")[:200],
            }
            for item in unique
        ],
    }


def generate_txt_report(job: dict) -> str:
    results = job.get("results") or {}
    errors = job.get("errors") or []
    lines = []
    lines.append("=" * 60)
    lines.append("BENZER METİN BULUCU — RAPOR")
    lines.append("=" * 60)
    lines.append(f"Toplam dosya      : {results.get('total', 0)}")
    lines.append(f"Tekrar grubu      : {results.get('duplicate_group_count', 0)}")
    lines.append(f"Benzersiz metin   : {results.get('unique_count', 0)}")
    lines.append(f"Hata              : {len(errors)}")
    lines.append("")

    groups = results.get("duplicate_groups") or []
    if groups:
        lines.append("-" * 60)
        lines.append(f"TEKRAR EDEN METİNLER VE GÖRSELLER ({len(groups)} grup)")
        lines.append("-" * 60)
        for i, group in enumerate(groups, 1):
            status = " [SİLİNDİ]" if group.get("deleted") else ""
            lines.append(f"\nGrup {i} ({len(group['files'])} dosya){status}:")
            for fi, f in enumerate(group["files"]):
                kept = group.get("best_index", 0) == fi
                lines.append(f"  {'★' if kept else '-'} {f}")
            preview = (group["text_preview"] or "").replace("\n", " ")
            if preview:
                lines.append(f"  Metin: {preview[:150]}")

    unique = results.get("unique_items") or []
    if unique:
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"BENZERSİZ METİNLER VE GÖRSELLER ({len(unique)} adet)")
        lines.append("-" * 60)
        for item in unique:
            lines.append(f"\n  Dosya : {item['file']}")
            preview = (item["text_preview"] or "").replace("\n", " ")
            if preview:
                lines.append(f"  Metin : {preview[:120]}")

    if errors:
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"HATALAR ({len(errors)} adet)")
        lines.append("-" * 60)
        for err in errors:
            lines.append(f"  - {err}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
