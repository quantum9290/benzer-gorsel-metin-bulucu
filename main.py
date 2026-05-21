import asyncio
import io
import json
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import ocr_engine

try:
    import torch
    _TORCH = True
except ImportError:
    _TORCH = False

TEMP_DIR = Path("temp")

readers_cache: dict = {}
_reader_lock = threading.Lock()

jobs: dict = {}

ocr_semaphore: asyncio.Semaphore = None  # set in lifespan


def _gpu_available() -> bool:
    return _TORCH and torch.cuda.is_available()


def _gpu_name() -> str | None:
    if _TORCH and torch.cuda.is_available():
        return torch.cuda.get_device_name(0)
    return None


def _clean_old_temp_dirs():
    try:
        now = time.time()
        if TEMP_DIR.exists():
            for p in TEMP_DIR.iterdir():
                if p.is_dir():
                    mtime = p.stat().st_mtime
                    if now - mtime > 1800:  # 30 minutes
                        shutil.rmtree(p, ignore_errors=True)
    except Exception as exc:
        print(f"[Cleanup] Error cleaning old temp dirs: {exc}")



def _get_or_init_reader(languages: tuple, use_gpu: bool):
    import easyocr

    key = (languages, use_gpu)
    if key in readers_cache:
        return readers_cache[key]
    with _reader_lock:
        if key not in readers_cache:
            readers_cache[key] = easyocr.Reader(list(languages), gpu=use_gpu)
    return readers_cache[key]


async def _preload_default_reader():
    loop = asyncio.get_event_loop()
    try:
        gpu = _gpu_available()
        await loop.run_in_executor(None, _get_or_init_reader, ("tr", "en"), gpu)
        print("[OCR] Default reader (tr+en) loaded.")
    except Exception as exc:
        print(f"[OCR] Preload failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_semaphore
    ocr_semaphore = asyncio.Semaphore(1)
    TEMP_DIR.mkdir(exist_ok=True)
    asyncio.create_task(_preload_default_reader())
    yield


app = FastAPI(title="Benzer Görsel ve Metin Bulucu", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Routes ──────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/gpu-status")
async def gpu_status():
    return {"available": _gpu_available(), "device": _gpu_name()}


@app.get("/check-folder")
async def check_folder(path: str):
    folder = Path(path)
    if not folder.exists():
        return {"valid": False, "error": "Klasör bulunamadı"}
    if not folder.is_dir():
        return {"valid": False, "error": "Bu bir klasör değil"}
    count = sum(
        1 for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in ocr_engine.SUPPORTED_EXTENSIONS
    )
    return {"valid": True, "count": count}


@app.post("/select-folder")
async def select_folder():
    import tkinter as tk
    from tkinter import filedialog
    import asyncio

    def _ask_dir():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        directory = filedialog.askdirectory(title="Analiz Edilecek Klasörü Seçin")
        root.destroy()
        return directory

    loop = asyncio.get_event_loop()
    selected_dir = await loop.run_in_executor(None, _ask_dir)
    return {"folder_path": selected_dir}


@app.post("/analyze")
async def analyze(
    files: list[UploadFile] = File(...),
    threshold: float | None = Form(None),
    languages: str = Form("tr+en"),
    use_gpu: str = Form("auto"),
    mode: str = Form("hybrid"),
):
    if not files:
        raise HTTPException(status_code=400, detail="Hiç dosya seçilmedi.")

    _clean_old_temp_dirs()

    job_id = str(uuid.uuid4())
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    file_paths = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in ocr_engine.SUPPORTED_EXTENSIONS:
            continue
        dest = job_dir / upload.filename
        dest.write_bytes(await upload.read())
        file_paths.append(str(dest))

    if not file_paths:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Desteklenen fotoğraf bulunamadı.")

    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total": len(file_paths),
        "processed": 0,
        "current_file": "",
        "errors": [],
        "results": None,
        "folder_path": str(job_dir),
        "folder_mode": False,
        "cleanup_dir": str(job_dir),
        "mode": mode,
    }

    asyncio.create_task(_run_ocr_job(job_id, file_paths, threshold, languages, use_gpu))
    return {"job_id": job_id, "total": len(file_paths)}


@app.post("/analyze-folder")
async def analyze_folder(
    folder_path: str = Form(...),
    threshold: float | None = Form(None),
    languages: str = Form("tr+en"),
    use_gpu: str = Form("auto"),
    mode: str = Form("hybrid"),
):
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Klasör bulunamadı veya geçersiz yol.")

    _clean_old_temp_dirs()

    file_paths = sorted(
        str(f) for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in ocr_engine.SUPPORTED_EXTENSIONS
    )
    if not file_paths:
        raise HTTPException(status_code=400, detail="Klasörde desteklenen fotoğraf bulunamadı.")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total": len(file_paths),
        "processed": 0,
        "current_file": "",
        "errors": [],
        "results": None,
        "folder_path": str(folder),
        "folder_mode": True,
        "cleanup_dir": None,
        "mode": mode,
    }

    asyncio.create_task(_run_ocr_job(job_id, file_paths, threshold, languages, use_gpu))
    return {"job_id": job_id, "total": len(file_paths)}


async def _run_ocr_job(
    job_id: str,
    file_paths: list,
    threshold: float | None,
    lang_key: str,
    use_gpu_str: str,
):
    async with ocr_semaphore:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _sync_ocr, job_id, file_paths, threshold, lang_key, use_gpu_str
        )


