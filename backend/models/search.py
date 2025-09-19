import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import re
import hashlib
import random

# simple JP->EN token map for short queries
JP_TO_EN = {
    '車': ['car', 'vehicle', 'automobile'],
    '家': ['house', 'home', 'building'],
    '木': ['tree'],
    '木々': ['trees'],
    '人': ['person', 'people'],
    '川': ['river'],
    '海': ['sea', 'ocean'],
}

# simple english->japanese mapping for safe comment generation
EN_TO_JP_SIMPLE = {
    'car': '車',
    'vehicle': '車',
    'automobile': '車',
    'house': '家',
    'home': '家',
    'building': '建物',
    'tree': '木',
    'trees': '木々',
    'person': '人',
    'people': '人たち',
    'river': '川',
    'sea': '海',
    'ocean': '海',
    'fruit': '果物',
    'apple': 'りんご',
    'banana': 'バナナ'
}

CACHE_DIR = Path(__file__).resolve().parents[1] / 'cache' / 'vlm_logs'

# System prompt in "妹口調" (imouto-style) for LMStudio chat-like API
IMOUTO_SYSTEM_PROMPT = (
    "あなたは優しい妹のように振る舞ってください。ユーザーの質問には短く、親しみやすく、少し甘えた日本語の口調（妹口調）で答えてください。出力は冷静にJSONで返す部分と、妹口調の短いコメントを含める部分の両方を提供してください。"
)


def _read_vlm_logs() -> List[Dict[str, Any]]:
    logs = []
    if not CACHE_DIR.exists():
        return logs
    for p in sorted(CACHE_DIR.glob('*.json')):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            # Expect each log to contain at least: id, description/text, coords (x,y,z) or bbox
            logs.append({'path': str(p), 'data': data, 'ts': p.stat().st_mtime})
        except Exception:
            continue
    return logs


def _build_candidates_from_logs() -> List[Dict[str, Any]]:
    logs = _read_vlm_logs()
    candidates = []
    for l in logs:
        d = l.get('data')
        # normalize
        text = ''
        coords = None
        vid = None
        if isinstance(d, dict):
            vid = d.get('id') or d.get('job_id') or Path(l['path']).stem
            # try common fields
            if 'result' in d and isinstance(d['result'], dict):
                text = d['result'].get('description') or d['result'].get('text') or json.dumps(d['result'])
            else:
                # check top-level textlike fields
                for k in ['text', 'description', 'caption', 'prompt', 'message']:
                    if k in d:
                        text = d[k]
                        break
            # coords or bbox
            if 'coords' in d:
                coords = d['coords']
            elif 'bbox' in d:
                coords = d['bbox']
            elif 'meta' in d and isinstance(d['meta'], dict):
                coords = d['meta'].get('coords') or d['meta'].get('location')
        else:
            text = str(d)
            vid = Path(l['path']).stem
        candidates.append({'id': vid, 'text': text or '', 'coords': coords, 'ts': l['ts']})
    # deduplicate by normalized text (keep most recent)
    def _norm(s: str) -> str:
        return re.sub(r"\s+", ' ', (s or '').strip().lower())

    seen = {}
    # keep only the most recent candidate per normalized text
    for c in sorted(candidates, key=lambda x: x.get('ts', 0), reverse=True):
        k = _norm(c.get('text',''))
        if not k:
            # keep empty-text items keyed by id to avoid collapsing unrelated empties
            k = (c.get('id') or '') + '|__empty__'
        if k in seen:
            continue
        seen[k] = c
    return list(seen.values())


