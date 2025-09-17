"""VLM (Vision-Language Model) attribute extraction using LM Studio.
LM Studio の Gemma3-Vision を使用して画像から属性を抽出。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
import requests
import base64
import json
import re

@dataclass
class VLMAttributes:
    category: str
    colors: List[str]
    size: str
    orientation: str
    details: List[str]


def load_vlm_model():
    """LM Studio の接続情報を返す"""
    from ..config import settings
    return {
        'name': 'lm-studio-gemma3-vision',
        'base_url': getattr(settings, 'lm_studio_base_url', 'http://localhost:1234/v1').replace('/chat/completions', ''),
        'model': getattr(settings, 'lm_studio_model', 'gemma-3-4b-it')
    }


def extract_attributes(model, image_bytes: bytes) -> VLMAttributes:
    """LM Studio を使用して画像から属性を抽出"""
    try:
        # 画像をbase64エンコード
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # LM Studio API へのリクエスト
        headers = {
            'Content-Type': 'application/json'
        }
        
        # プロンプトを日本語で構成
        prompt = """この画像に写っているオブジェクトを分析して、以下の形式で回答してください：

カテゴリ: [house/tree/river/person/car/building/nature/other のいずれか]
色: [主要な色を2-3個、英語で]
サイズ: [small/medium/large のいずれか]
向き: [front/side/back/diagonal のいずれか]
特徴: [窓、屋根、葉、枝などの特徴を2-3個、日本語で]

例:
カテゴリ: house
色: red, white
サイズ: medium
向き: front
特徴: 窓, 屋根, ドア"""

        payload = {
            "model": model.get('model', 'gemma-2-2b-it'),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": 200,
            "temperature": 0.3
        }
        
        response = requests.post(
            f"{model['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            return _parse_vlm_response(content)
        else:
            print(f"LM Studio API エラー: {response.status_code} - {response.text}")
            return _fallback_attributes()
            
    except Exception as e:
        print(f"VLM 処理エラー: {e}")
        return _fallback_attributes()


def _parse_vlm_response(content: str) -> VLMAttributes:
    """LM Studio からの応答をパースして VLMAttributes に変換"""
    try:
        # 正規表現で各項目を抽出
        category_match = re.search(r'カテゴリ[：:]\s*(\w+)', content)
        colors_match = re.search(r'色[：:]\s*([^\n]+)', content)
        size_match = re.search(r'サイズ[：:]\s*(\w+)', content)
        orientation_match = re.search(r'向き[：:]\s*(\w+)', content)
        details_match = re.search(r'特徴[：:]\s*([^\n]+)', content)
        
        # カテゴリ
        category = category_match.group(1) if category_match else 'object'
        
        # 色（カンマ区切りで分割）
        colors = []
        if colors_match:
            color_text = colors_match.group(1)
            colors = [c.strip() for c in re.split(r'[,、]', color_text) if c.strip()]
        if not colors:
            colors = ['gray', 'white']
            
        # サイズ
        size = size_match.group(1) if size_match else 'medium'
        
        # 向き
        orientation = orientation_match.group(1) if orientation_match else 'front'
        
        # 特徴（カンマ区切りで分割）
        details = []
        if details_match:
            details_text = details_match.group(1)
            details = [d.strip() for d in re.split(r'[,、]', details_text) if d.strip()]
        if not details:
            details = ['オブジェクト']
            
        return VLMAttributes(
            category=category,
            colors=colors,
            size=size,
            orientation=orientation,
            details=details
        )
        
    except Exception as e:
        print(f"応答パースエラー: {e}")
        return _fallback_attributes()


def _fallback_attributes() -> VLMAttributes:
    """エラー時のフォールバック属性"""
    return VLMAttributes(
        category='object',
        colors=['gray', 'white'],
        size='medium',
        orientation='front',
        details=['シンプルなオブジェクト']
    )


def to_prompt(attrs: VLMAttributes) -> str:
    """属性から Stable Diffusion 用のプロンプトを生成"""
    color_str = ', '.join(attrs.colors)
    details_str = ', '.join(attrs.details)
    
    return (
        f"voxel-style {attrs.category}, {attrs.size} size, "
        f"primary colors: {color_str}, "
        f"features: {details_str}, "
        f"low-poly, game-friendly, 3D render, {attrs.orientation} view, "
        f"clean background, high quality, detailed"
    )
