"""SD worker script — runs in a separate venv/python and generates an image using diffusers.

Usage:
  python sd_worker.py --prompt "A cat" --out out.png --model runwayml/stable-diffusion-v1-5

The script prints JSON to stdout with keys: status, out (path) or error.
"""
import argparse
import json
from pathlib import Path
from io import BytesIO

parser = argparse.ArgumentParser()
parser.add_argument('--prompt', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--model', default='runwayml/stable-diffusion-v1-5')
parser.add_argument('--steps', type=int, default=20)
parser.add_argument('--width', type=int, default=512)
parser.add_argument('--height', type=int, default=512)
args = parser.parse_args()

try:
    from diffusers import StableDiffusionPipeline
    import torch
    pipe = StableDiffusionPipeline.from_pretrained(args.model)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda':
        pipe = pipe.to('cuda')
    out = pipe(args.prompt, num_inference_steps=args.steps, height=args.height, width=args.width)
    image = out.images[0]
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    image.save(outp)
    print(json.dumps({'status':'ok','out':str(outp)}))
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    print(json.dumps({'status':'error','error':str(e),'trace':tb}))
    raise SystemExit(2)