def _score_with_keywords(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not query or not query.strip():
        return []
    q = query.lower()
    out = []
    # Determine whether query contains non-ascii (likely Japanese)
    is_non_ascii = any(ord(ch) > 127 for ch in query.strip())
    q_tokens = []
    if not is_non_ascii:
        # tokenize query (works for latin words)
        q_tokens = [tok for tok in re.split(r"\W+", q) if tok and len(tok) > 1]

    # if query is short Japanese (like '車'), map to English tokens to match candidate english descriptions
    mapped = []
    if query.strip() in JP_TO_EN:
        mapped = JP_TO_EN[query.strip()]
    # If JP->EN mapping exists, use it
    if mapped:
        q_tokens = mapped
    # If query is non-ascii and reverse mapping exists in EN->JP, use reverse mapping
    if is_non_ascii and not q_tokens:
        rev = [k for k, v in EN_TO_JP_SIMPLE.items() if v == query.strip() or query.strip() in v]
        if rev:
            q_tokens = rev

    if not q_tokens:
        # fallback to query as a token (for japanese/multibyte or others)
        q_tokens = [q]

    fallback_comments = [
        'これ、なんだろうね〜でも可愛いよ〜',
        'うーん、ちょっと自信ないけど……見つけたよ〜',
        'わかったかも？これっぽいね、見てみて〜',
        'お兄ちゃん、これかな〜？かわいいね〜'
    ]

    for c in candidates:
        t_raw = c.get('text') or ''
        t = t_raw.lower()
        # candidate tokens
        c_tokens = [tok for tok in re.split(r"\W+", t) if tok and len(tok) > 1]
        # score = token overlap ratio
        match_count = sum(1 for tok in q_tokens if tok in c_tokens or any(tok in ct for ct in c_tokens))
        score = match_count / max(1, len(q_tokens))
        # boost if query substring appears or any mapped token appears as substring (stronger signal)
        if q in t:
            score += 0.25
        if any(qtok in t for qtok in q_tokens):
            # if token appears as substring, ensure a noticeable positive score
            score = max(score, 0.5)

        # penalize extremely short/empty candidate texts
        if len(t_raw.strip()) < 3:
            score *= 0.2
        cpy = dict(c)
        cpy['score'] = float(min(1.0, score))
        # generate a tiny imouto-style Japanese comment fallback (avoid echoing technical tokens)
        preview = t_raw.strip()

        def _safe_comment_from_text(text: str, idx: int) -> str:
            try:
                if not text:
                    # deterministic selection based on id for empties
                    seed = int(hashlib.sha1((cpy.get('id') or str(idx)).encode('utf-8')).hexdigest(), 16)
                    return fallback_comments[seed % len(fallback_comments)]
                toks = [tok for tok in re.split(r"\W+", text) if tok]
                tech_tokens = ('voxel', 'voxel-style', 'style', 'low-poly', 'lowpoly', 'game-friendly', '3d', 'primary', 'colors', 'color', 'render', 'front', 'view', 'detail', 'details', 'large', 'small', 'size', 'game', 'friendly', 'texture', 'textures')
                subject = None
                # prefer safe ASCII tokens (letters/hyphen) that are not technical adjectives
                for tok in toks:
                    lowtok = tok.lower()
                    if not re.match(r'^[a-z\-]+$', lowtok):
                        continue
                    if any(tt in lowtok for tt in tech_tokens):
                        continue
                    # map known english nouns to jp
                    if lowtok in EN_TO_JP_SIMPLE:
                        subject = EN_TO_JP_SIMPLE[lowtok]
                        break
                    # otherwise use the ascii token as fallback
                    subject = lowtok
                    break
                if not subject:
                    # as a last resort, try to find any ascii word in the entire text
                    m = re.search(r'([A-Za-z]{2,})', text)
                    if m:
                        w = m.group(1).lower()
                        subject = EN_TO_JP_SIMPLE.get(w, 'これ')
                    else:
                        subject = 'これ'
                comment = f'これ、{subject}っぽいね、かわいい〜'
                if len(comment) > 40:
                    comment = comment[:37] + '...'
                return comment
            except Exception:
                return random.choice(fallback_comments)

        # produce comment with index to help uniqueness
        # Only attach a comment when score is positive; otherwise leave empty
        if cpy['score'] > 0.0:
            cpy['comment'] = _safe_comment_from_text(t_raw, len(out))
        else:
            cpy['comment'] = ''
        out.append(cpy)
    out.sort(key=lambda x: x['score'], reverse=True)
    # ensure uniqueness of comments across returned list (for duplicated texts)
    used_comments = set()
    suffix_variants = ['ね、かわいい〜', 'だよ〜', 'かな〜', 'すごいね〜', 'だね〜']
    def gen_imouto_comment_from_text(text: str) -> str:
        try:
            if not text:
                return random.choice(fallback_comments)
            first = text.split()[0]
            comment = f'これ、{first}っぽいね、かわいい〜'
            if len(comment) > 40:
                comment = comment[:37] + '...'
            return comment
        except Exception:
            return random.choice(fallback_comments)

    def variant_comment(base: str, idx: int) -> str:
        v = suffix_variants[idx % len(suffix_variants)]
        cand = f"これ、{base}{v}"
        return cand if len(cand) <= 40 else (cand[:37] + '...')

    for idx, item in enumerate(out):
        # Skip generating/adjusting comments for zero-score items
        if (item.get('score') or 0.0) <= 0.0:
            item['comment'] = ''
            continue
        c = (item.get('comment') or '').strip()
        if not c:
            item['comment'] = gen_imouto_comment_from_text(item.get('text',''))
            c = item['comment']
        # if duplicate comment, create a small variant
        if c in used_comments:
            base = (item.get('text') or '').split()[0] if item.get('text') else 'これ'
            item['comment'] = variant_comment(base, idx)
            c = item['comment']
        used_comments.add(c)

    # filter out very-low-score items
    filtered = [o for o in out if (o.get('score') or 0.0) > 0.02]
    # If nothing passes the threshold, return empty to indicate no match
    if not filtered:
        return []
    return filtered


def _call_lmstudio_chat(query: str, candidates: List[Dict[str, Any]], lm_url: str, lm_token: Optional[str], target: Optional[str] = None) -> List[Dict[str, Any]]:
    # Builds a chat-like prompt payload and asks LMStudio to rank or score candidates.
    # Because LMStudio APIs vary, we implement a lightweight "ask for similarity scores" approach.
    headers = {'Content-Type': 'application/json'}
    if lm_token:
        headers['Authorization'] = f'Bearer {lm_token}'

    # Compose a single system + user message asking to rank candidates
    system = IMOUTO_SYSTEM_PROMPT
    # target-specific hint
    target_hint = ''
    if target == 'paint':
        target_hint = '注: paint UI 用。comment は非常に短く（最大20文字）簡潔な妹口調でお願いします。'
    elif target in ('world_new', 'world'):
        target_hint = '注: world UI 用。comment は短め（10〜40文字）、場所の参照を含めても良いです。'

    user_msg = (
        f"次の候補テキスト（英語で書かれていることがあります）を参照して、質問 '{query}' に類似している順に並べ、各候補に0.0から1.0の範囲でスコアを付けてください。"
        " 出力はJSON配列で返してください。各要素は次の形でお願いします: {\n"
        "  \"id\": <候補のID文字列>,\n"
        "  \"score\": <0.0から1.0の数値>,\n"
        "  \"text\": <候補の元テキスト（必要なら英語のまま）>,\n"
        "  \"comment\": <妹口調の短い日本語コメント（10〜40文字程度）>\n"
        "}\n"
        + target_hint + "\n"
        "候補のテキストは英語の説明中心です。日本語の妹口調コメントは必ず含めてください。JSON 以外の余計な文章は出力しないでください。"
    )

    # Build candidate list string (truncate long texts)
    cand_texts = []
    for c in candidates:
        txt = (c.get('text') or '')
        if len(txt) > 400: txt = txt[:400] + '...'
        cand_texts.append({'id': c.get('id'), 'text': txt})

    payload = {
        'model': 'gpt-4o-mini',
        'messages': [
            { 'role': 'system', 'content': system },
            { 'role': 'user', 'content': user_msg + '\n\nCandidates:\n' + '\n'.join([f"[{i['id']}] {i['text']}" for i in cand_texts]) }
        ],
        'max_tokens': 512
    }

    try:
        r = requests.post(lm_url, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        j = r.json()
        # Try to extract assistant text -- adapt to LMStudio's response shape
        assistant = ''
        if isinstance(j, dict):
            if 'choices' in j and isinstance(j['choices'], list) and j['choices']:
                assistant = j['choices'][0].get('message', {}).get('content', '') or j['choices'][0].get('text','') or ''
            elif 'output' in j:
                assistant = j['output']
            else:
                assistant = json.dumps(j, ensure_ascii=False)
        else:
            assistant = str(j)

        # Helper: strip code fences and language hints
        def _strip_code_fences(s: str) -> str:
            if not s:
                return s
            # remove leading/trailing ```json or ```
            s = re.sub(r"^\s*```(?:json)?\s*", '', s, flags=re.I)
            s = re.sub(r"\s*```\s*$", '', s)
            return s

        # Helper: find balanced JSON array substring from first '['
        def _extract_json_array(s: str) -> Optional[str]:
            if not s or '[' not in s:
                return None
            start = s.find('[')
            depth = 0
            for i in range(start, len(s)):
                ch = s[i]
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        return s[start:i+1]
            return None

        import re
        parsed = None
        # try direct parse first
        try:
            parsed = json.loads(assistant)
        except Exception:
            # strip common markdown fences and try to extract JSON array substring
            txt = _strip_code_fences(assistant)
            js_sub = _extract_json_array(txt)
            if js_sub:
                try:
                    parsed = json.loads(js_sub)
                except Exception:
                    parsed = None
        if parsed and isinstance(parsed, list):
            out = []
            idmap = {c['id']: c for c in candidates}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                iid = item.get('id')
                sc = item.get('score')
                txt = item.get('text')
                comment = item.get('comment') or item.get('comment_jp') or ''
                # sanitize comment: normalize whitespace, remove newlines, limit length
                try:
                    comment = re.sub(r"\s+", ' ', (comment or '')).strip()
                    if len(comment) > 60:
                        comment = comment[:57] + '...'
                except Exception:
                    comment = (comment or '')
                if iid is None:
                    continue
                base = idmap.get(iid, {})
                out.append({
                    'id': iid,
                    'score': float(sc) if sc is not None else 0.0,
                    'text': txt or base.get('text',''),
                    'coords': base.get('coords'),
                    'comment': comment
                })
            out.sort(key=lambda x: x['score'], reverse=True)
            # Build a keyword baseline to compare against LM result
            keyword_baseline = _score_with_keywords(query, candidates)
            # If LM returned all-zero or very-low scores, fall back to keyword scoring to avoid meaningless results
            if all((item.get('score') or 0.0) <= 0.001 for item in out):
                return keyword_baseline

            # If LM scores are generally worse than keyword baseline (e.g., many zeros), prefer keyword baseline
            lm_mean = sum((it.get('score') or 0.0) for it in out) / max(1, len(out))
            kb_mean = sum((it.get('score') or 0.0) for it in keyword_baseline) / max(1, len(keyword_baseline))
            if lm_mean + 0.01 < kb_mean:
                # merge: prefer keyword result ordering and comments, but retain LM scores when positive
                merged = []
                kb_map = {k['id']: k for k in keyword_baseline}
                for kb in keyword_baseline:
                    it = dict(kb)
                    lm_item = next((x for x in out if x.get('id')==kb.get('id')), None)
                    if lm_item and (lm_item.get('score') or 0.0) > 0.0:
                        it['score'] = lm_item.get('score')
                    # keep kb comment if lm comment empty
                    if not it.get('comment') and lm_item:
                        it['comment'] = lm_item.get('comment') or ''
                    merged.append(it)
                return merged

            # deduplicate by normalized text (keep first/highest score)
            def _norm_text(s: str) -> str:
                return re.sub(r"\s+", ' ', (s or '').strip().lower())
            seen = set()
            deduped = []
            for it in out:
                nt = _norm_text(it.get('text',''))
                if nt in seen:
                    continue
                seen.add(nt)
                deduped.append(it)
            out = deduped

            # Clear comments for zero-score items so we don't attach imouto comments to non-matches
            for it in out:
                try:
                    if (it.get('score') or 0.0) <= 0.0:
                        it['comment'] = ''
                except Exception:
                    pass

            # Ensure comment is Japanese imouto-style; if detected English-only, replace with a generated jp comment
            def is_mostly_english(s: str) -> bool:
                if not s: return False
                letters = sum(1 for ch in s if 'a' <= ch.lower() <= 'z')
                return letters > max(3, len(s) // 3)

            def gen_imouto_comment(text: str) -> str:
                try:
                                if not text:
                                    return 'ん〜分かんないけど探してみたよ〜'
                                # prefer to avoid echoing technical style tokens like 'voxel-style' or 'style'
                                toks = [t.strip('\"\'.,:;()') for t in text.split() if t.strip()]
                                first = toks[0] if toks else ''
                                low = first.lower()
                                tech_tokens_local = ('voxel', 'voxel-style', 'style', 'low-poly', 'lowpoly', 'game-friendly', '3d', 'primary', 'colors', 'color', 'render', 'front', 'view', 'detail', 'details', 'large', 'small', 'size', 'game', 'friendly', 'texture', 'textures')
                                # try to map common english nouns to japanese
                                jp = EN_TO_JP_SIMPLE.get(low)
                                if not jp:
                                    # if token contains '-' like 'voxel-style', try last part
                                    if '-' in low:
                                        part = low.split('-')[-1]
                                        jp = EN_TO_JP_SIMPLE.get(part)
                                if jp:
                                    subject = jp
                                else:
                                    # if token is a tech token or obviously non-noun, avoid echoing it
                                    if re.match(r'^[a-z\-]+$', low) and any(tt in low for tt in tech_tokens_local):
                                        subject = 'これ'
                                    elif re.match(r'^[a-z\-]+$', low):
                                        # ascii fallback
                                        subject = low
                                    else:
                                        subject = first
                                comment = f'これ、{subject}っぽいね、かわいい〜'
                                if len(comment) > 40:
                                    comment = comment[:37] + '...'
                                return comment
                except Exception:
                    return '見つけたよ〜、すごいね〜'

            # ensure uniqueness of comments across returned list
            used_comments = set()
            suffix_variants = ['ね、かわいい〜', 'だよ〜', 'かな〜', 'すごいね〜', 'だね〜']
            def variant_comment(base: str, idx: int) -> str:
                v = suffix_variants[idx % len(suffix_variants)]
                cand = f"これ、{base}{v}"
                return cand if len(cand) <= 40 else (cand[:37] + '...')

            for idx, item in enumerate(out):
                c = (item.get('comment') or '').strip()
                if not c:
                    item['comment'] = gen_imouto_comment(item.get('text',''))
                    c = item['comment']
                else:
                    if is_mostly_english(c):
                        item['comment'] = gen_imouto_comment(item.get('text',''))
                        c = item['comment']
                # if duplicate comment, create a small variant
                if c in used_comments:
                    base = (item.get('text') or '').split()[0] if item.get('text') else 'これ'
                    item['comment'] = variant_comment(base, idx)
                used_comments.add(item['comment'])
            # If LM returned the exact same comment for all items, force index-based variants
            try:
                comments_set = set((it.get('comment') or '').strip() for it in out)
                if len(comments_set) == 1 and len(out) > 1:
                    for i, it in enumerate(out):
                        base = (it.get('text') or '').split()[0] if it.get('text') else 'これ'
                        it['comment'] = variant_comment(base, i)
            except Exception:
                pass

            # persist debug dump to cache for inspection (utf-8)
            try:
                dbg_dir = Path(CACHE_DIR)
                dbg_dir.mkdir(parents=True, exist_ok=True)
                dbg_path = dbg_dir / 'last_lm_parse_debug.json'
                dbg_path.write_text(json.dumps({'assistant_raw': assistant, 'parsed': parsed, 'final': out}, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass

            return out
    except Exception as e:
        # network or API error
        print('LMStudio call failed', e)
    # fallback to keyword scoring
    return _score_with_keywords(query, candidates)


def search_similar(query: str, top_k: int = 5, lm_url: Optional[str] = None, lm_token: Optional[str] = None, target: Optional[str] = None) -> List[Dict[str, Any]]:
    candidates = _build_candidates_from_logs()
    if not candidates:
        return []

    # Always compute a keyword baseline first (reliable, deterministic)
    keyword_baseline = _score_with_keywords(query, candidates)

    # If no LM is configured, return keyword baseline top_k
    if not lm_url:
        return keyword_baseline[:top_k]

    # Ask LM but be defensive: if LM returns low-quality results, prefer keyword baseline
    try:
        lm_out = _call_lmstudio_chat(query, candidates, lm_url, lm_token, target=target)
    except Exception:
        lm_out = None

    def mean_score(lst: List[Dict[str, Any]]) -> float:
        if not lst: return 0.0
        return sum((it.get('score') or 0.0) for it in lst) / max(1, len(lst))

    # If LM failed or returned nothing meaningful, use keyword baseline
    if not lm_out:
        return keyword_baseline[:top_k]

    # Remove obviously empty-text items from LM output
    lm_out = [it for it in lm_out if (it.get('text') or '').strip()]
    if not lm_out:
        return keyword_baseline[:top_k]

    lm_mean = mean_score(lm_out)
    kb_mean = mean_score(keyword_baseline)

    # If LM average score is significantly worse than keyword baseline, prefer baseline
    if lm_mean + 0.01 < kb_mean:
        # Merge: prefer keyword ordering/comments but retain any positive LM scores for same ids
        kb_map = {k['id']: k for k in keyword_baseline}
        merged = []
        for kb in keyword_baseline:
            it = dict(kb)
            lm_item = next((x for x in lm_out if x.get('id') == kb.get('id')), None)
            if lm_item and (lm_item.get('score') or 0.0) > 0.0:
                it['score'] = lm_item.get('score')
            # keep kb comment if lm comment empty
            if not it.get('comment') and lm_item:
                it['comment'] = lm_item.get('comment') or ''
            merged.append(it)
        return merged[:top_k]

    # Otherwise, prefer LM ordering but ensure comments are present (fallback to generated JP)
    out = lm_out
    # Clear comments for zero-score items to avoid misleading imouto comments
    for it in out:
        try:
            if (it.get('score') or 0.0) <= 0.0:
                it['comment'] = ''
        except Exception:
            it['comment'] = ''

    # Deduplicate and filter very low-score items, keep at least one
    def _norm_text(s: str) -> str:
        return re.sub(r"\s+", ' ', (s or '').strip().lower())

    seen = set()
    deduped = []
    for it in out:
        nt = _norm_text(it.get('text',''))
        if not nt:
            continue
        if nt in seen:
            continue
        seen.add(nt)
        deduped.append(it)

    filtered = [o for o in deduped if (o.get('score') or 0.0) > 0.02]
    if not filtered and deduped:
        filtered = deduped[:min(len(deduped), top_k)]

    if not filtered:
        # fallback to keyword baseline if LM produced nothing useful
        return keyword_baseline[:top_k]

    return filtered[:top_k]


def format_for_lmstudio(query: str, candidates: List[Dict[str, Any]], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Construct a chat-style payload to send to LMStudio that enforces translation and JSON output rules.

    rules: optional dict to customize behavior, e.g. {
      'require_jp_comment': True,
      'comment_style': 'imouto',
      'max_tokens': 512
    }

    Returns a dict payload (system, user messages, and candidates) that can be POSTed to LMStudio.
    """
    if rules is None:
        rules = {}
    max_tokens = int(rules.get('max_tokens', 512))

    system = (
        IMOUTO_SYSTEM_PROMPT + '\n'
        "出力は必ず JSON 配列のみで返してください。各要素は {id, score, text, comment} を含めてください。"
    )

    # Add explicit translation instruction when query is non-latin or short
    translation_hint = ''
    if len(query.strip()) <= 4 and any(ord(ch) > 127 for ch in query):
        translation_hint = (
            "注意: 入力クエリは日本語です。候補テキストは英語の場合があります。"
            " クエリに合わせて候補の英語テキストを内部的に翻訳・照合してください。"
        )

    user_msg = (
        f"次の候補を、質問 '{query}' に類似している順にスコア付けして返してください。"
        " 出力は JSON 配列のみで、各要素は次のフィールドを含めてください: id, score(0.0-1.0), text, comment。"
        " comment は短い日本語（妹口調）で書いてください。\n"
        + translation_hint
        + "\nCandidates:\n"
        + "\n".join([f"[{c.get('id')}] { (c.get('text') or '')[:400] }" for c in candidates])
    )

    payload = {
        'model': 'gpt-4o-mini',
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user_msg}
        ],
        'max_tokens': max_tokens
    }
    return payload