def _sync_ocr(
    job_id: str,
    file_paths: list,
    threshold: float | None,
    lang_key: str,
    use_gpu_str: str,
):
    job = jobs[job_id]
    job["status"] = "processing"
    mode = job.get("mode", "hybrid")

    reader = None
    if mode != "visual":
        if use_gpu_str == "auto":
            use_gpu = _gpu_available()
        elif use_gpu_str == "gpu":
            use_gpu = True
        else:
            use_gpu = False

        lang_map = {"tr+en": ("tr", "en"), "tr": ("tr",), "en": ("en",)}
        languages = lang_map.get(lang_key, ("tr", "en"))

        try:
            reader = _get_or_init_reader(languages, use_gpu)
        except Exception as exc:
            job["status"] = "failed"
            job["errors"].append(f"OCR başlatma hatası: {exc}")
            return

    results = []
    for i, path in enumerate(file_paths):
        fname = Path(path).name
        job["current_file"] = fname
        try:
            text, dhash_val = ocr_engine.process_image(path, reader, mode=mode)
            results.append({
                "file": fname,
                "path": path,
                "text": text,
                "dhash": dhash_val,
            })
        except Exception as exc:
            job["errors"].append(f"{fname}: {exc}")
        job["processed"] = i + 1

    grouped = ocr_engine.find_groups(results, mode=mode)
    grouped["total"] = len(file_paths)
    grouped["error_count"] = len(job["errors"])
    job["results"] = grouped
    job["status"] = "completed"


@app.get("/progress/{job_id}")
async def progress(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")

    async def event_stream():
        last_processed = -1
        last_status = ""
        last_send = 0.0

        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job bulunamadı'})}\n\n"
                break

            now = time.monotonic()
            changed = (
                job["processed"] != last_processed
                or job["status"] != last_status
            )
            if changed or (now - last_send) >= 2.0:
                last_processed = job["processed"]
                last_status = job["status"]
                last_send = now
                total = job["total"]
                pct = int(job["processed"] / total * 100) if total > 0 else 0
                payload = {
                    "status": job["status"],
                    "total": total,
                    "processed": job["processed"],
                    "percent": pct,
                    "current_file": job["current_file"],
                    "errors": job["errors"],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if job["status"] in ("completed", "failed"):
                break

            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/image/{job_id}/{filename}")
async def get_image(job_id: str, filename: str, thumb: bool = False):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")

    folder = job.get("folder_path")
    if not folder:
        raise HTTPException(status_code=404, detail="Görsel bu iş için mevcut değil.")

    # Path traversal guard
    folder_resolved = Path(folder).resolve()
    img_path = (folder_resolved / filename).resolve()
    if not str(img_path).startswith(str(folder_resolved)):
        raise HTTPException(status_code=403, detail="Erişim reddedildi.")
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Görsel bulunamadı.")

    if thumb:
        from PIL import Image as PILImage

        with PILImage.open(str(img_path)) as img:
            img = img.convert("RGB")
            img.thumbnail((300, 300))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82, optimize=True)
            buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=3600"},
        )

    return FileResponse(str(img_path))


@app.delete("/group/{job_id}/{group_index}")
async def delete_group(job_id: str, group_index: int):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analiz tamamlanmadı.")

    groups = (job.get("results") or {}).get("duplicate_groups", [])
    if group_index < 0 or group_index >= len(groups):
        raise HTTPException(status_code=404, detail="Grup bulunamadı.")

    group = groups[group_index]
    if group.get("deleted"):
        return {"deleted": 0, "kept": group.get("kept_file"), "message": "Zaten silindi."}

    best_idx = group.get("best_index", 0)
    paths = group.get("paths", [])
    files = group.get("files", [])

    deleted, failed = [], []
    for i, (path, fname) in enumerate(zip(paths, files)):
        if i == best_idx or not path:
            continue
        try:
            Path(path).unlink(missing_ok=True)
            deleted.append(fname)
        except Exception as exc:
            failed.append(f"{fname}: {exc}")

    group["deleted"] = True
    group["kept_file"] = files[best_idx] if files else None

    return {
        "deleted": len(deleted),
        "deleted_files": deleted,
        "kept": group["kept_file"],
        "failed": failed,
    }


@app.delete("/all-duplicates/{job_id}")
async def delete_all_duplicates(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analiz tamamlanmadı.")

    groups = (job.get("results") or {}).get("duplicate_groups", [])
    total_deleted, failed = 0, []

    for group in groups:
        if group.get("deleted"):
            continue
        best_idx = group.get("best_index", 0)
        paths = group.get("paths", [])
        files = group.get("files", [])

        for i, (path, fname) in enumerate(zip(paths, files)):
            if i == best_idx or not path:
                continue
            try:
                Path(path).unlink(missing_ok=True)
                total_deleted += 1
            except Exception as exc:
                failed.append(f"{fname}: {exc}")

        group["deleted"] = True
        group["kept_file"] = files[best_idx] if files else None

    return {
        "deleted": total_deleted,
        "groups_processed": len(groups),
        "failed": failed,
    }


@app.get("/report/{job_id}")
async def report(job_id: str, format: str = "json"):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analiz henüz tamamlanmadı.")

    short = job_id[:8]
    if format == "txt":
        content = ocr_engine.generate_txt_report(job)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="rapor_{short}.txt"'},
        )

    if job["results"]:
        job["results"]["folder_mode"] = job.get("folder_mode", False)

    body = json.dumps(job["results"], ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        iter([body]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rapor_{short}.json"'},
    )
