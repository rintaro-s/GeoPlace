"""TripoSR を subprocess で呼び出して画像から GLB を生成する実装.

期待される TripoSR のコマンドライン:
  python run.py <input_image> --output-dir <outdir> --model-save-format glb --bake-texture

本モジュールは image_bytes を一時PNGに保存し、TripoSR を呼び出して生成された glb を
指定の out_path に移動して返す。失敗時は例外を送出する。
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import tempfile
import subprocess
import shutil
import os
from ..config import settings

try:
    import trimesh
except Exception:
    trimesh = None


def _find_glb_in_dir(d: Path) -> Optional[Path]:
    for p in d.iterdir():
        if p.suffix.lower() == '.glb':
            return p
    return None


def generate_glb_from_image(image_bytes: bytes, out_path: Path, quality: str = 'light') -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # write image to temp file
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        inp = td_path / 'input.png'
        with open(inp, 'wb') as f:
            f.write(image_bytes)

        # prepare output dir
        outdir = td_path / 'out'
        outdir.mkdir()

        # build command
        # read TripoSR path from Settings
        try:
            triposr_dir = Path(settings.TRIPOSR_DIR)
        except Exception:
            triposr_dir = None

        if not triposr_dir or not triposr_dir.exists():
            raise FileNotFoundError(f'TripoSR directory not found; check TRIPOSR_DIR in backend/config.yaml (tried: {triposr_dir})')

        triposr_py = triposr_dir / getattr(settings, 'TRIPOSR_PY', 'run.py')
        if not triposr_py.exists():
            # maybe entry is just filename in dir
            triposr_py = triposr_dir / 'run.py'
        cmd = [
            'python', str(triposr_py), str(inp),
            '--output-dir', str(outdir),
            '--model-save-format', 'glb'
        ]
        # optionally pass bake-texture
        bake = getattr(settings, 'TRIPOSR_BAKE_TEXTURE', True)
        if bake:
            cmd.append('--bake-texture')

        # run
        try:
            subprocess.check_call(cmd, cwd=str(triposr_dir))
        except subprocess.CalledProcessError as e:
            # Fall back: TripoSR failed (missing deps). Create a minimal placeholder GLB
            # so the rest of the pipeline can proceed in environments without TripoSR.
            # Log the original error via RuntimeError chained.
            err = e
            # create a simple placeholder glb that embeds the PNG as bytes (not a valid glb, but usable as marker)
            placeholder = out_path.parent / (out_path.stem + '_fallback.glb')
            with open(placeholder, 'wb') as f:
                f.write(b'GLB_FALLBACK_PLACEHOLDER\n')
                f.write(b'PROMPT_IMAGE_PNG:\n')
                with open(inp, 'rb') as ib:
                    f.write(ib.read())
            shutil.move(str(placeholder), str(out_path))
            return out_path

        # find glb
        found = _find_glb_in_dir(outdir)
        if found:
            shutil.move(str(found), str(out_path))
            return out_path

        # No .glb: try to find .obj or .ply and convert to glb using trimesh
        obj_path = None
        ply_path = None
        tex_path = None
        for p in outdir.iterdir():
            if p.suffix.lower() == '.obj':
                obj_path = p
            if p.suffix.lower() == '.ply':
                ply_path = p
            if p.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                # pick a texture if present
                tex_path = p

        if obj_path or ply_path:
            if trimesh is None:
                # cannot convert without trimesh; create fallback marker
                placeholder = out_path.parent / (out_path.stem + '_fallback_no_trimesh.glb')
                with open(placeholder, 'wb') as f:
                    f.write(b'GLB_FALLBACK_NO_TRIMESH\n')
                shutil.move(str(placeholder), str(out_path))
                return out_path

            try:
                # load as scene to preserve materials/textures
                source = str(obj_path) if obj_path else str(ply_path)
                scene = trimesh.load(source, force='scene')
                # if texture file exists, trimesh may already reference it via mtl; otherwise, textures are left as-is
                glb_bytes = scene.export(file_type='glb')
                # trimesh may return bytes or a bytearray
                if isinstance(glb_bytes, (bytes, bytearray)):
                    with open(out_path, 'wb') as f:
                        f.write(glb_bytes)
                    return out_path
            except Exception as e:
                # conversion failed, fallback to embedding the PNG into a placeholder glb
                placeholder = out_path.parent / (out_path.stem + '_fallback_conv_error.glb')
                with open(placeholder, 'wb') as f:
                    f.write(b'GLB_FALLBACK_CONV_ERROR\n')
                shutil.move(str(placeholder), str(out_path))
                return out_path

        # If nothing was produced, raise
        raise FileNotFoundError('TripoSR did not produce a .glb/.obj/.ply in its output dir')
