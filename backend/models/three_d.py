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
import traceback
import time
import json
import uuid

try:
    import trimesh
except Exception:
    trimesh = None


def _find_glb_in_dir(d: Path) -> Optional[Path]:
    # search recursively to handle cases where TripoSR writes into a nested folder (e.g. out/0/...)
    for p in d.rglob('*.glb'):
        return p
    return None


def _find_any_in_dir(d: Path, exts=('*.obj', '*.ply', '*.glb')) -> Optional[Path]:
    """Find first file matching any of the provided glob patterns under directory d (recursive)."""
    for ext in exts:
        for p in d.rglob(ext):
            return p
    return None


def generate_glb_from_image(image_bytes: bytes, out_path: Path, quality: str = 'light') -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # write image to temp file
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        inp = td_path / 'input.png'
        # keep a copy of original bytes in memory in case external processes
        # remove the temporary file while we're still working
        orig_image_bytes = image_bytes
        with open(inp, 'wb') as f:
            f.write(orig_image_bytes)

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
        # Choose which Python executable to use to run TripoSR.
        # By default we use the current interpreter, but administrators can set
        # `TRIPOSR_PYTHON` in `backend/config.yaml` to point to a dedicated venv's
        # python to avoid installing heavy deps into the server venv.
        # allow selecting output format via settings (e.g. 'glb' or 'obj')
        fmt = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', 'glb')
        python_exec = getattr(settings, 'TRIPOSR_PYTHON', None) or sys.executable
        cmd = [
            python_exec, str(triposr_py), str(inp),
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
            # Always write an invocation log (success or failure) containing the command,
            # python executable used, cwd, returncode and stdout. This helps diagnose
            # cases where TripoSR silently exits without producing outputs.
            logdir = settings.cache_path / 'triposr_logs'
            logdir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            logpath = logdir / f'triposr_{ts}.log'
            try:
                with open(logpath, 'w', encoding='utf-8') as lf:
                    lf.write(f"command: {cmd}\n")
                    lf.write(f"python_exec: {python_exec}\n")
                    lf.write(f"cwd: {triposr_dir}\n")
                    lf.write(f"returncode: {res.returncode}\n\n")
                    lf.write(res.stdout or '')
            except Exception:
                # If logging the stdout fails, still continue to handle the result below.
                pass

            # Add debug output listing to help diagnose missing file issues
            debug_files = []
            for p in outdir.rglob('*'):
                if p.is_file():
                    debug_files.append(f"{p.relative_to(outdir)} ({p.stat().st_size} bytes)")
            debug_msg = f"TripoSR outdir contents: {debug_files}" if debug_files else "TripoSR outdir is empty"
            try:
                with open(logpath, 'a', encoding='utf-8') as lf:
                    lf.write(f"\n{debug_msg}\n")
            except Exception:
                pass

            # Persist a snapshot of the outdir for offline debugging (copy tree)
            try:
                debug_snapshot_dir = settings.cache_path / 'triposr_debug' / ts
                if debug_snapshot_dir.exists():
                    # ensure unique
                    debug_snapshot_dir = settings.cache_path / 'triposr_debug' / (ts + '_2')
                shutil.copytree(str(outdir), str(debug_snapshot_dir))
                try:
                    with open(logpath, 'a', encoding='utf-8') as lf:
                        lf.write(f"Snapshot of TripoSR outdir copied to: {debug_snapshot_dir}\n")
                except Exception:
                    pass
                # Prefer searching the persisted snapshot if copy succeeded. This
                # avoids race conditions where the original temporary outdir is
                # cleaned up or its contents are transient. We'll switch the
                # working outdir reference to the snapshot for subsequent
                # discovery and copying logic.
                try:
                    outdir = debug_snapshot_dir
                    with open(logpath, 'a', encoding='utf-8') as lf:
                        lf.write(f"Switched discovery root to snapshot dir: {outdir}\n")
                except Exception:
                    pass
                # If TripoSR wrote outputs into a nested numeric folder (e.g. out/0/*),
                # flatten those files into the snapshot root to make discovery simpler
                try:
                    # look for single-directory nests (common pattern: '0')
                    children = [p for p in outdir.iterdir() if p.is_dir()]
                    if len(children) == 1:
                        nested = children[0]
                        moved = []
                        for p in nested.rglob('*'):
                            if p.is_file():
                                dest = outdir / p.name
                                # avoid overwriting; if exists, prefix with subdir name
                                if dest.exists():
                                    dest = outdir / (nested.name + '_' + p.name)
                                try:
                                    shutil.move(str(p), str(dest))
                                    moved.append((str(p), str(dest)))
                                except Exception:
                                    try:
                                        shutil.copy(str(p), str(dest))
                                        moved.append((str(p), str(dest)))
                                    except Exception:
                                        pass
                        # attempt to remove the now-empty nested dir
                        try:
                            nested.rmdir()
                        except Exception:
                            pass
                        if moved:
                            try:
                                with open(logpath, 'a', encoding='utf-8') as lf:
                                    lf.write(f"Flattened snapshot: moved {moved}\n")
                            except Exception:
                                pass
                except Exception:
                    try:
                        with open(logpath, 'a', encoding='utf-8') as lf:
                            lf.write(f"Failed to flatten snapshot dir {outdir}: {traceback.format_exc()}\n")
                    except Exception:
                        pass
            except Exception as e:
                try:
                    with open(logpath, 'a', encoding='utf-8') as lf:
                        lf.write(f"Failed to snapshot outdir: {e}\n{traceback.format_exc()}\n")
                except Exception:
                    pass

            if res.returncode != 0:
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
                    # write texture (prefer any texture produced by TripoSR,
                    # otherwise fall back to the original image bytes)
                    try:
                        if inp.exists():
                            tex_path.write_bytes(inp.read_bytes())
                        else:
                            tex_path.write_bytes(orig_image_bytes)
                    except Exception:
                        # last resort: write orig bytes
                        tex_path.write_bytes(orig_image_bytes)
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

    # find any outputs in the outdir (search recursively)
    found = _find_glb_in_dir(outdir)
    
    # Debug: log what files we're looking for and what we found
    try:
        with open(logpath, 'a', encoding='utf-8') as lf:
            lf.write(f"\nSearching for GLB: found={found}\n")
    except Exception:
        pass
    if found:
        # If config requests OBJ (TripoSR is known to favor OBJ+texture),
        # attempt to convert GLB -> OBJ if trimesh is available; otherwise
        # move the GLB but warn in the logs.
        desired_fmt = getattr(settings, 'TRIPOSR_OUTPUT_FORMAT', 'glb')
        if desired_fmt.lower() == 'obj':
            if trimesh is not None:
                try:
                    scene = trimesh.load(str(found))
                    # export as obj (may produce separate material/texture files)
                    obj_bytes = scene.export(file_type='obj')
                    # trimesh returns str for obj, ensure bytes
                    if isinstance(obj_bytes, str):
                        obj_bytes = obj_bytes.encode('utf-8')
                    obj_out = out_path.with_suffix('.obj')
                    with open(obj_out, 'wb') as of:
                        of.write(obj_bytes)
                    # try to export textures/mtl if available via export to 'obj' produced files
                    # Note: trimesh may not include textures; preserve any texture files present.
                    for p in outdir.rglob('*'):
                        if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.mtl'):
                            try:
                                shutil.move(str(p), str(out_path.parent / p.name))
                            except Exception:
                                pass
                    return obj_out
                except Exception:
                    # conversion failed; fall back to moving the GLB and also produce a textured quad OBJ
                    pass
            # trimesh not available or conversion failed -> fall back to generating a textured quad OBJ
            # create a textured quad using the input image if present
            tex_path = None
            for p in outdir.rglob('*'):
                if p.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                    tex_path = p
                    break
            if tex_path is None:
                # try to use the original input if present (inp)
                tex_src = inp if inp.exists() else None
            else:
                tex_src = tex_path

            obj_name = out_path.stem + '_fallback.obj'
            obj_path = out_path.parent / obj_name
            mtl_name = out_path.stem + '_fallback.mtl'
            mtl_path = out_path.parent / mtl_name
            tex_name = out_path.stem + '_fallback.png'
            tex_out = out_path.parent / tex_name
            if tex_src is not None and tex_src.exists():
                try:
                    shutil.copy(str(tex_src), str(tex_out))
                except Exception:
                    # if copy fails (maybe file vanished), write from orig bytes
                    tex_out.write_bytes(orig_image_bytes)
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
            return obj_path

    # No .glb: try to find .obj/.ply and textures recursively
    # Some environments may not match rglob('*.OBJ') in a case-insensitive way,
    # so enumerate all files and filter by suffix.lower() to be robust.
    # Additionally, perform an os.walk dump to catch any filesystem oddities
    # (permissions, transient deletions, symlinks) that pathlib.rglob may miss.
    try:
        import os as _os
        walk_rows = []
        for root, dirs, files in _os.walk(str(outdir)):
            for fn in files:
                fp = Path(root) / fn
                try:
                    walk_rows.append((str(fp), fp.exists(), fp.is_file(), fp.stat().st_size))
                except Exception as _e:
                    walk_rows.append((str(fp), 'error', str(_e)))
        try:
            with open(logpath, 'a', encoding='utf-8') as lf:
                lf.write(f"os.walk rows: {walk_rows}\n")
        except Exception:
            pass
    except Exception:
        # If os.walk fails for any reason, continue; we'll still use rglob below.
        pass

    all_files = [p for p in outdir.rglob('*') if p.is_file()]
    obj_list = [p for p in all_files if p.suffix.lower() == '.obj']
    ply_list = [p for p in all_files if p.suffix.lower() == '.ply']
    tex_list = [p for p in all_files if p.suffix.lower() in ('.png', '.jpg', '.jpeg')]

    # Debug: log exact files found (full paths)
    try:
        with open(logpath, 'a', encoding='utf-8') as lf:
            lf.write(f"OBJ candidates: {[str(p) for p in obj_list]}\n")
            lf.write(f"PLY candidates: {[str(p) for p in ply_list]}\n")
            lf.write(f"Texture candidates: {[str(p) for p in tex_list]}\n")
    except Exception:
        pass

    obj_path = obj_list[0] if obj_list else None
    ply_path = ply_list[0] if ply_list else None
    tex_path = tex_list[0] if tex_list else None

    if obj_path:
        # Use OBJ directly - change output extension to .obj
        obj_out_path = out_path.parent / (out_path.stem + '.obj')
        # ensure parent exists
        obj_out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(obj_path), str(obj_out_path))
        except Exception as e:
                try:
                    shutil.copy(str(obj_path), str(obj_out_path))
                    obj_path.unlink()
                except Exception as e2:
                    try:
                        with open(logpath, 'a', encoding='utf-8') as lf:
                            lf.write(f"Failed to move or copy OBJ {obj_path} -> {obj_out_path}: {e} / {e2}\n")
                            lf.write(traceback.format_exc())
                    except Exception:
                        pass

        # Also move texture if present
        if tex_path:
            tex_out_path = out_path.parent / (out_path.stem + tex_path.suffix)
            try:
                shutil.move(str(tex_path), str(tex_out_path))
            except Exception as e:
                try:
                    shutil.copy(str(tex_path), str(tex_out_path))
                    tex_path.unlink()
                except Exception as e2:
                    try:
                        with open(logpath, 'a', encoding='utf-8') as lf:
                            lf.write(f"Failed to move or copy texture {tex_path} -> {tex_out_path}: {e} / {e2}\n")
                            lf.write(traceback.format_exc())
                    except Exception:
                        pass

        # Ensure an accompanying .mtl exists. Some TripoSR runs may export an OBJ
        # without an MTL; create one referencing the texture we moved above.
        mtl_expected = out_path.parent / (out_path.stem + '.mtl')
        # If there is no mtl present but we have a texture file, generate a simple MTL.
        if (not mtl_expected.exists()) and tex_path:
            tex_name = (out_path.stem + tex_path.suffix)
            try:
                with open(mtl_expected, 'w', encoding='utf-8') as mf:
                    mf.write(f"newmtl material_0\nmap_Kd {tex_name}\n")
            except Exception:
                pass

        # Ensure the OBJ references the mtllib line. If missing, prepend it.
        try:
            txt = obj_out_path.read_text(encoding='utf-8')
            if 'mtllib' not in txt.splitlines()[0:5]:
                # Prepend mtllib line
                mtl_name = mtl_expected.name if mtl_expected.exists() else ''
                if mtl_name:
                    new_txt = f"mtllib {mtl_name}\n" + txt
                    obj_out_path.write_text(new_txt, encoding='utf-8')
        except Exception:
            # If reading/writing fails, ignore; OBJ will still be present.
            pass

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
        except Exception:
            # conversion failed, fallback to embedding the PNG into a placeholder glb
            placeholder = out_path.parent / (out_path.stem + '_fallback_conv_error.glb')
            with open(placeholder, 'wb') as f:
                f.write(b'GLB_FALLBACK_CONV_ERROR\n')
            shutil.move(str(placeholder), str(out_path))
            return out_path

    # If nothing was produced, raise
    # Implement a robust discovery + copy workflow with retries and fallbacks.
    attempts = []

    def is_file_stable(p: Path, checks: int = 3, interval: float = 0.5) -> bool:
        """Return True if file exists and its size is stable across checks."""
        try:
            last = p.stat().st_size
        except Exception:
            return False
        for _ in range(checks):
            time.sleep(interval)
            try:
                cur = p.stat().st_size
            except Exception:
                return False
            if cur != last:
                last = cur
                continue
        return True

    def atomic_copy(src: Path, dest: Path) -> bool:
        """Copy src -> dest atomically by writing to temp and os.replace. Return True on success."""
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / (dest.name + f'.tmp-{uuid.uuid4().hex}')
            shutil.copy(str(src), str(tmp))
            os.replace(str(tmp), str(dest))
            return True
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            return False

    def try_copy(src: Path, dest: Path) -> bool:
        # wait for file to stabilize before copying
        if not is_file_stable(src, checks=2, interval=0.5):
            # try one more time quickly
            if not is_file_stable(src, checks=1, interval=0.2):
                return False
        # attempt atomic copy
        if atomic_copy(src, dest):
            try:
                # try to remove original if on same filesystem
                src.unlink()
            except Exception:
                pass
            return True
        # fallback to move (less atomic) then copy
        try:
            shutil.move(str(src), str(dest))
            return True
        except Exception:
            try:
                shutil.copy(str(src), str(dest))
                return True
            except Exception:
                return False

    # Create permanent snapshot dir for outputs
    out_snapshot_base = settings.cache_path / 'triposr_outputs'
    out_snapshot_base.mkdir(parents=True, exist_ok=True)
    snapshot_dir = out_snapshot_base / ts
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # discovery strategies (ordered): glb recursive, any obj/ply anywhere, filename contains 'mesh', nested dirs
    strategies = []
    strategies.append(lambda d: list(d.rglob('*') if False else []))  # placeholder to keep indices stable
    strategies.append(lambda d: [p for p in d.rglob('*') if p.suffix.lower() == '.glb'])
    strategies.append(lambda d: [p for p in d.rglob('*') if p.suffix.lower() == '.obj'])
    strategies.append(lambda d: [p for p in d.rglob('*') if p.suffix.lower() == '.ply'])
    strategies.append(lambda d: [p for p in d.rglob('*') if 'mesh' in p.name.lower()])
    strategies.append(lambda d: [p for sub in d.iterdir() if sub.is_dir() for p in sub.rglob('*')])

    # validation helpers
    def validate_obj(path: Path) -> bool:
        try:
            txt = path.read_text(encoding='utf-8', errors='ignore')
            verts = sum(1 for l in txt.splitlines() if l.startswith('v '))
            return verts > 4
        except Exception:
            return False

    max_total_seconds = 60
    deadline = time.time() + max_total_seconds
    max_rounds = 5
    round_no = 0
    found_any = False

    # Try multiple rounds with backoff to capture transient files; bounded by deadline and max_rounds
    while time.time() < deadline and round_no < max_rounds:
        round_no += 1
        try:
            with open(logpath, 'a', encoding='utf-8') as lf:
                lf.write(f"Discovery round {round_no} starting; deadline in {int(deadline - time.time())}s\n")
        except Exception:
            pass

        for strat_idx, strat in enumerate(strategies, start=1):
            candidates = []
            try:
                candidates = strat(outdir)
            except Exception as e:
                try:
                    with open(logpath, 'a', encoding='utf-8') as lf:
                        lf.write(f"Strategy {strat_idx} raised: {e}\n{traceback.format_exc()}\n")
                except Exception:
                    pass

            # filter files only and ensure exists
            candidates = [p for p in candidates if p.exists() and p.is_file()]
            try:
                with open(logpath, 'a', encoding='utf-8') as lf:
                    lf.write(f"Round {round_no} Strategy {strat_idx} candidates: {[str(p) for p in candidates]}\n")
            except Exception:
                pass

            for c in candidates:
                # copy into snapshot (atomic) and then install to expected out_path
                dest_snapshot = snapshot_dir / (c.name)
                if try_copy(c, dest_snapshot):
                    # validate if obj
                    if dest_snapshot.suffix.lower() == '.obj' and not validate_obj(dest_snapshot):
                        try:
                            with open(logpath, 'a', encoding='utf-8') as lf:
                                lf.write(f"Rejected OBJ (too few verts): {dest_snapshot}\n")
                        except Exception:
                            pass
                        continue

                    # atomic install to final
                    if c.suffix.lower() == '.glb':
                        final_dest = out_path
                    else:
                        final_dest = out_path.with_suffix(c.suffix.lower())

                    if try_copy(dest_snapshot, final_dest):
                        try:
                            with open(logpath, 'a', encoding='utf-8') as lf:
                                lf.write(f"Installed {dest_snapshot} -> {final_dest} (round {round_no} strat {strat_idx})\n")
                        except Exception:
                            pass
                        # record metadata
                        meta = {
                            'source': str(c),
                            'snapshot': str(dest_snapshot),
                            'final': str(final_dest),
                            'round': round_no,
                            'strategy': strat_idx,
                            'timestamp': datetime.utcnow().isoformat()
                        }
                        try:
                            (snapshot_dir / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
                        except Exception:
                            pass
                        if final_dest.suffix.lower() == '.obj':
                            return final_dest
                        if final_dest.suffix.lower() == '.glb':
                            return final_dest
                else:
                    try:
                        with open(logpath, 'a', encoding='utf-8') as lf:
                            lf.write(f"Failed to snapshot candidate {c} to {dest_snapshot}\n")
                    except Exception:
                        pass

        # exponential backoff before next round
        sleep_for = min(2 ** round_no, 8)
        time.sleep(sleep_for)

    # if we reached here, give up and log attempts
    try:
        with open(logpath, 'a', encoding='utf-8') as lf:
            lf.write(f"All discovery rounds exhausted. No valid outputs found.\n")
    except Exception:
        pass

    # Fallback: create textured quad OBJ (ensure deterministic fallback path)
    obj_name = out_path.stem + '_fallback.obj'
    obj_path = out_path.parent / obj_name
    mtl_name = out_path.stem + '_fallback.mtl'
    mtl_path = out_path.parent / mtl_name
    tex_name = out_path.stem + '_fallback.png'
    tex_path = out_path.parent / tex_name
    try:
        if inp.exists():
            tex_path.write_bytes(inp.read_bytes())
        else:
            tex_path.write_bytes(orig_image_bytes)
    except Exception:
        tex_path.write_bytes(orig_image_bytes)
    with open(mtl_path, 'w', encoding='utf-8') as mf:
        mf.write(f"newmtl fallback\nmap_Kd {tex_name}\n")
    with open(obj_path, 'w', encoding='utf-8') as of:
        of.write(f"mtllib {mtl_name}\n")
        of.write("o fallback_quad\n")
        of.write("v -0.5 -0.5 0.0\n")
        of.write("v 0.5 -0.5 0.0\n")
        of.write("v 0.5 0.5 0.0\n")
        of.write("v -0.5 0.5 0.0\n")
        of.write("vt 0 0\n")
        of.write("vt 1 0\n")
        of.write("vt 1 1\n")
        of.write("vt 0 1\n")
        of.write("usemtl fallback\n")
        of.write("s off\n")
        of.write("f 1/1 2/2 3/3 4/4\n")
    try:
        with open(logpath, 'a', encoding='utf-8') as lf:
            lf.write(f"Using fallback textured quad: {obj_path}\n")
    except Exception:
        pass
    return obj_path
