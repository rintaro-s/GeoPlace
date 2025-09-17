"""
Complete 3D generation workflow following readme specifications:
1. Extract tile image
2. VLM analysis (LM Studio)
3. Generate prompt template
4. Stable Diffusion image generation
5. TripoSR 2D→3D conversion
6. Open3D cleanup and GLB export
7. Register in objects.json
"""
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import tempfile
import json
import time
from ..models import vlm, sd, three_d
from ..config import settings

def run_complete_3d_workflow(tile_image_bytes: bytes, tile_x: int, tile_y: int) -> Tuple[Path, Dict[str, Any]]:
    """
    Complete 3D generation workflow for a single tile
    Returns: (glb_path, metadata)
    """
    workflow_start = time.time()
    
    # Create unique identifier for this workflow
    workflow_id = f"tile_{tile_x}_{tile_y}_{int(time.time())}"
    
    try:
        # Step 1: VLM Analysis using LM Studio
        print(f"[{workflow_id}] Step 1: VLM analysis...")
        vlm_model = vlm.load_vlm_model()
        attributes = vlm.extract_attributes(vlm_model, tile_image_bytes)
        
        # Step 2: Generate prompt template
        print(f"[{workflow_id}] Step 2: Generating prompt...")
        prompt = vlm.to_prompt(attributes)
        
        # Step 3: Stable Diffusion image generation
        print(f"[{workflow_id}] Step 3: SD image generation...")
        sd_model = sd.load_sd_model()
        generated_image_bytes = sd.generate_image(sd_model, prompt)
        
        # Step 4: TripoSR 2D→3D conversion
        print(f"[{workflow_id}] Step 4: TripoSR 3D generation...")
        glb_output_path = settings.glb_dir / f"{workflow_id}.glb"
        final_glb_path = three_d.generate_glb_from_image(
            generated_image_bytes, 
            glb_output_path, 
            quality='light'
        )
        
        # Step 5: Create metadata
        workflow_end = time.time()
        metadata = {
            'workflow_id': workflow_id,
            'tile_coords': [tile_x, tile_y],
            'vlm_attributes': {
                'category': attributes.category,
                'colors': attributes.colors,
                'size': attributes.size,
                'orientation': attributes.orientation,
                'details': attributes.details
            },
            'sd_prompt': prompt,
            'processing_time': workflow_end - workflow_start,
            'timestamp': time.time(),
            'quality': 'light',
            'pipeline_version': '1.0'
        }
        
        print(f"[{workflow_id}] Workflow completed in {workflow_end - workflow_start:.2f}s")
        return final_glb_path, metadata
        
    except Exception as e:
        print(f"[{workflow_id}] Workflow failed: {e}")
        # Create fallback GLB
        fallback_path = settings.glb_dir / f"{workflow_id}_fallback.glb"
        _create_fallback_glb(fallback_path, tile_image_bytes)
        
        metadata = {
            'workflow_id': workflow_id,
            'tile_coords': [tile_x, tile_y],
            'error': str(e),
            'fallback': True,
            'timestamp': time.time(),
            'quality': 'fallback'
        }
        
        return fallback_path, metadata


def _create_fallback_glb(output_path: Path, original_image_bytes: bytes):
    """Create a simple fallback GLB when the pipeline fails"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a simple placeholder GLB with embedded image data
    with open(output_path, 'wb') as f:
        f.write(b'GLB_FALLBACK_V1\n')
        f.write(b'ORIGINAL_IMAGE_DATA:\n')
        f.write(original_image_bytes)


def register_3d_object(glb_path: Path, metadata: Dict[str, Any], tile_x: int, tile_y: int):
    """Register the generated 3D object in objects.json"""
    try:
        # Load existing objects
        objects_file = settings.glb_dir / 'objects.json'
        if objects_file.exists():
            objects = json.loads(objects_file.read_text(encoding='utf-8'))
        else:
            objects = []
        
        # Create object entry
        object_id = f"tile_{tile_x}_{tile_y}"
        
        # Calculate 3D world position with proper scaling
        # タイル座標を3D世界座標に変換（スケール調整）
        tile_size_meters = 1.0  # 1タイル = 1メートル
        world_x = tile_x * tile_size_meters
        world_z = tile_y * tile_size_meters
        
        # VLM属性に基づくサイズ調整
        size_multiplier = {
            'small': 0.5,
            'medium': 1.0, 
            'large': 1.5
        }.get(metadata.get('vlm_attributes', {}).get('size', 'medium'), 1.0)
        
        object_entry = {
            'id': object_id,
            'x': world_x,
            'y': 0,  # Ground level
            'z': world_z,
            'rotation': [0, 0, 0],
            'scale': size_multiplier,  # VLM属性に基づくサイズ調整
            'glb_url': f'/assets/glb/{glb_path.name}',
            'metadata': metadata,
            'created_at': time.time(),
            'tile_coords': [tile_x, tile_y],  # 元のタイル座標を保存
            'size_category': metadata.get('vlm_attributes', {}).get('size', 'medium')
        }
        
        # Remove existing entry with same ID
        objects = [obj for obj in objects if obj.get('id') != object_id]
        
        # Add new entry
        objects.append(object_entry)
        
        # Save updated objects
        objects_file.parent.mkdir(parents=True, exist_ok=True)
        with open(objects_file, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False, indent=2)
            
        print(f"Registered 3D object: {object_id} at world position ({world_x}, 0, {world_z})")
        
    except Exception as e:
        print(f"Failed to register 3D object: {e}")


def batch_process_tiles(tile_coords_list: list) -> Dict[str, Any]:
    """Process multiple tiles in batch"""
    results = {
        'processed': [],
        'failed': [],
        'total_time': 0
    }
    
    batch_start = time.time()
    
    for tile_x, tile_y in tile_coords_list:
        try:
            # Load tile image
            from ..main import _cut_tile_image
            tile_bytes = _cut_tile_image(tile_x, tile_y, settings.tile_px)
            
            # Run workflow
            glb_path, metadata = run_complete_3d_workflow(tile_bytes, tile_x, tile_y)
            
            # Register object
            register_3d_object(glb_path, metadata, tile_x, tile_y)
            
            results['processed'].append({
                'tile': [tile_x, tile_y],
                'glb_path': str(glb_path),
                'metadata': metadata
            })
            
        except Exception as e:
            results['failed'].append({
                'tile': [tile_x, tile_y],
                'error': str(e)
            })
    
    results['total_time'] = time.time() - batch_start
    return results
