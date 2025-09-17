# GeoPlace - Anvil Version

完全にAnvilで書き直したGeoPlaceプロジェクトです。画像取得の問題を解決し、より安定したアーキテクチャを提供します。

## 特徴

### ✅ 修正された問題
- **画像取得の修正**: `E:\files\GeoPLace-tmp\images` からの画像取得を正しく実装
- **安定したUI**: AnvilのネイティブUIコンポーネントを使用
- **簡潔なアーキテクチャ**: FastAPI + HTMLの複雑さを排除

### 🎨 フロントエンド機能
- **ペイント画面** (`PaintForm`):
  - 32x32タイルベースの描画システム
  - リアルタイム座標表示
  - ズーム・パン機能
  - ブラシサイズ・色選択
  - タイル保存・3D生成

- **3D世界画面** (`WorldForm`):
  - 3Dオブジェクト一覧表示
  - テレポート機能（座標指定・プリセット）
  - カメラ位置表示
  - オブジェクト管理

### 🔧 バックエンド機能
- **タイル管理** (`TileManager`):
  - `E:\files\GeoPLace-tmp\images` への直接アクセス
  - PIL Imageを使用した画像処理
  - 自動透明タイル生成

- **AI パイプライン** (`AIWorkflow`):
  - LM Studio VLM統合 (Gemma-3-4b-it)
  - 属性抽出・プロンプト生成
  - Stable Diffusion統合準備
  - TripoSR統合準備

- **3Dオブジェクト管理** (`ObjectManager`):
  - objects.json管理
  - 2D→3D座標変換
  - サイズ調整機能

## セットアップ

### 1. 依存関係のインストール
```bash
cd Anvil_version
pip install -r requirements.txt
```

### 2. ディレクトリ作成
```bash
mkdir -p "E:/files/GeoPLace-tmp/images"
mkdir -p "./assets/glb"
```

### 3. LM Studio起動
- LM Studioを起動
- Gemma-3-4b-itモデルをロード
- localhost:1234でサーバー開始

### 4. Anvilサーバー起動
```bash
python main.py
```

## アーキテクチャ

```
Anvil_version/
├── main.py                 # メインサーバー（Anvil Server Functions）
├── client_code/
│   ├── PaintForm/         # ペイント画面
│   │   ├── __init__.py
│   │   └── form_template.yaml
│   └── WorldForm/         # 3D世界画面
│       ├── __init__.py
│       └── form_template.yaml
├── anvil.yaml             # Anvilアプリ設定
├── requirements.txt       # Python依存関係
└── README.md             # このファイル
```

## 主要クラス

### TileManager
- `get_tile_path(tile_x, tile_y)`: タイルファイルパス取得
- `load_tile(tile_x, tile_y)`: タイル画像読み込み
- `save_tile(tile_x, tile_y, image_data)`: タイル保存
- `get_tile_as_media(tile_x, tile_y)`: Anvil Media形式で取得

### AIWorkflow
- `analyze_with_vlm(image_bytes)`: VLM画像解析
- `generate_prompt(attributes)`: SD用プロンプト生成
- `run_complete_workflow(tile_x, tile_y)`: 完全AI処理

### ObjectManager
- `load_objects()`: objects.json読み込み
- `save_objects(objects)`: objects.json保存
- `register_object(object_id, metadata, glb_path)`: 3Dオブジェクト登録

## Anvil Server Functions

### 画像・タイル関連
- `get_tile(tile_x, tile_y)`: タイル画像取得
- `save_tile_data(tile_x, tile_y, pixel_data)`: タイルデータ保存
- `get_modified_tiles()`: 変更タイル一覧

### 3D生成関連
- `start_3d_generation(tile_coords)`: 3D生成開始
- `get_job_status(job_id)`: ジョブステータス取得
- `get_3d_objects()`: 3Dオブジェクト一覧

### 設定関連
- `get_canvas_info()`: キャンバス情報取得

## 使用方法

1. **ペイント**:
   - ブラシで描画
   - 色・サイズ調整
   - ズーム・パン操作
   - 保存ボタンでタイル保存

2. **3D生成**:
   - 「3D生成」ボタンクリック
   - 進捗表示でモニタリング
   - 完了後に3D世界で確認

3. **3D世界表示**:
   - 「3D世界」ボタンで画面切り替え
   - テレポート機能で移動
   - オブジェクト一覧で確認

## 既存システムとの違い

### 修正された問題
- ❌ FastAPI + HTML: 画像取得エラー
- ✅ Anvil: 直接ファイルアクセス成功

### アーキテクチャ改善
- ❌ 複雑なWebSocket通信
- ✅ シンプルなServer Functions

### UI改善
- ❌ HTML/CSS/JSの複雑な実装
- ✅ Anvilネイティブコンポーネント

## 今後の拡張

1. **AI統合完成**:
   - 既存のSD・TripoSRコードを統合
   - `AIWorkflow`クラスの完全実装

2. **3D表示強化**:
   - A-Frameの完全統合
   - リアルタイム3D表示

3. **協調編集**:
   - 複数ユーザー同時編集
   - リアルタイム同期

このAnvil版は画像取得問題を解決し、より安定した基盤を提供します。
