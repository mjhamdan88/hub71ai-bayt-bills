"""Safe, renderer-neutral visual metadata for persisted tool responses."""

import ast
import json
import re
from collections.abc import Mapping


_SAFE_IMAGE_DATA_URL = re.compile(
    r"^data:image/(?:png|jpe?g|gif|webp|bmp|avif);base64,",
    re.IGNORECASE,
)


def _decode(value):
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            try:
                value = ast.literal_eval(value)
            except (TypeError, ValueError, SyntaxError):
                break
    return value


def _result_payload(raw):
    value = _decode((raw or {}).get("tool_response", {}).get("result"))
    for _ in range(3):
        if (
            not isinstance(value, Mapping)
            or "result" not in value
            or "_unicom_presentation" in value
            or "_responses_content" in value
        ):
            break
        value = _decode(value.get("result"))
    return value


def extract_tool_presentation(raw):
    """Return a validated presentation descriptor from tool-response metadata."""
    payload = _result_payload(raw)
    if not isinstance(payload, Mapping):
        return None
    presentation = payload.get("_unicom_presentation")
    if isinstance(presentation, Mapping) and presentation.get("type") == "image":
        url = presentation.get("url")
        if isinstance(url, str) and (_SAFE_IMAGE_DATA_URL.match(url) or url.startswith(("https://", "http://", "/"))):
            return {
                "type": "image", "url": url,
                "alt": str(presentation.get("alt") or "Tool image")[:500],
                "caption": str(presentation.get("caption") or "")[:1000],
            }
    if isinstance(presentation, Mapping) and presentation.get("type") == "gallery":
        images = []
        for item in presentation.get("images") or []:
            if not isinstance(item, Mapping):
                continue
            url = item.get("url")
            if isinstance(url, str) and (_SAFE_IMAGE_DATA_URL.match(url) or url.startswith(("https://", "http://", "/"))):
                images.append({
                    "url": url, "alt": str(item.get("alt") or "Browser screenshot")[:500],
                    "caption": str(item.get("caption") or "")[:1000],
                })
        if images:
            return {"type": "gallery", "images": images[:5]}
    if isinstance(presentation, Mapping) and presentation.get("type") == "video":
        source_path = presentation.get("source_path")
        device_id = presentation.get("device_id")
        poster = presentation.get("poster") or ""
        if (isinstance(device_id, int) and isinstance(source_path, str) and source_path.startswith("/")
                and "\x00" not in source_path and (not poster or _SAFE_IMAGE_DATA_URL.match(poster))):
            return {
                "type": "video", "device_id": device_id, "source_path": source_path,
                "poster": poster, "caption": str(presentation.get("caption") or "Browser recording")[:1000],
            }
    if isinstance(presentation, Mapping) and presentation.get("type") == "public_links":
        links = []
        for item in presentation.get("links") or []:
            if not isinstance(item, Mapping):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            links.append({
                "url": url,
                "label": str(item.get("label") or "Open application")[:200],
                "port": item.get("port"),
            })
        if links:
            return {"type": "public_links", "links": links[:3]}
    if isinstance(presentation, Mapping) and presentation.get("type") == "terminal":
        return {
            "type": "terminal",
            "command": str(presentation.get("command") or "")[:4000],
            "exit_code": presentation.get("exit_code"),
            "stdout": str(presentation.get("stdout") or "")[-6000:],
            "stderr": str(presentation.get("stderr") or "")[-3000:],
            "timed_out": bool(presentation.get("timed_out")),
            "duration_seconds": presentation.get("duration_seconds"),
        }
    blocks = payload.get("_responses_content")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, Mapping) and block.get("type") == "input_image":
                url = block.get("image_url")
                if isinstance(url, str) and _SAFE_IMAGE_DATA_URL.match(url):
                    return {
                        "type": "image", "url": url, "alt": "Tool image",
                        "caption": str(payload.get("path") or "")[:1000],
                    }
    return None
