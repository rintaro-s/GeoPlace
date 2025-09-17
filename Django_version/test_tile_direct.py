#!/usr/bin/env python
"""
Direct tile access test - bypassing Django to verify tile files work
"""
import os
from PIL import Image
import io

def test_tile_access():
    """Test direct access to tile files"""
    
    # Test E: drive tiles
    e_drive_path = r'E:\files\GeoPLace-tmp\images\tile_0_0.png'
    
    print(f"Testing tile access:")
    print(f"Path: {e_drive_path}")
    print(f"Exists: {os.path.exists(e_drive_path)}")
    
    if os.path.exists(e_drive_path):
        try:
            # Read file
            with open(e_drive_path, 'rb') as f:
                data = f.read()
            print(f"File size: {len(data)} bytes")
            
            # Try to open as image
            img = Image.open(io.BytesIO(data))
            print(f"Image size: {img.size}")
            print(f"Image mode: {img.mode}")
            
            # Save a test copy
            test_path = "test_tile_copy.png"
            img.save(test_path)
            print(f"Saved test copy to: {test_path}")
            
            return True
            
        except Exception as e:
            print(f"Error processing tile: {e}")
            return False
    else:
        print("Tile file not found!")
        return False

if __name__ == "__main__":
    test_tile_access()
