#!/usr/bin/env python3
"""Fail-closed, real-browser HFVI replay verifier for the generated frontend.

The verifier deliberately builds the checked-in Vite/Leafer application, serves
that build with the checked-in tape, launches the locked Chrome-for-Testing
version, and compares its actual screenshot to the approved PNG baseline.  It
does not treat a synthetic renderer or a host-side model as visual evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import select
import struct
import subprocess
import signal
import sys
import tempfile
import threading
import time
import urllib.parse
import zlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


TAPE_ID = "baseline"
TAPE_SCHEMA_VERSION = "1.0.0"
GOLDEN_SCHEMA_VERSION = "2.0.0"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid HFVI JSON {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"HFVI JSON root must be an object: {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.replace(path)


def replay_state(tape: dict[str, Any]) -> dict[str, Any]:
    if tape.get("schemaVersion") != TAPE_SCHEMA_VERSION or tape.get("tapeId") != TAPE_ID:
        fail("HFVI tape has an unsupported schemaVersion or tapeId")
    initial = tape.get("initial")
    events = tape.get("events")
    if not isinstance(initial, dict) or not isinstance(events, list):
        fail("HFVI tape must have object initial state and array events")
    try:
        state = {
            "x": int(initial["x"]),
            "y": int(initial["y"]),
            "zoom": int(initial["zoom"]),
            "selected": str(initial["selected"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"HFVI tape initial state is invalid: {exc}")
    if not 1 <= state["zoom"] <= 400 or not state["selected"]:
        fail("HFVI initial state is invalid")
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            fail(f"HFVI event {index} must be an object with type")
        event_type = event["type"]
        try:
            if event_type == "pan":
                state["x"] += int(event["dx"])
                state["y"] += int(event["dy"])
            elif event_type == "zoom":
                state["zoom"] += int(event["delta"])
                if not 1 <= state["zoom"] <= 400:
                    fail(f"HFVI event {index} moves zoom outside 1..400")
            elif event_type == "select":
                state["selected"] = str(event["target"])
                if not state["selected"]:
                    fail(f"HFVI event {index} has an empty selection")
            else:
                fail(f"HFVI event {index} has unsupported type {event_type!r}")
        except (KeyError, TypeError, ValueError) as exc:
            fail(f"HFVI event {index} is malformed: {exc}")
    return state


def load_browser_lock(path: Path) -> dict[str, Any]:
    lock = load_object(path)
    required = {"schemaVersion", "engine", "productVersion", "archive", "viewport", "locale", "timezone", "pixelThreshold"}
    if set(lock) != required or lock.get("schemaVersion") != "1.0.0" or lock.get("engine") != "chrome-for-testing":
        fail("HFVI browser lock has an unsupported schema or unexpected fields")
    if not isinstance(lock["productVersion"], str) or not lock["productVersion"]:
        fail("HFVI browser lock productVersion must be a non-empty string")
    archive = lock["archive"]
    if not isinstance(archive, dict) or set(archive) != {"url", "contentLength", "md5"}:
        fail("HFVI browser lock archive must contain url, contentLength, and md5")
    if not isinstance(archive["url"], str) or not archive["url"].startswith("https://storage.googleapis.com/chrome-for-testing-public/"):
        fail("HFVI browser lock archive must use the Chrome-for-Testing origin")
    if not isinstance(archive["contentLength"], int) or archive["contentLength"] <= 0:
        fail("HFVI browser lock archive contentLength must be a positive integer")
    if not isinstance(archive["md5"], str) or len(archive["md5"]) != 32 or any(ch not in "0123456789abcdef" for ch in archive["md5"]):
        fail("HFVI browser lock archive md5 must be a lower-case MD5 ETag")
    viewport = lock["viewport"]
    if not isinstance(viewport, dict) or set(viewport) != {"width", "height", "deviceScaleFactor"}:
        fail("HFVI browser lock viewport must have width, height, and deviceScaleFactor")
    if not all(isinstance(viewport[key], int) and viewport[key] > 0 for key in ("width", "height", "deviceScaleFactor")):
        fail("HFVI browser lock viewport values must be positive integers")
    threshold = lock["pixelThreshold"]
    if not isinstance(threshold, dict) or set(threshold) != {"maxPixels", "maxChannelDelta"}:
        fail("HFVI browser lock pixelThreshold must have maxPixels and maxChannelDelta")
    if not all(isinstance(threshold[key], int) and threshold[key] >= 0 for key in threshold):
        fail("HFVI browser lock pixelThreshold values must be non-negative integers")
    if not isinstance(lock["locale"], str) or not isinstance(lock["timezone"], str):
        fail("HFVI browser lock locale and timezone must be strings")
    return lock


def run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    rendered = " ".join(command)
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True) as process:
        try:
            output, _ = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            fail(f"HFVI command timed out after 120 seconds: {rendered}")
        if process.returncode != 0:
            fail(f"HFVI command failed ({rendered}):\n{output}")


def build_frontend(frontend: Path) -> None:
    package_lock = frontend / "package-lock.json"
    if not package_lock.is_file():
        fail("frontend/package-lock.json is required for real-browser HFVI verification")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None or npm is None:
        fail("HFVI real-browser verification requires Node.js 22 and npm")
    version = subprocess.run([node, "--version"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if version.returncode != 0 or not version.stdout.startswith("v22."):
        fail(f"HFVI requires Node.js major 22, found {version.stdout.strip()!r}")
    run_checked([npm, "ci", "--ignore-scripts", "--no-audit", "--fund=false"], cwd=frontend)
    run_checked([npm, "run", "build"], cwd=frontend)
    if not (frontend / "dist" / "index.html").is_file():
        fail("frontend build did not produce dist/index.html")


class HfviStaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, dist_root: Path, hfvi_root: Path, **kwargs: Any) -> None:
        self.dist_root = dist_root.resolve()
        self.hfvi_root = hfvi_root.resolve()
        super().__init__(*args, **kwargs)

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        requested = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        if requested.startswith("/hfvi/"):
            root = self.hfvi_root
            relative = requested.removeprefix("/hfvi/")
        else:
            root = self.dist_root
            relative = requested.lstrip("/") or "index.html"
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            return str(root / ".blocked-path")
        return str(candidate)


def start_static_server(dist_root: Path, hfvi_root: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = partial(HfviStaticHandler, directory=str(dist_root), dist_root=dist_root, hfvi_root=hfvi_root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="hfvi-static-server", daemon=True)
    thread.start()
    return server, thread


def png_rgba(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        fail(f"HFVI screenshot is not a PNG: {path}")
    position = len(PNG_SIGNATURE)
    width = height = bit_depth = colour_type = interlace = None
    compressed = bytearray()
    while position < len(data):
        if position + 12 > len(data):
            fail(f"truncated PNG chunk in {path}")
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_start = position + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > len(data):
            fail(f"truncated PNG payload in {path}")
        chunk = data[chunk_start:chunk_end]
        if chunk_type == b"IHDR":
            if len(chunk) != 13:
                fail(f"invalid PNG header in {path}")
            width, height, bit_depth, colour_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", chunk)
            if compression != 0 or filter_method != 0:
                fail(f"unsupported PNG compression/filter in {path}")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            break
        position = chunk_end + 4
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        fail(f"missing PNG dimensions in {path}")
    if bit_depth != 8 or colour_type not in {2, 6} or interlace != 0:
        fail(f"HFVI PNG must be non-interlaced 8-bit RGB/RGBA: {path}")
    channels = 4 if colour_type == 6 else 3
    stride = width * channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        fail(f"invalid PNG image stream in {path}: {exc}")
    if len(raw) != height * (stride + 1):
        fail(f"unexpected PNG decoded length in {path}")
    rows: list[bytes] = []
    cursor = 0
    for _row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        source = raw[cursor : cursor + stride]
        cursor += stride
        prior = rows[-1] if rows else bytes(stride)
        decoded = bytearray(stride)
        for index, value in enumerate(source):
            left = decoded[index - channels] if index >= channels else 0
            up = prior[index]
            up_left = prior[index - channels] if index >= channels else 0
            if filter_type == 0:
                decoded[index] = value
            elif filter_type == 1:
                decoded[index] = (value + left) & 0xFF
            elif filter_type == 2:
                decoded[index] = (value + up) & 0xFF
            elif filter_type == 3:
                decoded[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = left + up - up_left
                pa = abs(predictor - left)
                pb = abs(predictor - up)
                pc = abs(predictor - up_left)
                nearest = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
                decoded[index] = (value + nearest) & 0xFF
            else:
                fail(f"unsupported PNG filter {filter_type} in {path}")
        rows.append(bytes(decoded))
    if channels == 4:
        return width, height, b"".join(rows)
    rgba = bytearray(width * height * 4)
    source = b"".join(rows)
    for index in range(width * height):
        rgba[index * 4 : index * 4 + 3] = source[index * 3 : index * 3 + 3]
        rgba[index * 4 + 3] = 255
    return width, height, bytes(rgba)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)


def encode_png_rgba(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height * 4:
        raise ValueError("invalid RGBA buffer length")
    raw = b"".join(b"\x00" + pixels[row * width * 4 : (row + 1) * width * 4] for row in range(height))
    return PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + png_chunk(b"IDAT", zlib.compress(raw, level=9)) + png_chunk(b"IEND", b"")


def compare_pixels(expected: bytes, actual: bytes, *, max_channel_delta: int) -> tuple[int, bytes]:
    diff = bytearray(len(expected))
    mismatches = 0
    for offset in range(0, len(expected), 4):
        changed = any(abs(expected[offset + channel] - actual[offset + channel]) > max_channel_delta for channel in range(4))
        if changed:
            mismatches += 1
            diff[offset : offset + 4] = b"\xff\x00\x00\xff"
        else:
            diff[offset : offset + 4] = b"\x00\x00\x00\xff"
    return mismatches, bytes(diff)


def capture_ready_page(command: list[str], *, root: Path, env: dict[str, str], url: str, viewport: dict[str, int], output_path: Path) -> None:
    """Capture actual pixels after the application completes replay and painting.

    Chrome's virtual-time CLI screenshot can stall on background activity or
    capture before asynchronous replay. The local DevTools pipe needs no open
    debugging port or third-party browser driver.
    """
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["bash", "-c", 'exec 3<&0 4>&1; exec "$@"', "hfvi-browser", *command, "--remote-debugging-pipe", "about:blank"],
            cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=errors, start_new_session=True,
        )
        buffer = b""
        sequence = 0
        def call(method: str, params: dict[str, Any] | None = None, session: str | None = None) -> dict[str, Any]:
            nonlocal buffer, sequence
            sequence += 1
            request: dict[str, Any] = {"id": sequence, "method": method, "params": params or {}}
            if session:
                request["sessionId"] = session
            process.stdin.write(json.dumps(request).encode("utf-8") + b"\0")
            process.stdin.flush()
            deadline = time.monotonic() + 60
            while True:
                while b"\0" in buffer:
                    raw, buffer = buffer.split(b"\0", 1)
                    message = json.loads(raw)
                    if message.get("id") != sequence:
                        continue
                    if "error" in message:
                        raise RuntimeError(f"{method}: {message['error']}")
                    return message["result"]
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                    raise RuntimeError(f"browser command timed out: {method}")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError(f"browser exited during {method}")
                buffer += chunk
        try:
            target = call("Target.createTarget", {"url": "about:blank"})["targetId"]
            session = call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
            call("Page.enable", session=session)
            call("Emulation.setDeviceMetricsOverride", {**viewport, "mobile": False}, session)
            call("Page.navigate", {"url": url}, session)
            ready = call("Runtime.evaluate", {
                "expression": """(async () => {
                    const deadline = Date.now() + 30000;
                    while (document.documentElement.dataset.hfviReplay !== 'baseline') {
                        const error = document.documentElement.dataset.hfviError;
                        if (error) throw new Error(error);
                        if (Date.now() > deadline) throw new Error('HFVI replay did not complete');
                        await new Promise(resolve => setTimeout(resolve, 20));
                    }
                    await document.fonts.ready;
                    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    return true;
                })()""",
                "awaitPromise": True, "returnByValue": True,
            }, session)
            if "exceptionDetails" in ready or ready.get("result", {}).get("value") is not True:
                raise RuntimeError(f"HFVI page replay failed: {ready}")
            screenshot = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}, session)
            output_path.write_bytes(base64.b64decode(screenshot["data"], validate=True))
        except (OSError, ValueError, RuntimeError) as exc:
            errors.seek(0)
            diagnostics = errors.read().decode("utf-8", errors="replace")[-4000:]
            fail(f"HFVI browser capture failed: {exc}\n{diagnostics}")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            process.stdin.close()
            process.stdout.close()


def capture_browser_screenshot(root: Path, browser_lock: dict[str, Any], output_path: Path) -> tuple[str, str]:
    browser = os.environ.get("HFVI_BROWSER_BINARY", "google-chrome")
    binary = shutil.which(browser) if Path(browser).name == browser else browser
    if binary is None or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        fail("HFVI_BROWSER_BINARY must name an executable Chrome-for-Testing binary")
    version = subprocess.run([binary, "--product-version"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if version.returncode != 0:
        fail(f"unable to obtain HFVI browser version: {version.stdout}")
    product_version = version.stdout.strip()
    if product_version != browser_lock["productVersion"]:
        fail(f"HFVI browser version mismatch: expected {browser_lock['productVersion']}, got {product_version}")
    viewport = browser_lock["viewport"]
    with tempfile.TemporaryDirectory(prefix="hfvi-browser-") as temporary:
        server, thread = start_static_server(root / "frontend" / "dist", root / "hfvi")
        try:
            env = os.environ.copy()
            env["TZ"] = browser_lock["timezone"]
            url = f"http://127.0.0.1:{server.server_port}/?hfviTape={TAPE_ID}"
            command = [
                binary,
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-features=MediaRouter,OptimizationHints,Translate",
                "--disable-sync",
                "--force-color-profile=srgb",
                "--force-device-scale-factor=1",
                "--hide-scrollbars",
                f"--lang={browser_lock['locale']}",
                "--no-first-run",
                "--run-all-compositor-stages-before-draw",
                f"--user-data-dir={Path(temporary) / 'profile'}",
                f"--window-size={viewport['width']},{viewport['height']}",
            ]
            capture_ready_page(command, root=root, env=env, url=url, viewport=viewport, output_path=output_path)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    if not output_path.is_file():
        fail("locked browser did not produce an HFVI screenshot")
    return product_version, sha256_file(Path(binary).resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-baseline", action="store_true", help="replace the approved baseline after an explicit review workflow")
    args = parser.parse_args()
    if args.record_baseline and os.environ.get("HFVI_ALLOW_RECORD_BASELINE") != "1":
        fail("recording an HFVI baseline requires HFVI_ALLOW_RECORD_BASELINE=1")

    root = Path(__file__).resolve().parents[1]
    tape_path = root / "hfvi" / "tapes" / f"{TAPE_ID}.json"
    golden_path = root / "hfvi" / "golden" / f"{TAPE_ID}.json"
    golden_png_path = root / "hfvi" / "golden" / f"{TAPE_ID}.png"
    browser_lock_path = root / "hfvi" / "browser.lock.json"
    tape = load_object(tape_path)
    state = replay_state(tape)
    browser_lock = load_browser_lock(browser_lock_path)
    build_frontend(root / "frontend")

    evidence_root = root / ".cadence" / "out" / "hfvi"
    evidence_root.mkdir(parents=True, exist_ok=True)
    actual_png_path = evidence_root / f"{TAPE_ID}.actual.png"
    product_version, browser_executable_sha256 = capture_browser_screenshot(root, browser_lock, actual_png_path)
    width, height, actual_pixels = png_rgba(actual_png_path)
    browser_lock_sha256 = sha256_file(browser_lock_path)

    if args.record_baseline:
        atomic_write(golden_png_path, actual_png_path.read_bytes())
        golden = {
            "schemaVersion": GOLDEN_SCHEMA_VERSION,
            "tapeId": TAPE_ID,
            "state": state,
            "browserLockSha256": browser_lock_sha256,
            "screenshotSha256": sha256_file(golden_png_path),
            "pixelSha256": sha256_bytes(actual_pixels),
            "pixelDimensions": {"width": width, "height": height},
            "pixelThreshold": browser_lock["pixelThreshold"],
        }
        atomic_write(golden_path, canonical_bytes(golden))
        print(json.dumps({"status": "recorded", "tapeId": TAPE_ID, "screenshotSha256": golden["screenshotSha256"]}, sort_keys=True))
        return 0

    golden = load_object(golden_path)
    required_golden = {"schemaVersion", "tapeId", "state", "browserLockSha256", "screenshotSha256", "pixelSha256", "pixelDimensions", "pixelThreshold"}
    if set(golden) != required_golden or golden.get("schemaVersion") != GOLDEN_SCHEMA_VERSION or golden.get("tapeId") != TAPE_ID:
        fail("HFVI golden has an unsupported schemaVersion, tapeId, or fields")
    if golden.get("state") != state:
        fail("HFVI state diff: replayed state does not match the approved golden")
    if golden.get("browserLockSha256") != browser_lock_sha256 or golden.get("pixelThreshold") != browser_lock["pixelThreshold"]:
        fail("HFVI browser lock diff: golden is not bound to the current browser lock")
    if not golden_png_path.is_file():
        fail("HFVI golden screenshot is missing")
    if golden.get("screenshotSha256") != sha256_file(golden_png_path):
        fail("HFVI golden integrity diff: screenshot hash does not match approved metadata")
    expected_width, expected_height, expected_pixels = png_rgba(golden_png_path)
    if golden.get("pixelDimensions") != {"width": expected_width, "height": expected_height} or golden.get("pixelSha256") != sha256_bytes(expected_pixels):
        fail("HFVI golden integrity diff: pixel metadata does not match approved screenshot")
    if (width, height) != (expected_width, expected_height):
        fail(f"HFVI screenshot dimensions differ: expected {expected_width}x{expected_height}, got {width}x{height}")
    threshold = browser_lock["pixelThreshold"]
    mismatch_count, diff_pixels = compare_pixels(expected_pixels, actual_pixels, max_channel_delta=threshold["maxChannelDelta"])
    diff_path = evidence_root / f"{TAPE_ID}.diff.png"
    atomic_write(diff_path, encode_png_rgba(width, height, diff_pixels))
    receipt = {
        "schemaVersion": "1.0.0",
        "reportType": "HfviBrowserReplayReceipt",
        "status": "passed" if mismatch_count <= threshold["maxPixels"] else "failed",
        "tapeId": TAPE_ID,
        "tapeSha256": sha256_file(tape_path),
        "browserLockSha256": browser_lock_sha256,
        "browserProductVersion": product_version,
        "browserExecutableSha256": browser_executable_sha256,
        "goldenScreenshotSha256": sha256_file(golden_png_path),
        "actualScreenshotSha256": sha256_file(actual_png_path),
        "pixelDimensions": {"width": width, "height": height},
        "pixelMismatchCount": mismatch_count,
        "pixelThreshold": threshold,
        "actualScreenshot": ".cadence/out/hfvi/baseline.actual.png",
        "diffScreenshot": ".cadence/out/hfvi/baseline.diff.png",
    }
    atomic_write(evidence_root / f"{TAPE_ID}.browser-replay.json", canonical_bytes(receipt))
    if mismatch_count > threshold["maxPixels"]:
        fail(f"HFVI pixel diff: {mismatch_count} pixels exceed the approved threshold {threshold['maxPixels']}; review {diff_path}")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
