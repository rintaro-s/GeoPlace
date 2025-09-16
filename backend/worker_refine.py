"""Refine worker (skeleton) - 高品質再生成用ワーカーの骨格"""
import time


def refine_job(job_id, input_glb, output_dir):
    print(f"Refining {job_id}: {input_glb} -> {output_dir}")
    time.sleep(2)
    out_path = f"{output_dir}/refined_{int(time.time())}.glb"
    with open(out_path, 'wb') as f:
        f.write(b"GLB_REFINED_PLACEHOLDER")
    return out_path

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: worker_refine.py <job_id> <input_glb>')
    else:
        print(refine_job(sys.argv[1], sys.argv[2], '.'))
