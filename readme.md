# GeoPlace / dot2world

巨大ドットキャンバスをタイル単位で編集し AI パイプライン (VLM -> Stable Diffusion -> 3D生成 -> Refine) により 3D ワールドへ反映するプロトタイプ実装です。(現段階: モデル生成部はダミー) 

## 主なフロントエンド
- `/frontend/paint.html` : パン / ズーム / ペン / タイル選択 (Shift+クリック) / 変更タイル送信 / 3D生成トリガ / WebSocket 進捗表示
- `/frontend/world.html` : A-Frame ワールド表示 (WebSocket で更新反映, light→refined の段階的差し替え)

## 起動 - 重要！
**必ずサーバを起動してからブラウザでアクセスしてください**

```powershell
# 1. 仮想環境をアクティベート
python -m venv venv
./venv/Scripts/Activate.ps1

# 2. 依存関係をインストール
pip install -r requirements.txt

# 3. サーバを起動 (推奨方法)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

# または直接実行
python backend/main.py
```

## 設定
`backend/config.yaml` でタイルサイズ/ワーカー数/リファイン有無などを調整可能。

## キャッシュ
`backend/pipeline.py` がタイル PNG (RGBA) を SHA256 でキャッシュキー化し、light 結果を再利用。

## 追加ドキュメント
詳細ワークフロー / 置換ガイド: `how_to_work.md`

---
以下、元仕様書 (参考 / 将来の本実装指針):

**GeoPlace 仕様書**


このプロジェクトは、複数のユーザーが「20,000×20,000ピクセルくらいの大きなcanvas PNG画像」にドットを置いてみんなで、canvas画像の上に絵を描いて共有することができるものを提供する。
置かれたドットを解析し、AIによって「何が描かれたか」をざっくり理解して簡易的な3Dオブジェクトを生成。
全ユーザーは同じ3Dワールドを共有し、ブラウザから自由に歩き回ったり、テレポートして探索できる。

# dot2world — 最適確定仕様（VLM → SD1.5 → 3Dgen（TripoSR等）ワークフロー）

**目的**
ドット絵（小領域）をAIで詳しく「解釈（カテゴリ、色、大きさ、向き、ディテール）」してから、Stable Diffusion 1.5（軽量設定）で単一視点画像を生成し、TripoSR 等の軽量3D生成器で3Dメッシュを作成、glTFにして A-frame 上の共有ワールドに配置する。

## 全体フロー（要点）

1. クライアントが canvas.pngキャンバス上でタイル（TILE_PX=32）を編集 → 差分タイルをサーバへ送信。タイル分けは事前にしておいて、どこで切り取られるかがユーザーにわかるようになっている。共同で同時編集も可能。

2. サーバは差分タイルの bbox を切り出し、**VLM（LMstudio上のGemma3）** に投げて属性を抽出（ラベル・色・大きさ・向き・意図的なメタ情報）。

3. 属性を元に**プロンプトテンプレ**を自動生成。

4. Stable Diffusion v1.5（軽量/FP16）で単一視点（正面）画像を生成（ControlNet や inpainting を併用可）。

5. 生成画像を **TripoSR 等の軽量 2D→3D モデル** に渡して点群／メッシュを生成。（なお、TripoSRはobj+png。後記でGLBとタイポするかも知れないがobj+pngです。）

6. Open3D で簡易クリーニング（ノイズ除去・法線推定・単純なリトポ

7. 生成 OBJ を `objects.json` に登録して A-frame ワールドに差し替え・配置する（全ユーザ共通）。

8. 3Dワールドを、wasdとマウスで自由に行きできる。スペースやシフトで上下移動なども。座標を入力することでテレポートも可能。

## 使用モデル（最小必須／DL方法）

> すべて「学習済みモデルを利用」。事前学習・Fine-tune は行わない。

1. **VLM（画像→属性抽出） — 優先候補**

   * 利用例：LMstudioの`Gemma3-Vision`を使用する。

```

messages\_content = [
{
"type": "image\_url",
"image\_url": {
"url": f"data:image/jpeg;base64,{base64\_image\_string}"
}
},
{
"type": "text",
"text": "この画像に何が写っているか詳しく説明してください。"
}
]

```

* 取得方法：Hugging Face のリポジトリ名を指定して `transformers`/`accelerate` でロード。

* 役割：カテゴリ（house/tree/river/person 等）、色（dominant colors）、相対大きさ（小/中/大）、向き（縦横、斜め）、特徴語句（窓, 屋根, 柱）を返す。

### LMStudio(Gemma3) の接続方法

