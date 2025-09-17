import os
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from tqdm import tqdm
import torch.nn.functional as F
Image.MAX_IMAGE_PIXELS = None 

def generate_tiles_gpu(canvas_path, output_dir, tile_size=32, batch_size=32):
    """
    Generate tiles from a large canvas image using GPU acceleration.
    Skips already processed tiles.
    """
    # Check if CUDA is available
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load the canvas image
    print(f"Loading canvas image: {canvas_path}")
    canvas = Image.open(canvas_path).convert('RGBA')
    canvas_array = np.array(canvas)
    
    # Convert to PyTorch tensor and move to GPU
    canvas_tensor = torch.from_numpy(canvas_array).permute(2, 0, 1).float() / 255.0
    canvas_tensor = canvas_tensor.unsqueeze(0).to(device)
    
    # Calculate number of tiles
    _, _, height, width = canvas_tensor.shape
    num_tiles_x = (width + tile_size - 1) // tile_size
    num_tiles_y = (height + tile_size - 1) // tile_size
    
    print(f"Canvas size: {width}x{height}")
    print(f"Generating {num_tiles_x}x{num_tiles_y} tiles of size {tile_size}x{tile_size}")
    
    # Process tiles in batches for better performance
    for y in tqdm(range(0, num_tiles_y, batch_size), desc="Processing tile rows"):
        for x in range(0, num_tiles_x, batch_size):
            # Check which tiles in this batch need processing
            tiles_to_process = []
            for dy in range(min(batch_size, num_tiles_y - y)):
                for dx in range(min(batch_size, num_tiles_x - x)):
                    tile_x, tile_y = x + dx, y + dy
                    output_path = output_dir / f'tile_{tile_x}_{tile_y}.png'
                    if not output_path.exists():
                        tiles_to_process.append((tile_x, tile_y))
            
            if not tiles_to_process:
                continue
                
            # Process the batch of tiles
            patches = []
            coords = []
            for tile_x, tile_y in tiles_to_process:
                x_px, y_px = tile_x * tile_size, tile_y * tile_size
                x_start = x_px / (width - 1) * 2 - 1
                y_start = y_px / (height - 1) * 2 - 1
                x_end = (x_px + tile_size - 1) / (width - 1) * 2 - 1
                y_end = (y_px + tile_size - 1) / (height - 1) * 2 - 1
                
                # Create sampling grid
                grid = torch.stack(torch.meshgrid(
                    torch.linspace(x_start, x_end, tile_size, device=device),
                    torch.linspace(y_start, y_end, tile_size, device=device),
                    indexing='ij'
                ), dim=-1).unsqueeze(0)
                
                # Sample the tile
                tile = F.grid_sample(
                    canvas_tensor,
                    grid,
                    mode='bilinear',
                    padding_mode='border',
                    align_corners=True
                )
                patches.append(tile.squeeze(0))
                coords.append((tile_x, tile_y))
            
            # Save the processed tiles
            for i, (tile_x, tile_y) in enumerate(coords):
                output_path = output_dir / f'tile_{tile_x}_{tile_y}.png'
                tile_np = (patches[i].permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                tile_img = Image.fromarray(tile_np)
                tile_img.save(output_path, 'PNG')

if __name__ == '__main__':
    # Configuration
    CANVAS_PATH = 'data/canvas.png'  # Update this path
    OUTPUT_DIR = 'data/tiles'         # Update this path
    TILE_SIZE = 32                   # Should match your TILE_SIZE setting
    
    generate_tiles_gpu(
        canvas_path='data/canvas.png',  # Path to your canvas image
        output_dir=r'E:\files\GeoPLace-tmp\images',    # Directory where tiles will be saved
        tile_size=32,                   # Tile size (32x32 pixels)
        batch_size=32                   # Number of tiles to process in parallel
    )