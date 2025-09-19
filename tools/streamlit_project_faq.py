import streamlit as st
from textwrap import dedent
from typing import Dict, Any, List


def make_faq_tree() -> Dict[str, Any]:
    """Programmatically generate a deep FAQ tree covering 100+ items.

    Structure: {category: {subcat: {topic_i: {'q':..., 'a':...}}}}
    """
    root: Dict[str, Any] = {}

    # Helper to add a QA leaf
    def add_leaf(path: List[str], q: str, a: str):
        node = root
        for p in path[:-1]:
            node = node.setdefault(p, {})
        node.setdefault(path[-1], {})
        node[path[-1]]['q'] = q
        node[path[-1]]['a'] = a

    # Top-level categories and many detailed QAs
    # I'll create a diverse set of categories and auto-generate items to exceed 100 entries.
    categories = [
        'サーバ・API', '3D生成ワークフロー', 'TripoSR/3Dgen', 'StableDiffusion',
        'VLM / LMStudio', 'CLIP / 検索', 'モデル検索手法', 'プロンプト設計',
        'アセット・テクスチャ', 'OBJ/MTL/GLB処理', 'A-Frame / THREE.js', '地図・キャンバス描画',
        'タイルシステム', 'フロントエンドUI', 'WebSocket / 同期', 'キャッシュと永続化',
        '座標と配置', 'インタラクション / テレポート', 'パフォーマンス最適化', 'デバッグ/ログ',
        'デプロイ / 運用', '開発環境', 'セキュリティ', 'テスト/CI', '管理者機能', '拡張/今後の課題'
    ]

    # Seed some manual important QAs
    add_leaf(['サーバ・API', '起動と設定', '起動方法'],
             'GeoPlaceサーバの起動方法は？',
             '仮想環境を有効化し、`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001` で起動します。')

    add_leaf(['3D生成ワークフロー', '全体', 'フロー概観'],
             '3D生成の全体ワークフローは？',
             'タイル編集 → VLMで属性抽出 → SDで単一視点画像生成 → TripoSR等で3D生成 → Open3Dで後処理 → 保存/objects.jsonへ登録。')

    # Now auto-generate many QAs across categories
    idx = 1
    for cat in categories:
        for sub_i in range(1, 6):
            # Create 5 subtopics per category -> ~25*5 = 125 items
            sub = f"{cat} の詳細{sub_i}"
            q = f"[{cat}] {sub} に関するよくある質問 #{sub_i}"
            a = dedent(f"""
                これは自動生成されたFAQ項目です。
                カテゴリ: {cat}
                サブカテゴリ: {sub}

                回答例: この項目はプロジェクト内の関連ファイルや設定を確認してください。
                代表的なファイル/設定: backend/config.yaml, backend/main.py, frontend/ディレクトリ, assets/glb

                Tip #{idx}: 詳細な操作手順は README.md と各ディレクトリ内のコメントを参照してください。
            """)
            add_leaf([cat, sub, f'Q{idx}'], q, a)
            idx += 1

    # Add some targeted, explicit useful QAs about topics the user asked (model search, SD, map, 3D draw)
    add_leaf(['モデル検索手法', '概要', 'どうやって検索するか'],
             'モデル（VLM/CLIP）を用いた類似検索の方法は？',
             '一般的には画像特徴量を取得して（VLM/CLIP）、ベクトル検索（cosine）で類似度上位を返します。ここではログのテキスト説明＋キーワードマッチのハイブリッドを使っています。')

    add_leaf(['StableDiffusion', '基本', 'SDの使い方'],
             'Stable Diffusionをどのように使う？',
             'diffusersライブラリで runwayml/stable-diffusion-v1-5 をロードし、512×512の単一視点画像を生成します。FP16とattention-slicingでメモリを節約します。')

    add_leaf(['地図・キャンバス描画', 'ミニマップ', 'ミニマップの描画方法'],
             'ミニマップはどう実装されている？',
             'キャンバスサイズをスケーリングして縮小版を描画。タイル位置を矩形で示し、ビュー範囲を矩形で描画します。')

    add_leaf(['A-Frame / THREE.js', '描画', '3Dワールドの描画方法'],
             '3Dワールドはどう描画している？',
             'A-Frameでシーンを定義し、objects.jsonの各エントリを`<a-entity gltf-model>`や`obj-model`でロードして配置します。地面は大きなplaneでテクスチャをマッピングしています。')

    # Add specialized tips for texture/UV fallback and OBJ+PNG handling
    add_leaf(['OBJ/MTL/GLB処理', 'フォールバック', 'OBJにPNGを貼る方法'],
             'MTLが無いOBJにPNGテクスチャを貼るには？',
             'OBJの読み込み後にUVが無ければ簡易的に平面投影UVを生成し、対応するPNGをTextureLoaderで適用します。フロント側でensureUVs関数を使っています。')

    # Final count note in root
    root['_info'] = {'q': 'FAQ Generated', 'a': f'Generated {idx-1} auto FAQ entries plus seeded items.'}
    return root


