<#
Create a dedicated venv for Stable Diffusion and install required packages.
Usage (PowerShell):
  .\scripts\create_sd_venv.ps1 -Path .\venv-sd -Model runwayml/stable-diffusion-v1-5
#>
param(
    [string]$Path = '.\\venv-sd',
    [string]$Model = 'runwayml/stable-diffusion-v1-5'
)
$abs = Resolve-Path $Path -ErrorAction SilentlyContinue
if (-not $abs) {
    python -m venv $Path
}
& $Path\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
# Install CPU PyTorch by default; if you want GPU, please modify manually
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.1.1+cpu torchvision==0.15.2+cpu --extra-index-url https://download.pytorch.org/whl/cpu
pip install diffusers transformers accelerate safetensors huggingface_hub
# Optionally, pre-download the model to the venv cache
  # Optionally, pre-download the model to the venv cache by writing a small Python script and running it
  $tmpPy = Join-Path $env:TEMP "preload_sd_model_$([System.Guid]::NewGuid().ToString()).py"
$pyContent = @"
from diffusers import StableDiffusionPipeline
try:
  m = StableDiffusionPipeline.from_pretrained(r'''$Model''')
  print('preloaded model:', type(m))
except Exception as e:
  import traceback
  traceback.print_exc()
  raise
"@
  $pyContent | Out-File -FilePath $tmpPy -Encoding utf8
  & python $tmpPy
  Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue
Write-Output "Created SD venv at $Path. Activate with: & $Path\Scripts\Activate.ps1"
