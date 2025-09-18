"""VLM client with three modes:
 - HTTP mode: POST to configured VLM_URL (expects JSON response)
 - subprocess/local transformers mode (optional, heavier)
 - dummy mode: returns a simple attribute set

Logs requests/responses to backend/cache/vlm_logs for auditing.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from base64 import b64encode
import json
import time
import traceback
from pathlib import Path
import requests
import subprocess


@dataclass
class VLMAttributes:
    category: str
    colors: List[str]
    size: str
    orientation: str
    details: List[str]


def _log_vlm(name: str, payload: Dict[str, Any]):
    try:
        cache = Path(__file__).resolve().parent.parent / 'cache' / 'vlm_logs'
        cache.mkdir(parents=True, exist_ok=True)
        ts = time.strftime('%Y%m%dT%H%M%SZ')
        p = cache / f"{ts}_{name}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def load_vlm_model():
    # interface-compatible placeholder; actual loading not required for HTTP mode
    return {'name': 'vlm-client'}


def _http_call(url: str, token: Optional[str], image_bytes: bytes, timeout: int) -> Optional[Dict[str, Any]]:
    try:
        hdr = {'Accept': 'application/json'}
        if token:
            hdr['Authorization'] = f'Bearer {token}'
        # adapt payload by configured mode
        try:
            from ..config import settings
            mode = getattr(settings, 'VLM_MODE', 'image_b64')
        except Exception:
            mode = 'image_b64'

        if mode == 'openai_chat':
            # Build OpenAI-like messages array with data URL image
            img_b64 = b64encode(image_bytes).decode('ascii')
            data_url = f"data:image/png;base64,{img_b64}"
            # Use a strict system+user prompt pair to force JSON-only responses
            system_msg = {
                'role': 'system',
                'content': (
                    'You are an assistant that analyzes an input image and returns ' \
                    'a single JSON object and nothing else. The JSON must match the ' \
                    'schema: {"category":string, "colors": [string], "size": "small|medium|large", ' \
                    '"orientation": "front|side|top|angled", "details": [string]}. '
                )
            }
            user_msg = {
                'role': 'user',
                'content': f'Analyze this image and return JSON only. Image data: {data_url}'
            }
            payload = {'messages': [system_msg, user_msg]}
            _log_vlm('request_openai_chat', {'url': url, 'payload_preview': str(payload)[:1000]})
            resp = requests.post(url, json=payload, headers=hdr, timeout=timeout)
        elif mode == 'multipart':
            # send as multipart/form-data file upload
            files = {'file': ('tile.png', image_bytes, 'image/png')}
            _log_vlm('request_multipart', {'url': url, 'files': list(files.keys())})
            resp = requests.post(url, files=files, headers={'Authorization': hdr.get('Authorization')} if token else None, timeout=timeout)
        else:
            # Include messages alongside image_b64 for compatibility with
            # LMStudio/Gemma3 chat-completions endpoints which require a
            # `messages` field. We'll also add a stricter instruction to
            # attempt to return JSON-first; however servers may still reply
            # with free-form text, so we handle that downstream.
            img_b64 = b64encode(image_bytes).decode('ascii')
            data_url = f"data:image/png;base64,{img_b64}"
            system_msg = {
                'role': 'system',
                'content': 'Return a single JSON object and nothing else following schema: {"category","colors","size","orientation","details"}.'
            }
            user_msg = {
                'role': 'user',
                'content': f'Analyze the image and return JSON only. Image: {data_url}'
            }
            payload = {
                'image_b64': img_b64,
                'messages': [system_msg, user_msg]
            }
            _log_vlm('request_image_b64_with_messages', {'url': url, 'headers': {k: hdr.get(k) for k in ('Authorization',)}, 'payload_preview': str(payload)[:1000]})
            resp = requests.post(url, json=payload, headers=hdr, timeout=timeout)

        try:
            j = resp.json()
        except Exception:
            j = {'status_code': resp.status_code, 'text': resp.text}
        _log_vlm('response', {'status': resp.status_code, 'body': j})
        return j
    except Exception as e:
        _log_vlm('error', {'error': str(e), 'trace': traceback.format_exc()})
        return None


def _subprocess_call(cmd: List[str], image_path: Path, timeout: int) -> Optional[Dict[str, Any]]:
    # placeholder: call a CLI VLM with image path and expect JSON on stdout
    try:
        proc = subprocess.run(cmd + [str(image_path)], capture_output=True, text=True, timeout=timeout)
        out = proc.stdout or proc.stderr
        try:
            j = json.loads(out)
        except Exception:
            j = {'status': 'ok', 'raw': out}
        _log_vlm('subprocess_response', {'cmd': cmd, 'returncode': proc.returncode, 'out_len': len(out) if out else 0})
        return j
    except Exception as e:
        _log_vlm('subprocess_error', {'error': str(e), 'trace': traceback.format_exc()})
        return None


def extract_attributes(model, image_bytes: bytes) -> VLMAttributes:
    # decide mode from settings
    try:
        from ..config import settings
    except Exception:
        settings = None

    # 1) HTTP mode
    if settings and getattr(settings, 'VLM_URL', None):
        for attempt in range(getattr(settings, 'VLM_RETRIES', 2)):
            resp = _http_call(settings.VLM_URL, getattr(settings, 'VLM_TOKEN', None), image_bytes, getattr(settings, 'VLM_TIMEOUT', 10))
            if resp:
                # Attempt to extract structured attributes. LM servers may
                # return either JSON object directly or a chat-like response
                # structure. Try several common patterns.
                try:
                    # If resp is already a mapping with keys
                    if isinstance(resp, dict):
                        # common OpenAI-like choice structure
                        if 'choices' in resp and isinstance(resp['choices'], list) and resp['choices']:
                            # extract message content
                            msg = resp['choices'][0].get('message') or resp['choices'][0].get('text')
                            content = None
                            if isinstance(msg, dict):
                                content = msg.get('content')
                            elif isinstance(msg, str):
                                content = msg
                        else:
                            # direct object
                            content = None
                            # If dict contains category/colors etc, use it
                            if all(k in resp for k in ('category', 'colors')):
                                return VLMAttributes(
                                    category=resp.get('category','object'),
                                    colors=resp.get('colors', ['gray']),
                                    size=resp.get('size','medium'),
                                    orientation=resp.get('orientation','front'),
                                    details=resp.get('details', [])
                                )
                        # if we have textual content, try to parse JSON inside
                        if content:
                            # try direct JSON parse
                            try:
                                j = json.loads(content)
                                if isinstance(j, dict) and 'category' in j:
                                    return VLMAttributes(
                                        category=j.get('category','object'),
                                        colors=j.get('colors', ['gray']),
                                        size=j.get('size','medium'),
                                        orientation=j.get('orientation','front'),
                                        details=j.get('details', [])
                                    )
                            except Exception:
                                # attempt to extract JSON substring
                                import re
                                m = re.search(r"\{[\s\S]*\}", content)
                                if m:
                                    try:
                                        j = json.loads(m.group(0))
                                        if isinstance(j, dict) and 'category' in j:
                                            return VLMAttributes(
                                                category=j.get('category','object'),
                                                colors=j.get('colors', ['gray']),
                                                size=j.get('size','medium'),
                                                orientation=j.get('orientation','front'),
                                                details=j.get('details', [])
                                            )
                                    except Exception:
                                        pass
                        # If we get here, we couldn't parse structured attrs.
                        # As a fallback, if there is text content available,
                        # return a VLMAttributes with category='object' and
                        # put the raw text into details so pipeline can use it
                        raw_text = None
                        if isinstance(resp, dict):
                            # flatten likely text fields
                            if 'choices' in resp and resp['choices']:
                                c0 = resp['choices'][0]
                                raw_text = c0.get('message', {}).get('content') if isinstance(c0.get('message'), dict) else c0.get('text') or c0.get('message')
                            else:
                                # try common fields
                                raw_text = resp.get('text') or resp.get('content') or str(resp)
                        else:
                            raw_text = str(resp)
                        if raw_text:
                            # keep the raw text so pipeline can fall back to sending
                            # it directly to SD if structured parsing fails
                            return VLMAttributes(
                                category='object',
                                colors=['gray'],
                                size='medium',
                                orientation='front',
                                details=[raw_text]
                            )
                except Exception:
                    # parsing attempt failed for this resp; try next attempt
                    continue
        # if HTTP mode fails, fallthrough to other modes

    # 2) Subprocess/local mode (not implemented fully; placeholder showing where to add)
    # if CLI path or other config present, call it
    # (left as future extension)

    # 3) Dummy fallback
    _log_vlm('fallback', {'reason': 'no_vlm_available'})
    return VLMAttributes(
        category='object',
        colors=['red','white'],
        size='medium',
        orientation='front',
        details=['placeholder']
    )


def to_prompt(attrs: VLMAttributes) -> str:
    return (
        f"voxel-style {attrs.category}, {attrs.size}, primary colors: {', '.join(attrs.colors)}, "
        f"details: {', '.join(attrs.details)}, low-poly, game-friendly, 3D render, front view"
    )
