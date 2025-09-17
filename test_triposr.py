import sys
from pathlib import Path
from backend.models.three_d import generate_glb_from_image

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_triposr.py <input_image> [output_glb]")
        return
        
    input_image = Path(sys.argv[1])
    output_glb = sys.argv[2] if len(sys.argv) > 2 else 'output.glb'
    
    if not input_image.exists():
        print(f"Error: Input image not found: {input_image}")
        return
        
    print(f"Testing TripoSR with {input_image}...")
    
    try:
        with open(input_image, 'rb') as f:
            image_data = f.read()
            
        output_path = generate_glb_from_image(image_data, Path(output_glb))
        print(f"Success! Output saved to: {output_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
