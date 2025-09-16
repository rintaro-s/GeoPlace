import trimesh
from PIL import Image
import numpy as np
import os

def obj_png_to_glb_trimesh(obj_path, png_path, output_glb_path):
    """
    Trimeshを使用して、OBJファイルとPNGテクスチャをGLBファイルに変換します。

    Args:
        obj_path (str): 入力OBJファイルへのパス。
        png_path (str): 入力PNGテクスチャファイルへのパス。
        output_glb_path (str): 出力GLBファイルへのパス。
    """
    if not os.path.exists(obj_path):
        print(f"エラー: OBJファイルが見つかりません: {obj_path}")
        return
    if not os.path.exists(png_path):
        print(f"エラー: PNGファイルが見つかりません: {png_path}")
        return

    try:
        # OBJファイルを読み込む
        mesh = trimesh.load(obj_path)

        # PILを使用してテクスチャ画像を読み込む
        texture_image = Image.open(png_path)
        
        # モデルにテクスチャを適用する
        # OBJファイルにUV座標が含まれていることが前提
        if hasattr(mesh.visual, 'uv'):
            # TextureVisualsを使用して画像とUV座標を関連付ける
            mesh.visual = trimesh.visual.texture.TextureVisuals(
                uv=mesh.visual.uv,
                image=texture_image
            )
        else:
            print("警告: OBJファイルにUV座標が見つかりませんでした。テクスチャが適用されない可能性があります。")
            mesh.visual = trimesh.visual.TextureVisuals(image=texture_image)

        # GLB形式で保存する
        mesh.export(output_glb_path, file_type='glb')
        
        print(f"GLBファイルが正常に生成されました: {output_glb_path}")
    except Exception as e:
        print(f"GLBファイルの保存中にエラーが発生しました: {e}")

if __name__ == '__main__':
    # ファイルパスをTripoSRの出力に合わせて設定
    input_obj = r'C:\Users\s-rin\Documents\GitHub\GeoPlace\tmp\0\mesh.obj'
    input_png = r'C:\Users\s-rin\Documents\GitHub\GeoPlace\tmp\0\texture.png'
    output_glb = r'C:\Users\s-rin\Documents\GitHub\GeoPlace\tmp\textured_model.glb'

    obj_png_to_glb_trimesh(input_obj, input_png, output_glb)
