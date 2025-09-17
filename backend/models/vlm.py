"""VLM (Vision-Language Model) attribute extraction placeholder.
実際の Gemma3-Vision などを統合する際のインターフェースを定義。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class VLMAttributes:
    category: str
    colors: List[str]
    size: str
    orientation: str
    details: List[str]


def load_vlm_model():
    # 実際には transformers 等でモデルロード
    return {
        'name': 'dummy-vlm'
    }


def extract_attributes(model, image_bytes: bytes) -> VLMAttributes:
    # ここではダミー推論
    return VLMAttributes(
        category='object',
        colors=['red','white'],
        size='medium',
        orientation='front',
        details=['placeholder']
    )


def to_prompt(attrs: VLMAttributes) -> str:
    return (
        f"voxel-style {attrs.category}, {attrs.size}, primary colors: {', '.join(attrs.colors)}, "
        f"details: {', '.join(attrs.details)}, low-poly, game-friendly, 3D render, front view"
    )
