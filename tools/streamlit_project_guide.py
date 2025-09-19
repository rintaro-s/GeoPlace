import os
import streamlit as st
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]

@st.cache_data
def build_tree(root: Path):
    """Return a nested dict representing files and directories under root."""
    tree = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        parts = rel.parts
        node = tree
        for p in parts:
            node = node.setdefault(p, {})
        for d in sorted(dirnames):
            node.setdefault(d, {})
        for f in sorted(filenames):
            node.setdefault(f, None)
    return tree


def categorize_top_level(root: Path):
    """Provide human-friendly top-level "genres" based on common folders/files."""
    items = [p.name for p in root.iterdir()]
    genres = []
    if 'backend' in items or 'models' in items:
        genres.append('Backend / Models')
    if 'frontend' in items or 'assets' in items:
        genres.append('Frontend / Assets')
    if 'data' in items or 'cache' in items:
        genres.append('Data / Cache')
    if 'TripoSR-main' in items or 'tsr' in items:
        genres.append('3D / TripoSR')
    if 'readme.md' in [n.lower() for n in items] or 'readme.md' in items:
        genres.append('Docs / How to run')
    if not genres:
        genres = ['Repository']
    # append any other top-level folders as fallback
    for p in sorted(items):
        if p not in ('backend','frontend','assets','data','cache','TripoSR-main','tsr','readme.md'):
            genres.append(p)
    return genres


def preview_file(path: Path, max_lines=200):
    try:
        txt = path.read_text(encoding='utf-8', errors='ignore')
        lines = txt.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + "\n\n... (truncated)"
        return txt
    except Exception as e:
        return f"Could not read file: {e}"


def guess_answers_for_path(path: Path):
    """Return suggested questions and answers for a folder or file path."""
    qas = []
    name = path.name.lower()
    if path.is_dir():
        # common folder answers
        if 'backend' in name:
            qas.append(("How do I run the server?",
                        "Start the FastAPI server: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`. See `readme.md` for details."))
            qas.append(("Where are API endpoints?",
                        "Look in `backend/main.py` and `backend/models/` for search, pipeline, and job logic."))
        if 'frontend' in name:
            qas.append(("Which files are the UIs?",
                        "`frontend/paint.html`, `frontend/world_new.html`, and `frontend/world.html` are the main pages. They call `/api` endpoints on the backend."))
        if 'assets' in name:
            qas.append(("Where are generated 3D assets stored?",
                        "`assets/glb/` and `assets/glb/objects.json` contain glb files and placement metadata used by A-Frame.") )
        if 'data' in name:
            qas.append(("Where is the large canvas image?",
                        "`data/canvas.png` is the shared canvas used by the frontends."))
        if 'cache' in name or 'vlm_logs' in name:
            qas.append(("Where are VLM logs and cache?",
                        "`backend/cache/vlm_logs` stores VLM/LMStudio logs and debug dumps."))
    else:
        # file heuristics
        if name.endswith('.md'):
            qas.append(("What's the run command?",
                        preview_file(path).splitlines()[0:10] and '\n'.join(preview_file(path).splitlines()[:20]) or 'See file.'))
        if name == 'main.py' and 'backend' in str(path.parent):
            qas.append(("How is FastAPI configured?",
                        "Open `backend/main.py` to see routes, APIRouter, and middleware. Uvicorn command is in the README."))
        if name.endswith('.html') and 'frontend' in str(path.parent):
            qas.append(("What does this frontend page do?",
                        f"Preview of `{path.name}`:\n\n" + (preview_file(path, max_lines=30)[:800] + '\n...'))) 
        if name.endswith('.py') and 'models' in str(path.parent):
            qas.append(("Does this script implement search or model logic?",
                        preview_file(path, max_lines=80)[:1000]))
    # generic fallback
    if not qas:
        qas.append(("What is this?", f"Path: {path}\nType: {'directory' if path.is_dir() else 'file'}"))
    return qas


