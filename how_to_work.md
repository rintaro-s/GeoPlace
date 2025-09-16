# GeoPlace / dot2world 開発ワークフロー (更新版)

## 目的概要
巨大ドットキャンバス (22400x21966) をタイル (32x32) 単位で編集し、AI パイプライン (VLM -> Stable Diffusion -> 3D生成 -> Open3D 後処理) によって 3D オブジェクト化し A-Frame ワールドへ配置する。

現段階: VLM/SD/3D はダミー出力（テキスト埋め込みPNG + プレースホルダGLB）で動作し、パイプライン呼び出し/キャッシュ/リファイン2段階の制御・UI・WebSocket進捗通知までを実装済み。

## ディレクトリ概要
- backend/main.py : FastAPI + WebSocket + ThreadPoolExecutor ジョブ + 静的配信(frontend, assets)
- backend/pipeline.py : VLM -> SD -> 3D -> refine の骨格 + キャッシュ (SHA256)
- backend/models/*.py : 個別モデルローダ/ダミー実装
- backend/config.(yaml|py) : 設定値/パス定義
- assets/glb/ : 生成 GLB (light / refined)
- data/canvas.png : 巨大キャンバス (初回アクセス時生成)
- frontend/paint.html : パン/ズーム/描画/タイル選択/手動生成/WS進捗
- frontend/world.html : A-Frame + WS リアルタイム反映

## 起動手順
```
python -m venv venv
./venv/Scripts/Activate.ps1
pip install -r requirements.txt
python backend/main.py
# ブラウザで
#   http://localhost:8001/frontend/paint.html
#   http://localhost:8001/frontend/world.html
```

## 差分管理フロー
1. paint.html ローカルで変更タイルを Uint8ClampedArray に反映
2. Shift+クリックでタイル選択トグル (選択が無ければ「変更タイルすべて」)
3. 送信時 `/api/paint` (JSON: RGBA 配列) でサーバに差分適用
4. `/api/generate` がジョブを起動し light パイプライン実行
5. 完了後 (light_ready) → すぐ refine ステップ (refined_ready)
6. WebSocket `/ws` が `job_progress` / `job_done` を push → world が再取得

## パイプライン (ダミー実装詳細)
- VLM: `vlm.extract_attributes` が固定の属性を返却
- Prompt: voxel-style テンプレ
- SD: プロンプト文字を描画した 512x512 PNG バイト生成
- 3D: `generate_glb_from_image` が placeholder GLB を書出し
- refine: light GLB に `_REFINED` バイト付与コピー
- キャッシュ: タイル RGBA PNG の SHA256 をキーに light 結果を再利用

## キャッシュレイアウト
`backend/cache/pipe/<sha256>.json` に meta, `assets/glb/<sha256>_light.glb`

## WebSocket メッセージ例
```json
{ "type":"job_progress", "job_id":"job_173...", "stage":"light", "entry": {"id": "tile_10_5", ...} }
{ "type":"job_done", "job_id":"job_173...", "stage":"refine" }
```

## objects.json レコード例
```json
{
  "id": "tile_100_42",
  "x": 320.0,
  "y": 0,
  "z": 134.4,
  "rotation": [0,0,0],
  "scale": 1.0,
  "glb_url": "/assets/glb/2f..._light.glb",
  "quality": "light",
  "meta": {"prompt": "voxel-style object ..."}
}
```
Refine 後は `quality":"refined"` と `meta_refined` 追加。

## 今後の本実装差し替えポイント
| ステップ | 現在 | 置き換え案 |
|----------|------|------------|
| VLM | ダミー関数 | Gemma3-Vision (transformers) or LLaVA |
| SD | テキスト描画 | diffusers StableDiffusionPipeline (fp16) |
| 3D | バイト置換 | TripoSR / Point-E / Shap-E + Open3D 処理 |
| キャッシュ | ローカル JSON | Redis / MinIO / S3 + メタDB |

## 性能最適化メモ
- タイル送信を RLE などで圧縮
- /api/paint をバッチ化 (複数タイルまとめ)
- ThreadPoolExecutor → asyncio + GPU ジョブキュー (priority / rate-limit)

## テスト観点
- ジョブ進捗が WebSocket で順序通り届くか (light -> refining -> refined)
- キャッシュヒット時速度 (2回目同一タイル生成が即座になるか)
- 大量同時生成 (max_workers 超過時のキュー動作)

## セキュリティ / 考慮
- 現在は認証無し: CSRF/濫用対策未
- 本番導入時: API Key or OIDC + レートリミット (per IP / per user)

## 置換実装ガイド (例: Stable Diffusion)
```python
from diffusers import StableDiffusionPipeline
import torch
pipe = StableDiffusionPipeline.from_pretrained(
    'runwayml/stable-diffusion-v1-5', torch_dtype=torch.float16
).to('cuda')
pipe.enable_attention_slicing()
image = pipe(prompt, num_inference_steps=20, guidance_scale=7.5).images[0]
```

## よくある落とし穴
- 巨大 PNG 直書きの I/O 遅延 → メモリキャッシュ or 分割保存
- WebSocket ブロードキャストでの同期呼び出し (asyncio.run) 多用 → 大量同時接続で負荷、将来は専用タスクキューに集約
- 生成ファイル肥大化 (glb) → decimation + gzip or Draco

---
開発段階ロードマップ: VLM 置換 → SD 実装 → 3D 変換接続 → Open3D 後処理 → キャッシュ永続化 → Undo/Redo / バージョン履歴。
