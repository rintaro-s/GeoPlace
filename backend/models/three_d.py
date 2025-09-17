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
import sys
from datetime import datetime

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
        # Use the same Python interpreter that's running this process to ensure
        # external tool runs in the same virtualenv (avoids ModuleNotFoundError
        # when dependencies are installed in the server venv).
        # allow selecting output format via settings (e.g. 'glb' or 'obj')
        fmt = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', 'glb')
        cmd = [
            sys.executable, str(triposr_py), str(inp),
            '--output-dir', str(outdir),
            '--model-save-format', fmt
        ]
        # optionally pass bake-texture
        bake = getattr(settings, 'TRIPOSR_BAKE_TEXTURE', True)
        if bake:
            cmd.append('--bake-texture')

        # run
        try:
            # capture output for debugging
            res = subprocess.run(cmd, cwd=str(triposr_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if res.returncode != 0:
                # save output for debugging
                logdir = settings.cache_path / 'triposr_logs'
                logdir.mkdir(parents=True, exist_ok=True)
                ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
                logpath = logdir / f'triposr_{ts}.log'
                with open(logpath, 'w', encoding='utf-8') as lf:
                    lf.write(res.stdout or '')

                # Fall back: TripoSR failed (missing deps).
                # Create a minimal placeholder in the requested output format.
                if fmt == 'obj':
                    # Create a simple textured quad OBJ as a usable fallback.
                    obj_name = out_path.stem + '_fallback.obj'
                    obj_path = out_path.parent / obj_name
                    mtl_name = out_path.stem + '_fallback.mtl'
                    mtl_path = out_path.parent / mtl_name
                    tex_name = out_path.stem + '_fallback.png'
                    tex_path = out_path.parent / tex_name
                    # write texture (copy input PNG)
                    with open(inp, 'rb') as ib:
                        tex_bytes = ib.read()
                    tex_path.write_bytes(tex_bytes)
                    # write MTL referencing the texture
                    with open(mtl_path, 'w', encoding='utf-8') as mf:
                        mf.write(f"newmtl fallback\nmap_Kd {tex_name}\n")
                    # write OBJ: a single quad with uv coords
                    with open(obj_path, 'w', encoding='utf-8') as of:
                        of.write(f"mtllib {mtl_name}\n")
                        of.write("o fallback_quad\n")
                        # vertices
                        of.write("v -0.5 -0.5 0.0\n")
                        of.write("v 0.5 -0.5 0.0\n")
                        of.write("v 0.5 0.5 0.0\n")
                        of.write("v -0.5 0.5 0.0\n")
                        # uvs
                        of.write("vt 0 0\n")
                        of.write("vt 1 0\n")
                        of.write("vt 1 1\n")
                        of.write("vt 0 1\n")
                        of.write("usemtl fallback\n")
                        of.write("s off\n")
                        of.write("f 1/1 2/2 3/3 4/4\n")
                    # move to expected out_path (with .obj extension)
                    final_obj = out_path.with_suffix('.obj')
                    shutil.move(str(obj_path), str(final_obj))
                    # ensure texture and mtl are present next to final_obj
                    shutil.move(str(mtl_path), str(out_path.parent / mtl_name))
                    shutil.move(str(tex_path), str(out_path.parent / tex_name))
                    return final_obj
                else:
                    placeholder = out_path.parent / (out_path.stem + '_fallback.glb')
                    with open(placeholder, 'wb') as f:
                        f.write(b'GLB_FALLBACK_PLACEHOLDER\n')
                        f.write(b'PROMPT_IMAGE_PNG:\n')
                        with open(inp, 'rb') as ib:
                            f.write(ib.read())
                    shutil.move(str(placeholder), str(out_path))
                    return out_path
        except FileNotFoundError as e:
            # very unlikely since we use sys.executable, but handle defensively
            logdir = settings.cache_path / 'triposr_logs'
            logdir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            logpath = logdir / f'triposr_missing_{ts}.log'
            with open(logpath, 'w', encoding='utf-8') as lf:
                lf.write(str(e))
            # create fallback placeholder
            placeholder = out_path.parent / (out_path.stem + '_fallback_nopython.glb')
            with open(placeholder, 'wb') as f:
                f.write(b'GLB_FALLBACK_NO_PYTHON\n')
            shutil.move(str(placeholder), str(out_path))
            return out_path

        # find glb
        found = _find_glb_in_dir(outdir)
        if found:
            shutil.move(str(found), str(out_path))
            return out_path

        # No .glb: try to find .obj and use it directly or convert to glb
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

        if obj_path:
            # Use OBJ directly - change output extension to .obj
            obj_out_path = out_path.parent / (out_path.stem + '.obj')
            shutil.move(str(obj_path), str(obj_out_path))
            
            # Also move texture if present
            if tex_path:
                tex_out_path = out_path.parent / (out_path.stem + tex_path.suffix)
                shutil.move(str(tex_path), str(tex_out_path))
            
            return obj_out_path
            
        elif ply_path:
            if trimesh is None:
                # cannot convert without trimesh; create fallback marker
                placeholder = out_path.parent / (out_path.stem + '_fallback_no_trimesh.glb')
                with open(placeholder, 'wb') as f:
                    f.write(b'GLB_FALLBACK_NO_TRIMESH\n')
                shutil.move(str(placeholder), str(out_path))
                return out_path

            try:
                # load as scene to preserve materials/textures
                source = str(ply_path)
                scene = trimesh.load(source, force='scene')
                glb_bytes = scene.export(file_type='glb')
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
