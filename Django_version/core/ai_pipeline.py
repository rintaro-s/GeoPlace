"""
Complete AI Pipeline: VLM -> Stable Diffusion -> TripoSR
"""
import requests
import base64
import json
import time
import subprocess
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import io
import logging
import threading
import queue
from django.conf import settings
from django.utils import timezone
from .models import VLMAnalysis, GenerationJob, Tile, ThreeDObject
from .services import TileService, ObjectService

logger = logging.getLogger('geoplace')


class VLMService:
    """Vision-Language Model service using LM Studio"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.base_url = self.config['LM_STUDIO_BASE_URL']
        self.model = self.config['LM_STUDIO_MODEL']
        self.timeout = self.config['LM_STUDIO_TIMEOUT']
    
    def analyze_image(self, image_bytes):
        """Analyze image with VLM and extract attributes"""
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Prepare prompt
            prompt = """この画像に写っているオブジェクトを分析して、以下の形式で回答してください：

カテゴリ: [house/tree/river/person/car/building/nature/other のいずれか]
色: [主要な色を2-3個、英語で]
サイズ: [small/medium/large のいずれか]
向き: [front/side/back/diagonal のいずれか]
特徴: [窓、屋根、葉、枝などの特徴を2-3個、日本語で]"""
            
            payload = {
                "model": self.model,
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
            
            start_time = time.time()
            response = requests.post(
                self.base_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=self.timeout
            )
            processing_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                attributes = self._parse_vlm_response(content)
                attributes['processing_time'] = processing_time
                attributes['model_used'] = self.model
                return attributes
            else:
                logger.error(f"VLM API error: {response.status_code} - {response.text}")
                return self._fallback_attributes()
                
        except Exception as e:
            logger.error(f"VLM analysis error: {e}")
            return self._fallback_attributes()
    
    def _parse_vlm_response(self, content):
        """Parse VLM response into structured data"""
        import re
        
        try:
            category_match = re.search(r'カテゴリ[：:]\s*(\w+)', content)
            colors_match = re.search(r'色[：:]\s*([^\n]+)', content)
            size_match = re.search(r'サイズ[：:]\s*(\w+)', content)
            orientation_match = re.search(r'向き[：:]\s*(\w+)', content)
            details_match = re.search(r'特徴[：:]\s*([^\n]+)', content)
            
            return {
                'category': category_match.group(1) if category_match else 'object',
                'colors': [c.strip() for c in re.split(r'[,、]', colors_match.group(1))] if colors_match else ['gray'],
                'size': size_match.group(1) if size_match else 'medium',
                'orientation': orientation_match.group(1) if orientation_match else 'front',
                'details': [d.strip() for d in re.split(r'[,、]', details_match.group(1))] if details_match else ['オブジェクト'],
                'confidence_score': 0.8,
                'raw_response': content
            }
        except Exception as e:
            logger.error(f"Error parsing VLM response: {e}")
            return self._fallback_attributes()
    
    def _fallback_attributes(self):
        """Fallback attributes when VLM fails"""
        return {
            'category': 'object',
            'colors': ['gray'],
            'size': 'medium',
            'orientation': 'front',
            'details': ['シンプルなオブジェクト'],
            'confidence_score': 0.0,
            'processing_time': 0.0,
            'model_used': 'fallback'
        }


class StableDiffusionService:
    """Stable Diffusion service for image generation"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.model_id = self.config['SD_MODEL_ID']
        self.resolution = self.config['SD_RESOLUTION']
        self.steps_light = self.config['SD_STEPS_LIGHT']
        self.steps_high = self.config['SD_STEPS_HIGH']
        self.pipe = None
        self._load_model()
    
    def _load_model(self):
        """Load Stable Diffusion model"""
        try:
            from diffusers import StableDiffusionPipeline
            import torch
            
            logger.info(f"Loading Stable Diffusion model: {self.model_id}")
            
            self.pipe = StableDiffusionPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                safety_checker=None,
                requires_safety_checker=False
            )
            
            if torch.cuda.is_available():
                self.pipe = self.pipe.to("cuda")
                self.pipe.enable_attention_slicing()
                self.pipe.enable_xformers_memory_efficient_attention()
            
            logger.info("Stable Diffusion model loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading Stable Diffusion model: {e}")
            self.pipe = None
    
    def generate_prompt(self, attributes):
        """Generate SD prompt from VLM attributes"""
        colors = ', '.join(attributes['colors'])
        details = ', '.join(attributes['details'])
        
        prompt = (
            f"voxel-style {attributes['category']}, {attributes['size']} size, "
            f"primary colors: {colors}, features: {details}, "
            f"low-poly, game-friendly, 3D render, {attributes['orientation']} view, "
            f"clean background, high quality, detailed, single object"
        )
        
        negative_prompt = (
            "blurry, low quality, distorted, multiple objects, text, watermark, "
            "signature, complex background, realistic, photographic"
        )
        
        return prompt, negative_prompt
    
    def generate_image(self, prompt, negative_prompt=None, quality='light'):
        """Generate image using Stable Diffusion"""
        if not self.pipe:
            logger.error("Stable Diffusion model not loaded")
            return None
        
        try:
            steps = self.steps_light if quality == 'light' else self.steps_high
            
            logger.info(f"Generating SD image with prompt: {prompt[:100]}...")
            
            with torch.no_grad():
                result = self.pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    height=self.resolution,
                    width=self.resolution,
                    num_inference_steps=steps,
                    guidance_scale=7.5,
                    num_images_per_prompt=1
                )
            
            image = result.images[0]
            logger.info("SD image generated successfully")
            return image
            
        except Exception as e:
            logger.error(f"Error generating SD image: {e}")
            return None


