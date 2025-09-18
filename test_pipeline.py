#!/usr/bin/env python3
"""End-to-end test for the complete pipeline: VLM -> SD -> TripoSR -> 3D display
Tests the actual implementation without mocks to ensure everything works.
"""
import sys
from pathlib import Path
import time
import json
from PIL import Image
from io import BytesIO

# Add project root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from backend.config import settings
    from backend import pipeline
    from backend.models import vlm, sd, three_d
    print(f"✓ Imports successful")
except Exception as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)

def create_test_tile():
    """Create a simple test tile with some recognizable content"""
    img = Image.new('RGBA', (32, 32), (255, 255, 255, 0))
    # Draw a simple red square in the center
    for x in range(8, 24):
        for y in range(8, 24):
            img.putpixel((x, y), (255, 0, 0, 255))
    bio = BytesIO()
    img.save(bio, format='PNG')
    return bio.getvalue()

def test_vlm():
    """Test VLM component"""
    print("\n=== Testing VLM ===")
    try:
        model = vlm.load_vlm_model()
        test_bytes = create_test_tile()
        attrs = vlm.extract_attributes(model, test_bytes)
        print(f"✓ VLM extraction successful: {attrs}")
        prompt = vlm.to_prompt(attrs)
        print(f"✓ Prompt generation: {prompt[:100]}...")
        return True
    except Exception as e:
        print(f"✗ VLM test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sd():
    """Test Stable Diffusion component"""
    print("\n=== Testing SD ===")
    try:
        model = sd.load_sd_model()
        test_prompt = "red square object, voxel-style, low-poly, 3D render"
        img_bytes = sd.generate_image(model, test_prompt)
        print(f"✓ SD generation successful: {len(img_bytes)} bytes")
        # Save test image
        test_dir = ROOT / 'test_outputs'
        test_dir.mkdir(exist_ok=True)
        (test_dir / 'sd_test.png').write_bytes(img_bytes)
        print(f"✓ SD output saved to test_outputs/sd_test.png")
        return True
    except Exception as e:
        print(f"✗ SD test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_three_d():
    """Test 3D generation component"""
    print("\n=== Testing 3D Generation ===")
    try:
        test_dir = ROOT / 'test_outputs'
        test_dir.mkdir(exist_ok=True)
        # Use the SD output if available, otherwise create a dummy
        sd_path = test_dir / 'sd_test.png'
        if sd_path.exists():
            img_bytes = sd_path.read_bytes()
        else:
            img_bytes = create_test_tile()
        
        out_path = test_dir / 'test_model.obj'
        result_path = three_d.generate_glb_from_image(img_bytes, out_path, quality='light')
        print(f"✓ 3D generation successful: {result_path}")
        print(f"✓ File exists: {result_path.exists()}, size: {result_path.stat().st_size if result_path.exists() else 0} bytes")
        return True
    except Exception as e:
        print(f"✗ 3D generation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complete_pipeline():
    """Test the complete pipeline"""
    print("\n=== Testing Complete Pipeline ===")
    try:
        test_bytes = create_test_tile()
        result_path, meta = pipeline.run_light_pipeline(test_bytes)
        print(f"✓ Complete pipeline successful: {result_path}")
        print(f"✓ Meta: {json.dumps(meta, indent=2)}")
        return True
    except Exception as e:
        print(f"✗ Complete pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("Starting end-to-end pipeline test...")
    print(f"Settings loaded: {settings.VLM_URL}, {settings.SD_VENV_PYTHON}, {settings.TRIPOSR_PYTHON}")
    
    tests = [
        ("VLM", test_vlm),
        ("SD", test_sd),
        ("3D", test_three_d),
        ("Complete Pipeline", test_complete_pipeline)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"Running test: {name}")
        start_time = time.time()
        success = test_func()
        duration = time.time() - start_time
        results.append((name, success, duration))
        print(f"Test {name}: {'PASSED' if success else 'FAILED'} ({duration:.2f}s)")
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY:")
    all_passed = True
    for name, success, duration in results:
        status = "PASS" if success else "FAIL"
        print(f"  {name:20} {status:4} ({duration:.2f}s)")
        if not success:
            all_passed = False
    
    print(f"\nOverall result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())