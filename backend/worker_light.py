"""Light worker (skeleton) - VLM -> SD -> 3Dgen (light) -> Open3D -> save glb

実装の詳細はプラグインに委ねる。ここでは処理フローの骨格のみを示す。
"""
import time


def process_tile(tile_path, output_dir):
    # ダミー処理: 実際は VLM 抽出 -> SD -> 3Dgen
    print(f"Processing {tile_path} -> {output_dir}")
    time.sleep(1)
    out_path = f"{output_dir}/obj_{int(time.time())}.glb"
    # ダミー出力作成
    with open(out_path, 'wb') as f:
        f.write(b"GLB_PLACEHOLDER")
    return out_path

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: worker_light.py <tile_path> <output_dir>')
    else:
        print(process_tile(sys.argv[1], sys.argv[2]))