class TripoSRService:
    """TripoSR service for 2D to 3D conversion"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.triposr_dir = self.config['TRIPOSR_DIR']
        self.triposr_py = self.config['TRIPOSR_PY']
        self.bake_texture = self.config['TRIPOSR_BAKE_TEXTURE']
    
    def generate_3d_model(self, image, output_path, quality='light'):
        """Generate 3D model from 2D image using TripoSR"""
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Save input image
                input_png = temp_path / 'input.png'
                if isinstance(image, Image.Image):
                    image.save(input_png, 'PNG')
                else:
                    # Assume it's bytes
                    with open(input_png, 'wb') as f:
                        f.write(image)
                
                # Prepare output directory
                output_dir = temp_path / 'output'
                output_dir.mkdir()
                
                # Build TripoSR command
                script_path = self.triposr_dir / self.triposr_py
                
                cmd = [
                    'python', str(script_path),
                    str(input_png),
                    '--output-dir', str(output_dir),
                    '--model-save-format', 'glb'
                ]
                
                if self.bake_texture:
                    cmd.append('--bake-texture')
                
                if quality == 'light':
                    cmd.extend(['--render'])
                
                logger.info(f"Running TripoSR: {' '.join(cmd)}")
                
                # Run TripoSR
                result = subprocess.run(
                    cmd,
                    cwd=str(self.triposr_dir),
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout
                )
                
                if result.returncode == 0:
                    # Find generated GLB file
                    glb_files = list(output_dir.glob('*.glb'))
                    if glb_files:
                        glb_file = glb_files[0]
                        shutil.move(str(glb_file), str(output_path))
                        logger.info(f"TripoSR generated GLB: {output_path}")
                        return output_path
                    else:
                        logger.error("TripoSR did not generate GLB file")
                        return self._create_fallback_glb(output_path, image)
                else:
                    logger.error(f"TripoSR failed: {result.stderr}")
                    return self._create_fallback_glb(output_path, image)
                    
        except Exception as e:
            logger.error(f"Error running TripoSR: {e}")
            return self._create_fallback_glb(output_path, image)
    
    def _create_fallback_glb(self, output_path, original_image):
        """Create fallback GLB file"""
        try:
            with open(output_path, 'wb') as f:
                f.write(b'GLB_FALLBACK_DJANGO\n')
                f.write(b'ORIGINAL_IMAGE_PNG:\n')
                
                if isinstance(original_image, Image.Image):
                    buffer = io.BytesIO()
                    original_image.save(buffer, format='PNG')
                    f.write(buffer.getvalue())
                else:
                    f.write(original_image)
            
            logger.info(f"Created fallback GLB: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating fallback GLB: {e}")
            return None


class AIWorkflowService:
    """Complete AI workflow orchestrator"""
    
    def __init__(self):
        self.vlm_service = VLMService()
        self.sd_service = StableDiffusionService()
        self.triposr_service = TripoSRService()
        self.tile_service = TileService()
        self.object_service = ObjectService()
        self.config = settings.GEOPLACE_CONFIG
    
    def run_complete_workflow(self, tile_x, tile_y, job_id=None, quality='light'):
        """Run complete AI workflow for a tile"""
        workflow_id = f"tile_{tile_x}_{tile_y}_{int(time.time())}"
        
        try:
            logger.info(f"[{workflow_id}] Starting AI workflow for tile ({tile_x}, {tile_y})")
            
            # Update job status
            if job_id:
                self._update_job_status(job_id, 'vlm_analyzing', f"tile_{tile_x}_{tile_y}")
            
            # Step 1: Load tile image
            tile_image = self.tile_service.load_tile_image(tile_x, tile_y)
            
            # Convert to bytes for VLM
            buffer = io.BytesIO()
            tile_image.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()
            
            # Step 2: VLM Analysis
            logger.info(f"[{workflow_id}] Step 1: VLM analysis...")
            attributes = self.vlm_service.analyze_image(image_bytes)
            
            # Save VLM analysis
            tile_obj, _ = Tile.objects.get_or_create(x=tile_x, y=tile_y)
            vlm_analysis, created = VLMAnalysis.objects.get_or_create(
                tile=tile_obj,
                defaults={
                    'category': attributes['category'],
                    'colors': attributes['colors'],
                    'size': attributes['size'],
                    'orientation': attributes['orientation'],
                    'details': attributes['details'],
                    'confidence_score': attributes.get('confidence_score', 0.0),
                    'processing_time': attributes.get('processing_time', 0.0),
                    'model_used': attributes.get('model_used', '')
                }
            )
            
            # Step 3: Generate SD prompt
            if job_id:
                self._update_job_status(job_id, 'sd_generating', f"tile_{tile_x}_{tile_y}")
            
            logger.info(f"[{workflow_id}] Step 2: Generating SD prompt...")
            prompt, negative_prompt = self.sd_service.generate_prompt(attributes)
            vlm_analysis.sd_prompt = prompt
            vlm_analysis.save()
            
            # Step 4: Stable Diffusion generation
            logger.info(f"[{workflow_id}] Step 3: SD generation...")
            sd_image = self.sd_service.generate_image(prompt, negative_prompt, quality)
            
            if not sd_image:
                # Use original tile image as fallback
                sd_image = tile_image
                logger.warning(f"[{workflow_id}] Using original tile image as SD fallback")
            
            # Step 5: TripoSR 3D generation
            if job_id:
                self._update_job_status(job_id, 'triposr_generating', f"tile_{tile_x}_{tile_y}")
            
            logger.info(f"[{workflow_id}] Step 4: TripoSR generation...")
            glb_path = self.config['GLB_DIR'] / f"{workflow_id}.glb"
            
            generated_glb = self.triposr_service.generate_3d_model(sd_image, glb_path, quality)
            
            if not generated_glb:
                logger.error(f"[{workflow_id}] TripoSR generation failed")
                return None
            
            # Step 6: Register 3D object
            if job_id:
                self._update_job_status(job_id, 'light_ready', f"tile_{tile_x}_{tile_y}")
            
            logger.info(f"[{workflow_id}] Step 5: Registering 3D object...")
            
            metadata = {
                'workflow_id': workflow_id,
                'tile_coords': [tile_x, tile_y],
                'attributes': attributes,
                'prompt': prompt,
                'quality': quality,
                'timestamp': time.time()
            }
            
            obj = self.object_service.register_3d_object(tile_x, tile_y, generated_glb, metadata)
            
            logger.info(f"[{workflow_id}] Workflow completed successfully")
            return obj
            
        except Exception as e:
            logger.error(f"[{workflow_id}] Workflow failed: {e}")
            if job_id:
                self._update_job_status(job_id, 'failed', f"tile_{tile_x}_{tile_y}", str(e))
            return None
    
    def _update_job_status(self, job_id, status, current_tile=None, error_message=None):
        """Update generation job status"""
        try:
            job = GenerationJob.objects.get(job_id=job_id)
            job.status = status
            if current_tile:
                job.current_tile = current_tile
            if error_message:
                job.error_message = error_message
            job.save()
        except GenerationJob.DoesNotExist:
            logger.error(f"Job {job_id} not found")


class WorkerService:
    """Background worker service for processing generation jobs"""
    
    def __init__(self):
        self.workflow_service = AIWorkflowService()
        self.job_queue = queue.Queue()
        self.workers = []
        self.max_workers = settings.GEOPLACE_CONFIG['MAX_CONCURRENT_WORKERS']
        self.running = False
    
    def start_workers(self):
        """Start background worker threads"""
        if self.running:
            return
        
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"Started {self.max_workers} AI workflow workers")
    
    def stop_workers(self):
        """Stop background worker threads"""
        self.running = False
        # Add sentinel values to wake up workers
        for _ in range(self.max_workers):
            self.job_queue.put(None)
    
    def queue_job(self, job_id, tile_coords, quality='light'):
        """Queue a generation job"""
        job_data = {
            'job_id': job_id,
            'tile_coords': tile_coords,
            'quality': quality
        }
        self.job_queue.put(job_data)
        logger.info(f"Queued job {job_id} with {len(tile_coords)} tiles")
    
    def _worker_loop(self, worker_id):
        """Worker thread main loop"""
        logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Get job from queue
                job_data = self.job_queue.get(timeout=1)
                
                if job_data is None:  # Sentinel value to stop
                    break
                
                job_id = job_data['job_id']
                tile_coords = job_data['tile_coords']
                quality = job_data['quality']
                
                logger.info(f"Worker {worker_id} processing job {job_id}")
                
                # Update job status
                try:
                    job = GenerationJob.objects.get(job_id=job_id)
                    job.status = 'processing'
                    job.total_tiles = len(tile_coords)
                    job.save()
                except GenerationJob.DoesNotExist:
                    logger.error(f"Job {job_id} not found")
                    continue
                
                # Process each tile
                for i, (tile_x, tile_y) in enumerate(tile_coords):
                    try:
                        self.workflow_service.run_complete_workflow(
                            tile_x, tile_y, job_id, quality
                        )
                        
                        # Update progress
                        job.progress = i + 1
                        job.save()
                        
                        # Cooldown between tiles
                        time.sleep(settings.GEOPLACE_CONFIG['PER_TILE_COOLDOWN'])
                        
                    except Exception as e:
                        logger.error(f"Worker {worker_id} error processing tile {tile_x},{tile_y}: {e}")
                
                # Mark job as completed
                job.mark_completed()
                logger.info(f"Worker {worker_id} completed job {job_id}")
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.info(f"Worker {worker_id} stopped")


# Global worker service instance
worker_service = WorkerService()