このリポジトリは LMStudio の HTTP エンドポイントに画像を POST して構造化 JSON を得る実装を持ちます。`backend/config.yaml` の以下を設定してください：

- VLM_URL: LMStudio のエンドポイント URL
- VLM_TOKEN: 必要なら Bearer トークン
- VLM_MODE: リクエスト形式。`image_b64`（デフォルト）、`openai_chat`（Chat-like messages）、`multipart`（ファイルアップロード）のいずれか。

例（LMStudio が Chat 形式を期待する場合）:

VLM_URL: "http://127.0.0.1:1234/v1/chat/completions"
VLM_MODE: "openai_chat"
VLM_TOKEN: "<your-token>"

この設定でサーバを再起動すれば、パイプラインは LMStudio に画像を投げて属性を取得します。サーバ側のレスポンスは `backend/cache/vlm_logs` に保存されます。

2. **CLIP（類似検索）**

* 利用：VLM抽出のバックアップ／テンプレ検索用の埋め込み

* 取得：`open_clip_torch` を pip でインストール／モデルを HF から取得

3. **Stable Diffusion v1.5（軽量）**

* モデル：`runwayml/stable-diffusion-v1-5`（diffusers 経由で取得）

* 取得方法（簡易）

```

pip install diffusers transformers accelerate safetensors

```

* 設定：FP16、低解像度（512×512）で高速化。単一視点（正面）画像を生成。モデルはデフォルトのキャッシュディレクトリにダウンロードされます。

4. **軽量3D生成器（実装プラグイン）**

* 優先：`TripoSR` をプラグイン可能に用意。

```

cd E:\\GITS\\TripoSR-main
python run.py path/to/input_image.png --output-dir path/to/output --bake-texture --texture-resolution 512

```

* 役割：単一の画像 → 点群／メッシュ変換

5. **Open3D**

* 役割：点群クリーニング、メッシュ化（Poisson / Ball Pivoting）、glTF 出力

* 取得：`pip install open3d`

## プロンプト設計（テンプレ化）

VLM の出力を構造化（JSON）して、PromptBuilder がテンプレートに収める。例：

```

# VLM 出力例

{
"category": "house",
"colors": ["red", "white"],
"size": "medium",
"orientation": "front-right",
"details": ["chimney", "two windows", "sloped roof"]
}

# Prompt template (voxel / minecraft style)

"voxel-style {category}, {size}, primary colors: {colors}, details: {details}, low-poly, game-friendly, 3D render, front view"

```

* 上記を用いて **単一視点プロンプト** を作る

* SD 出力は「512×512 × 1 image」を標準とする

## 画像生成（SD）設定（最適化）

* 解像度：512×512（高速化のため）

* サンプラー：Euler a / DPM++（環境で最速のもの）

* ステップ数：20〜30（品質/速度トレード）

* Guidance scale：7.0〜9.0

* FP16 & attention slicing を有効にする（VRAM節約）

* Optional: ControlNet（スケッチ/edge map）で入力ドット形状をガイド

## TripoSR 等 3D生成器設定（推奨ワークフロー）

* 入力：単一画像 + optional masks

* 出力：点群（XYZ + RGB）または三角メッシュ（.ply/.obj）

* Postprocess（Open3D）：

  * Statistical outlier removal（点群ノイズ除去）

  * 法線推定 → Poisson surface reconstruction（メッシュ化）

  * リトポ（必要なら decimate） → UV 生成（簡易） → obj + png

* 注意：品質向上は生成器のハイパーパラメータ（ステップ）で調整。時間と品質のトレードオフあり。

## システム構成（Flask 実装の具体）

### エンドポイント（最小）

* `POST /api/paint`

  * リクエスト：`{tile_x, tile_y, png(32x32), user_id}`

  * 動作：差分を保存、job を Redis に enqueue、即時レスポンスで `job_id` を返す

* `GET /api/status/{job_id}`

  * ジョブ状態を返す（queued / processing / light_ready / refined_ready）

* WebSocket `/ws`（簡易）**必須**：クライアントに asset 生成完了を通知（light/refined）

### ワーカー（役割）

* **light_worker**：VLM抽出 → CLIPテンプレ検索 → prompt 作成 → SD で単一画像を生成 → TripoSR（低品質設定）で mesh生成 → Open3Dで簡易処理 → 保存（obj + png）→ notify

* **refine_worker**（バックグラウンド）：より高品質設定で再生成（より高解像度）→差し替え通知

### 重要パラメータ（config）