# -- Streamlit UI --
st.set_page_config(page_title='GeoPlace — Project Guide', layout='wide')
st.title('GeoPlace — Project Guide')
st.markdown('Tap through the tree (left) to find helpful questions and quick answers about the project structure.')

with st.sidebar:
    st.header('Browse')
    genres = categorize_top_level(ROOT)
    genre = st.radio('Genre', genres)

# build tree lazily
tree = build_tree(ROOT)

# Compute the starting node for the selected genre

def find_node_for_genre(tree, genre):
    # Map common genres to actual folder names
    mapping = {
        'Backend / Models': 'backend',
        'Frontend / Assets': 'frontend',
        'Data / Cache': 'data',
        '3D / TripoSR': 'TripoSR-main',
        'Docs / How to run': 'readme.md'
    }
    target = mapping.get(genre)
    if not target:
        return tree
    # if target is file at root
    if target in tree and tree[target] is None:
        return {target: None}
    # else find subtree
    node = tree.get(target, {})
    return {target: node}

start_node = find_node_for_genre(tree, genre)

# Show hierarchical navigation pane
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader('Tree')
    # breadcrumb state
    if 'path_parts' not in st.session_state:
        st.session_state['path_parts'] = []

    def render_level(node, prefix_path):
        # node is dict mapping name->(dict or None)
        names = sorted(node.keys())
        choice = st.selectbox('Select', ['..'] + names, key='sel_' + '_'.join(prefix_path) if prefix_path else 'sel_root')
        if choice and choice != '..':
            new_path = prefix_path + [choice]
            st.session_state['path_parts'] = new_path
        else:
            if prefix_path:
                st.session_state['path_parts'] = prefix_path[:-1]
            else:
                st.session_state['path_parts'] = []

    # render one-level per interaction (keeps UI simple on Streamlit)
    current_node = start_node
    prefix = []
    depth = 0
    while True:
        # show the current level compactly
        render_level(current_node, prefix)
        prefix = st.session_state.get('path_parts', [])
        # drill down according to prefix
        node = start_node
        for p in prefix:
            if node and p in node and isinstance(node[p], dict):
                node = node[p]
            else:
                node = None
                break
        current_node = node or {}
        depth += 1
        if depth >= 6:
            break
        # provide a small stop control
        if not st.button('もっと深く', key=f'deep_{depth}'):
            break

with col2:
    st.subheader('Details')
    path_parts = st.session_state.get('path_parts', [])
    if not path_parts:
        st.write('Select a genre and then tap through folders to reach a target file or directory.')
    else:
        target_path = ROOT.joinpath(*path_parts)
        st.markdown('**Selected:** ' + str(target_path.relative_to(ROOT)))
        if target_path.exists():
            if target_path.is_file():
                st.code(preview_file(target_path, max_lines=200), language='')
            else:
                st.write('Directory contents:')
                items = list(sorted(target_path.iterdir(), key=lambda p: (p.is_file(), p.name)))
                for it in items:
                    st.write(('- [F] ' if it.is_file() else '- [D] ') + it.name)

        st.markdown('---')
        st.subheader('Suggested Questions')
        qas = guess_answers_for_path(target_path if path_parts else ROOT)
        for q, a in qas:
            with st.expander(q):
                st.write(a)

        st.markdown('---')
        st.write('Quick actions:')
        if target_path.exists():
            if target_path.is_file() and target_path.suffix in ('.py', '.md'):
                if st.button('Open file in editor (prints path)'):
                    st.write(str(target_path))
            if target_path.is_dir():
                if st.button('List files (flat)'):
                    files = [str(p.relative_to(ROOT)) for p in target_path.rglob('*') if p.is_file()]
                    st.write('\n'.join(files[:500]))

st.markdown('---')
st.write('Run the app:')
st.code('pip install streamlit\nstreamlit run tools/streamlit_project_guide.py', language='bash')
