import json
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DOWNLOAD_ROOT = Path(os.getenv("MOVIEBOX_DOWNLOAD_ROOT", "/downloads"))
MAX_WORKERS = int(os.getenv("MOVIEBOX_MAX_WORKERS", "2"))
DEFAULT_TIMEOUT = int(os.getenv("MOVIEBOX_TIMEOUT", "7200"))

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = Lock()

app = FastAPI(
    title="Moviebox API Service",
    version="0.1.0",
    description="HTTP wrapper around moviebox-api CLI for ARR orchestrators.",
)


class DetailsRequest(BaseModel):
    title: str = Field(min_length=1)
    year: int = 0
    subject_type: str = "all"
    yes: bool = True
    full: bool = False
    timeout: int = 90


class MovieDownloadRequest(BaseModel):
    title: str = Field(min_length=1)
    year: int = 0
    subject_type: str = "movies"
    quality: str = "720p"
    dub: str = "Original"
    languages: list[str] = Field(default_factory=lambda: ["English"])
    download_dir: str = "/downloads/movies"
    caption_dir: str = "/downloads/subtitles"
    caption: bool = True
    ignore_missing_caption: bool = True
    test: bool = False
    background: bool = True
    timeout: int = DEFAULT_TIMEOUT


class SeriesDownloadRequest(BaseModel):
    title: str = Field(min_length=1)
    year: int = 0
    season: int = Field(default=1, ge=1)
    episode: int = Field(default=1, ge=1)
    limit: int = 1
    quality: str = "720p"
    dub: str = "Original"
    languages: list[str] = Field(default_factory=lambda: ["English"])
    download_dir: str = "/downloads/series"
    caption_dir: str = "/downloads/subtitles"
    format: Literal["standard", "group", "struct"] = "standard"
    caption: bool = True
    ignore_missing_caption: bool = True
    auto_mode: bool = False
    test: bool = False
    background: bool = True
    timeout: int = DEFAULT_TIMEOUT


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: str) -> str:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = DOWNLOAD_ROOT / resolved
    resolved.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def parse_first_json(text: str) -> Any | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value
        except json.JSONDecodeError:
            continue
    return None


def run_moviebox(args: list[str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=str(DOWNLOAD_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = {
        "command": args,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "json": parse_first_json(completed.stdout),
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(output, ensure_ascii=False))
    return output


def create_job(command: list[str], timeout: int) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "queued",
        "command": command,
        "created_at": utc_now(),
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "json": None,
        "error": None,
    }
    with jobs_lock:
        jobs[job_id] = job
    executor.submit(run_job, job_id, command, timeout)
    return job


def run_job(job_id: str, command: list[str], timeout: int) -> None:
    with jobs_lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = utc_now()
    try:
        result = run_moviebox(command, timeout)
        with jobs_lock:
            jobs[job_id].update(result)
            jobs[job_id]["status"] = "succeeded"
            jobs[job_id]["ended_at"] = utc_now()
    except Exception as exc:
        error_text = str(exc)
        parsed_error = parse_first_json(error_text)
        with jobs_lock:
            if isinstance(parsed_error, dict):
                jobs[job_id].update(parsed_error)
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = error_text
            jobs[job_id]["ended_at"] = utc_now()


def details_command(payload: DetailsRequest) -> list[str]:
    command = ["moviebox-v3", "item-details", payload.title, "-s", payload.subject_type]
    if payload.year:
        command += ["-y", str(payload.year)]
    if payload.yes:
        command.append("-Y")
    command.append("-J")
    if payload.full:
        command.append("-F")
    return command


def movie_download_command(payload: MovieDownloadRequest) -> list[str]:
    download_dir = ensure_dir(payload.download_dir)
    caption_dir = ensure_dir(payload.caption_dir)
    command = [
        "moviebox-v3",
        "download-movie",
        payload.title,
        "-s",
        payload.subject_type,
        "-q",
        payload.quality,
        "-u",
        payload.dub,
        "-d",
        download_dir,
        "-D",
        caption_dir,
        "-Y",
    ]
    if payload.year:
        command += ["-y", str(payload.year)]
    for language in payload.languages:
        command += ["-x", language]
    if not payload.caption:
        command.append("--no-caption")
    if payload.ignore_missing_caption:
        command.append("-I")
    if payload.test:
        command.append("-T")
    return command


def series_download_command(payload: SeriesDownloadRequest) -> list[str]:
    download_dir = ensure_dir(payload.download_dir)
    caption_dir = ensure_dir(payload.caption_dir)
    command = [
        "moviebox-v3",
        "download-series",
        payload.title,
        "-s",
        str(payload.season),
        "-e",
        str(payload.episode),
        "-l",
        str(payload.limit),
        "-q",
        payload.quality,
        "-u",
        payload.dub,
        "-d",
        download_dir,
        "-D",
        caption_dir,
        "-f",
        payload.format,
        "-Y",
    ]
    if payload.year:
        command += ["-y", str(payload.year)]
    for language in payload.languages:
        command += ["-x", language]
    if not payload.caption:
        command.append("--no-caption")
    if payload.ignore_missing_caption:
        command.append("-I")
    if payload.auto_mode:
        command.append("-A")
    if payload.test:
        command.append("-T")
    return command


def sync_or_background(
    command: list[str], timeout: int, background: bool
) -> dict[str, Any]:
    if background:
        return {"job": create_job(command, timeout)}
    try:
        return run_moviebox(command, timeout)
    except RuntimeError as exc:
        parsed = parse_first_json(str(exc))
        raise HTTPException(status_code=502, detail=parsed or str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"Command timed out: {exc}") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "download_root": str(DOWNLOAD_ROOT),
        "max_workers": MAX_WORKERS,
    }


@app.post("/movies/details")
def movie_details(payload: DetailsRequest) -> dict[str, Any]:
    if not payload.subject_type or payload.subject_type == "all":
        payload.subject_type = "movies"
    return sync_or_background(details_command(payload), payload.timeout, False)


@app.post("/series/details")
def series_details(payload: DetailsRequest) -> dict[str, Any]:
    payload.subject_type = "tv_series"
    return sync_or_background(details_command(payload), payload.timeout, False)


@app.post("/movies/download")
def movie_download(payload: MovieDownloadRequest) -> dict[str, Any]:
    return sync_or_background(
        movie_download_command(payload), payload.timeout, payload.background
    )


@app.post("/series/download")
def series_download(payload: SeriesDownloadRequest) -> dict[str, Any]:
    return sync_or_background(
        series_download_command(payload), payload.timeout, payload.background
    )


@app.get("/jobs")
def list_jobs() -> dict[str, Any]:
    with jobs_lock:
        return {"jobs": list(jobs.values())}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