```

TILE\_PX: 32
EMBED\_TOP\_K: 8
SD\_RESOLUTION: 512
SD\_STEPS\_LIGHT: 20
SD\_STEPS\_HIGH: 50
MAX\_CONCURRENT\_WORKERS: 4
PER\_TILE\_COOLDOWN: 5

```

## キャッシュ & 冪等性

* 生成プロセスは入力（tile image + VLM JSON）をハッシュ化してキャッシュキーを作る

* 同一入力はキャッシュされた glTF を即返却（コスト大幅低減）

## 共有ワールド表示（A-Frame）
A-Frame を使用して、宣言的なHTMLシンタックスで3Dシーンを構築する。

1. objects.json を定義（各オブジェクトに id, x, y, z, rotation, scale, glb_url, quality）

2. クライアントは WebSocketで受け取ったオブジェクトデータを元に、<a-entity>にglTFモデルを動的にロードして配置する。

3. 移動：A-Frameに組み込まれている3Dナビゲーションコンポーネントを利用する。

**注意！** 

あくまで3D描画を簡単にするものなのでVR/AR対応は考えていません。
キーマウとモニターで操作します。

## フォールバック戦略（TripoSR が使えない場合）

1. Point-E を使って点群生成 → Open3D でメッシュ化

2. Shap-E を使って直接低ポリメッシュを生成

3. もしくは辞書ベース（テンプレ glb）にSDで生成したテクスチャを貼る（最速）

## パフォーマンス目安（RTX5070ti / 96GB RAM）

* VLM（1 tile）: 0.5〜2s（モデルに依存）

* SD（1視点，512）: 1〜5s（環境差）

* 3Dgen（TripoSR）: 5–30s（モデルによる）

* Open3D 処理: 1–5s
  → 合計：**お兄ちゃんが許容するなら 10–40 秒**の範囲で、light/refined の二段構えでユーザー体験を維持するのが現実的

## ローカル配置・DL手順（簡潔）

1. Python 環境作成

```

python -m venv venv
source venv/bin/activate
pip install torch torchvision diffusers transformers accelerate open\_clip\_torch open3d pillow fastapi uvicorn redis rq

```

2. Stable Diffusion v1.5（diffusers）を事前キャッシュ

```

from diffusers import StableDiffusionPipeline
pipe = StableDiffusionPipeline.from\_pretrained("runwayml/stable-diffusion-v1-5", torch\_dtype=torch.float16)

```

## 実装注意（AIに渡すべき指示）

* 全てのモデル呼び出しは **try/except** で失敗時にフォールバック経路へ流すこと

* 生成は **small-batch** で行い、FP16 と attention-slicing を使うこと

* 生成中は `status` を逐次更新してクライアントに送る（queued→sd_generating→3d_generating→light_ready→refining→refined_ready）

* 出力 glTF は最終的に **外部 URL**（ローカルサーバの静的配信パス）に置くこと

## ディレクトリ雛形

```

GeoPlace/
├─ backend/
│  ├─ app.py             \# Flask server
│  ├─ worker\_light.py
│  ├─ worker\_refine.py
│  ├─ models/            \# model loaders (sd, vlm, clip)
│  ├─ cache/
│  └─ config.yaml
├─ data/
│  └─ canvas.png
├─ assets/
│  └─ glb/
└─ frontend/
├─ index.html
└─ world.html

E:\GITS\TripoSR-main
```

## 追加: TripoSR と Admin UI

このリポジトリは TripoSR を外部ツールとして呼び出し、生成画像から glTF/GLB を作成するよう設計されています。

- TripoSR を使う場合はローカルに `E:\GITS\TripoSR-main` のようにクローンし、`backend/config.yaml` の `TRIPOSR_DIR` を設定してください。
- TripoSR 実行例（コマンドライン）:

```powershell
cd E:\GITS\TripoSR-main
python run.py C:\path\to\input.png --output-dir output --model-save-format glb --bake-texture
```

- サーバは起動時に Stable Diffusion パイプラインをバックグラウンドでロードしようとします。`/frontend/admin.html` でモデルロード状態 (`/api/admin/models`) を確認できます。
- TripoSR の依存が不足する場合、サーバは自動的にフォールバックの簡易 GLB を作成して進行を続けます。完全な 3D 結果を得るには TripoSR の依存（`torchmcubes` など）をインストールしてください。

## 実行方法 (推奨)

開発中はパッケージモードで起動するのが安定します。ワークスペースのルートから次のコマンドで起動してください。

```powershell
# 仮想環境をアクティベートした後
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

またはスクリプト直接実行をサポートしています:

```powershell
run_triposr.ps1
```

両方の起動方法で相対インポートの問題が出ないよう `backend/main.py` にフォールバックの処理を入れてあります。