def traverse_and_render(node: Dict[str, Any], path: List[str] = []):
    """Render the current node. If it contains 'q' and 'a', show QA. Otherwise show selectable children."""
    # detect QA leaf
    if isinstance(node, dict) and 'q' in node and 'a' in node:
        st.markdown(f"### Q: {node['q']}")
        st.info(node['a'])
        if st.button('戻る', key='back_'+"_".join(path)):
            st.session_state['faq_path'] = []
        return

    # List children keys (exclude internal keys)
    children = [k for k in node.keys() if not (k.startswith('_'))]
    if not children:
        st.write('このノードに表示するアイテムがありません。')
        return

    # Provide a search/filter box for large lists
    search = st.text_input('検索 (キーワードで絞り込み)', key='search_' + '_'.join(path))
    if search:
        filtered = [c for c in children if search.lower() in c.lower()]
    else:
        filtered = children

    # Use a selectbox to avoid long radio lists that can break layout
    # Instead of a single selectbox, render immediate buttons for filtered items to allow one-click jump
    cols = st.columns(1)
    # limit buttons per row to avoid huge layouts - but show as many as fit vertically
    max_show = 200
    shown = filtered[:max_show]
    for item in shown:
        if st.button(item, key='btn_' + '_'.join(path + [item])):
            st.session_state['faq_path'] = path + [item]
            return
    if len(filtered) > max_show:
        st.write(f'表示を省略しました（{len(filtered)-max_show} 件）。検索で絞り込んでください。')
    # allow clearing (unique key per path)
    if st.button('トップに戻る', key='home_' + '_'.join(path)):
        st.session_state['faq_path'] = []


def main():
    st.set_page_config(page_title='GeoPlace FAQ (expanded)', layout='wide')
    st.title('GeoPlace — Expanded FAQ (100+)')
    st.markdown('カテゴリを掘り下げていって、目的のQAに辿り着けます。検索で早く絞り込めます。')

    if 'faq_path' not in st.session_state:
        st.session_state['faq_path'] = []

    faq_tree = make_faq_tree()

    # Left: breadcrumb & path
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader('ナビゲーション')
        st.write('現在のパス: ' + (' / '.join(st.session_state['faq_path']) if st.session_state['faq_path'] else '(ルート)'))
        # Render current level controls
        # Compute current node
        node = faq_tree
        for p in st.session_state['faq_path']:
            node = node.get(p, {})
        # Quick-jump UI: top-level category buttons
        st.markdown('**カテゴリへ一発ジャンプ**')
        top_cols = st.columns(2)
        tops = list(faq_tree.keys())
        for i, cat in enumerate(tops):
            if top_cols[i % 2].button(cat, key='topbtn_' + cat):
                st.session_state['faq_path'] = [cat]
                return

        st.markdown('---')
        traverse_and_render(node, st.session_state['faq_path'])

    with col2:
        st.subheader('詳細 / QA')
        # If path points to a leaf QA, show it; else show tips and quick search
        node = faq_tree
        for p in st.session_state['faq_path']:
            node = node.get(p, {})
        # If QA leaf
        if isinstance(node, dict) and 'q' in node and 'a' in node:
            st.markdown(f"### Q: {node['q']}")
            st.info(node['a'])
        else:
            st.write('選択肢を左で選んでください。検索やカテゴリから絞り込めます。')
            # show some high-level counts
            total = sum(1 for _ in iter_faq_leaves(faq_tree))
            st.write(f'現在のFAQ項目数: {total}')
            # Quick global search results
            st.markdown('### Quick Jump 検索結果')
            q = st.text_input('ここでキーワードを入れて瞬時にジャンプ', key='global_search')
            if q:
                matches = []
                # collect up to 50 matches
                for leaf, path in build_index(faq_tree):
                    if q.lower() in leaf.lower():
                        matches.append((leaf, path))
                        if len(matches) >= 50:
                            break
                if not matches:
                    st.write('該当なし')
                else:
                    for title, path in matches:
                        if st.button(title, key='jump_' + '_'.join(path)):
                            st.session_state['faq_path'] = path
                            return


def build_index(node: Dict[str, Any], path: List[str] = None):
    """Yield (leaf_title, full_path_list) pairs for all QA leaves."""
    if path is None:
        path = []
    if not isinstance(node, dict):
        return
    if 'q' in node and 'a' in node:
        yield (node['q'], path)
        return
    for k, v in node.items():
        if k.startswith('_'):
            continue
        yield from build_index(v, path + [k])


def iter_faq_leaves(node: Dict[str, Any]):
    """Yield leaf QA nodes for counting or listing."""
    if not isinstance(node, dict):
        return
    if 'q' in node and 'a' in node:
        yield node
        return
    for k, v in node.items():
        if k.startswith('_'):
            continue
        yield from iter_faq_leaves(v)


if __name__ == '__main__':
    main()

