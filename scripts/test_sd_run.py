"""Simple test runner for the project's Stable Diffusion wrapper.

Behaviour:
- activates project's sd loader `backend.models.sd.load_sd_model`
- tries to generate an image for a simple prompt
- saves the generated PNG into `backend/cache/pipe/<hash>_sd.png`
- prints model status and basic image stats

Run with the project's venv activated:
& .\venv\Scripts\Activate.ps1; python scripts/test_sd_run.py
"""
from pathlib import Path
import hashlib
from backend.config import settings
from backend.models import sd
from PIL import Image, ImageStat

PROMPT = "A colorful toy house, low poly, game asset, front view"

def _hash_prompt(p: str) -> str:
    return hashlib.sha256(p.encode('utf-8')).hexdigest()


def main():
    print('Project cache path:', settings.cache_path)
    model_id = None
    try:
        cfg = __import__('backend.config', fromlist=['get_config'])
        model_id = cfg.get_config().get('SD_MODEL_ID')
    except Exception:
        model_id = None
    print('Configured SD model id:', model_id)

    model = sd.load_sd_model(model_id)
    print('SD model loaded?', model is not None)

    h = _hash_prompt(PROMPT)[:16]
    outdir = settings.cache_path / 'pipe'
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f"{h}_sd.png"

    img_bytes = sd.generate_image(model, PROMPT)
    outpath.write_bytes(img_bytes)
    print('Wrote SD output to', outpath)

    im = Image.open(outpath).convert('RGBA')
    stat = ImageStat.Stat(im)
    print('Image size:', im.size)
    print('Channel means:', stat.mean)
    print('Channel extrema:', stat.extrema)
    # quick uniqueness test
    px = list(im.getdata())
    rset = set(p[0] for p in px)
    print('unique R values:', len(rset))

if __name__ == '__main__':
    main()
