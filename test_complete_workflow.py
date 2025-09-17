"""
Test script for the complete AI pipeline workflow
Tests: VLM → SD → TripoSR → GLB generation
"""
import sys
import asyncio
from pathlib import Path
from backend.workflows.generate_3d import run_complete_3d_workflow, register_3d_object

def test_workflow_with_sample_tile():
    """Test the complete workflow with a sample tile"""
    
    # Create a simple test image (32x32 red square)
    from PIL import Image
    from io import BytesIO
    
    test_image = Image.new('RGBA', (32, 32), (255, 0, 0, 255))  # Red square
    buffer = BytesIO()
    test_image.save(buffer, format='PNG')
    test_image_bytes = buffer.getvalue()
    
    print("Testing complete 3D generation workflow...")
    print("1. Creating test tile image (32x32 red square)")
    
    try:
        # Test coordinates
        tile_x, tile_y = 100, 100
        
        print("2. Running complete workflow...")
        glb_path, metadata = run_complete_3d_workflow(test_image_bytes, tile_x, tile_y)
        
        print(f"3. Generated GLB: {glb_path}")
        print(f"4. Metadata: {metadata}")
        
        print("5. Registering 3D object...")
        register_3d_object(glb_path, metadata, tile_x, tile_y)
        
        print("✅ Workflow test completed successfully!")
        print(f"   GLB file: {glb_path}")
        print(f"   File exists: {glb_path.exists()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_lm_studio_connection():
    """Test LM Studio connection"""
    from backend.models.vlm import load_vlm_model, extract_attributes
    from PIL import Image
    from io import BytesIO
    
    print("Testing LM Studio connection...")
    
    try:
        # Create test image
        test_image = Image.new('RGBA', (32, 32), (0, 255, 0, 255))  # Green square
        buffer = BytesIO()
        test_image.save(buffer, format='PNG')
        test_image_bytes = buffer.getvalue()
        
        # Test VLM
        model = load_vlm_model()
        print(f"VLM Model config: {model}")
        
        attributes = extract_attributes(model, test_image_bytes)
        print(f"Extracted attributes: {attributes}")
        
        print("✅ LM Studio connection test completed!")
        return True
        
    except Exception as e:
        print(f"❌ LM Studio test failed: {e}")
        print("Make sure LM Studio is running on localhost:1234")
        return False

def test_triposr_script():
    """Test TripoSR PowerShell script"""
    import subprocess
    from PIL import Image
    import tempfile
    
    print("Testing TripoSR PowerShell script...")
    
    try:
        # Create test image file
        test_image = Image.new('RGB', (256, 256), (128, 128, 255))  # Blue square
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_image = temp_path / "test_input.png"
            output_dir = temp_path / "output"
            
            test_image.save(input_image)
            
            # Test the PowerShell script
            script_path = Path("run_triposr.ps1").absolute()
            cmd = [
                'powershell.exe',
                '-ExecutionPolicy', 'Bypass',
                '-File', str(script_path),
                str(input_image),
                str(output_dir)
            ]
            
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                print("✅ TripoSR script test completed!")
                print(f"Output: {result.stdout}")
                
                # Check for GLB files
                glb_files = list(output_dir.glob("*.glb"))
                if glb_files:
                    print(f"Generated GLB files: {glb_files}")
                else:
                    print("No GLB files found in output")
                    
                return True
            else:
                print(f"❌ TripoSR script failed: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"❌ TripoSR script test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=== AI Pipeline Test Suite ===\n")
    
    tests = [
        ("LM Studio Connection", test_lm_studio_connection),
        ("TripoSR Script", test_triposr_script),
        ("Complete Workflow", test_workflow_with_sample_tile),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        results[test_name] = test_func()
        print()
    
    print("=== Test Results ===")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if not all_passed:
        print("\nTroubleshooting:")
        if not results.get("LM Studio Connection"):
            print("- Make sure LM Studio is running on localhost:1234")
            print("- Load a vision model (like Gemma-2-2B-IT)")
        if not results.get("TripoSR Script"):
            print("- Check TripoSR installation at E:\\GITS\\TripoSR-main")
            print("- Verify torchmcubes is installed")

if __name__ == "__main__":
    main()
