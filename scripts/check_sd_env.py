import sys
print('Python executable:', sys.executable)
try:
    import torch
    print('torch version:', getattr(torch,'__version__',None))
    try:
        cuda_available = torch.cuda.is_available()
    except Exception as e:
        cuda_available = f'error checking cuda: {e}'
    print('torch.cuda.is_available():', cuda_available)
except Exception as e:
    print('torch import error:', repr(e))

try:
    import diffusers
    print('diffusers import: ok')
except Exception as e:
    print('diffusers import error:', repr(e))

try:
    import transformers
    print('transformers import: ok')
except Exception as e:
    print('transformers import error:', repr(e))

try:
    import safetensors
    print('safetensors import: ok')
except Exception as e:
    print('safetensors import error:', repr(e))

try:
    import accelerate
    print('accelerate import: ok')
except Exception as e:
    print('accelerate import error:', repr(e))

print('\nFinished checks')
