# GeoPlace Django Version

A complete rewrite of the GeoPlace collaborative 2D tile painting system with AI-driven 3D object generation using Django framework.

## Features

### Core Functionality
- **Collaborative 2D Canvas**: 20000x20000 pixel canvas with 32x32 pixel tiles
- **Real-time Updates**: WebSocket-based real-time collaboration
- **3D Object Generation**: AI pipeline for converting 2D drawings to 3D objects
- **3D World Navigation**: A-Frame-based 3D world with WASD controls and teleportation
- **Admin Dashboard**: Comprehensive system management interface

### AI Pipeline
- **Vision-Language Model (VLM)**: LM Studio integration for image analysis
- **Stable Diffusion**: Image generation and enhancement
- **TripoSR**: 2D to 3D mesh conversion
- **Background Processing**: Asynchronous job queue with progress tracking

### Technical Features
- **Django REST Framework**: Full API for all operations
- **WebSocket Support**: Real-time updates via Django Channels
- **File System Integration**: Direct access to `E:\files\GeoPLace-tmp\images`
- **Japanese UI**: Complete Japanese language interface
- **Dark Theme**: Modern dark-themed Bootstrap UI

## Installation

### Prerequisites
- Python 3.8+
- Node.js (for A-Frame dependencies)
- LM Studio running locally
- TripoSR installation

### Setup Steps

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Settings**
   Edit `geoplace/settings.py` to configure:
   - Database settings
   - File paths for tiles and assets
   - LM Studio API URL
   - TripoSR installation path

3. **Initialize Database**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Create Required Directories**
   ```bash
   mkdir -p E:\files\GeoPLace-tmp\images
   mkdir -p assets\glb
   ```

5. **Start Development Server**
   ```bash
   python manage.py runserver
   ```

6. **Start WebSocket Server** (in separate terminal)
   ```bash
   python -m channels.routing
   ```

## Configuration

### Django Settings (`geoplace/settings.py`)

Key configuration variables:

```python
# GeoPlace Configuration
GEOPLACE_CONFIG = {
    'TILES_DIR': r'E:\files\GeoPLace-tmp\images',
    'ASSETS_DIR': os.path.join(BASE_DIR, '..', 'assets'),
    'GLB_DIR': os.path.join(BASE_DIR, '..', 'assets', 'glb'),
    'CANVAS_SIZE': (20000, 20000),
    'TILE_SIZE': (32, 32),
    'LM_STUDIO_URL': 'http://localhost:1234/v1',
    'LM_STUDIO_MODEL': 'llava-v1.6-mistral-7b',
    'TRIPOSR_PATH': r'C:\path\to\TripoSR',
    'STABLE_DIFFUSION_MODEL': 'stabilityai/stable-diffusion-2-1',
}
```

### File Structure

```
Django_version/
├── geoplace/                 # Django project settings
│   ├── settings.py          # Main configuration
│   ├── urls.py              # URL routing
│   ├── asgi.py              # ASGI configuration
│   └── wsgi.py              # WSGI configuration
├── core/                    # Main application
│   ├── models.py            # Database models
│   ├── views.py             # HTTP views
│   ├── api_views.py         # REST API views
│   ├── services.py          # Business logic
│   ├── ai_pipeline.py       # AI processing
│   ├── consumers.py         # WebSocket consumers
│   └── serializers.py       # API serializers
├── templates/               # HTML templates
│   ├── base.html            # Base template
│   ├── paint.html           # Canvas interface
│   ├── world.html           # 3D world interface
│   └── admin_dashboard.html # Admin interface
├── manage.py                # Django management
└── requirements.txt         # Python dependencies
```

## Usage

### Accessing the Application

1. **Paint Canvas**: `http://localhost:8000/paint/`
   - Draw on the collaborative canvas
   - Select colors and brush sizes
   - Zoom and pan around the canvas
   - Start 3D generation for selected tiles

2. **3D World**: `http://localhost:8000/world/`
   - Navigate the 3D world with WASD + mouse
   - Use Space/Shift for vertical movement
   - Teleport to preset locations
   - View and interact with 3D objects

3. **Admin Dashboard**: `http://localhost:8000/admin-dashboard/`
   - Monitor system status
   - View active generation jobs
   - Test AI model connectivity
   - Manage system operations

4. **Django Admin**: `http://localhost:8000/admin/`
   - Full database administration
   - User management
   - System configuration

### API Endpoints

#### Tiles
- `GET /api/tiles/` - List tiles
- `GET /api/tiles/{id}/` - Get tile details
- `POST /api/tiles/` - Create tile
- `PUT /api/tiles/{id}/` - Update tile
- `DELETE /api/tiles/{id}/` - Delete tile

#### 3D Objects
- `GET /api/objects/` - List 3D objects
- `GET /api/objects/{id}/` - Get object details
- `POST /api/objects/` - Create object
- `GET /api/objects/region/` - Get objects in region

#### Generation Jobs
- `GET /api/jobs/` - List jobs
- `POST /api/jobs/` - Create generation job
- `GET /api/jobs/{id}/` - Get job status
- `POST /api/jobs/{id}/cancel/` - Cancel job

#### System
- `GET /api/system/status/` - System status
- `GET /api/system/models/` - AI model status
- `GET /api/canvas/stats/` - Canvas statistics

### WebSocket Events

#### Canvas Updates (`/ws/canvas/`)
- `tile_update`: Real-time tile modifications
- `cursor_position`: User cursor positions
- `selection_change`: Tile selection updates

#### Generation Progress (`/ws/generation/`)
- `job_started`: Generation job started
- `job_progress`: Progress updates
- `job_completed`: Job completion
- `job_failed`: Job failure

#### World Updates (`/ws/world/`)
- `object_added`: New 3D object added
- `object_removed`: 3D object removed
- `player_position`: Player position updates

## AI Pipeline

### Workflow
1. **Tile Selection**: User selects tiles for 3D generation
2. **VLM Analysis**: LM Studio analyzes tile content
3. **Image Generation**: Stable Diffusion creates enhanced images
4. **3D Conversion**: TripoSR converts 2D to 3D mesh
5. **Object Registration**: 3D object added to world

### Configuration
- **LM Studio**: Must be running on `http://localhost:1234`
- **Model**: llava-v1.6-mistral-7b or compatible VLM
- **TripoSR**: Requires local installation and PowerShell script
- **Stable Diffusion**: Uses Hugging Face diffusers library

## Development

### Running Tests
```bash
python manage.py test
```

### Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Collecting Static Files
```bash
python manage.py collectstatic
```

### Creating Superuser
```bash
python manage.py createsuperuser
```

## Troubleshooting

### Common Issues

1. **Image Access Errors**
   - Ensure `E:\files\GeoPLace-tmp\images` directory exists
   - Check file permissions
   - Verify TILES_DIR setting

2. **WebSocket Connection Failures**
   - Check if Channels is properly configured
   - Verify ASGI routing
   - Ensure Redis is running (if using Redis channel layer)

3. **AI Pipeline Errors**
   - Verify LM Studio is running
   - Check TripoSR installation path
   - Ensure GPU drivers are updated for PyTorch

4. **Static Files Not Loading**
   - Run `python manage.py collectstatic`
   - Check STATIC_URL and STATIC_ROOT settings
   - Verify DEBUG setting for development

### Performance Optimization

1. **Database**
   - Use PostgreSQL for production
   - Add database indexes for frequently queried fields
   - Implement connection pooling

2. **File Storage**
   - Consider using cloud storage for assets
   - Implement CDN for static files
   - Add file caching

3. **WebSocket**
   - Use Redis for channel layer in production
   - Implement connection limits
   - Add message rate limiting

## Production Deployment

### Requirements
- PostgreSQL database
- Redis for WebSocket channel layer
- Nginx for static file serving
- Gunicorn for WSGI
- Daphne for ASGI (WebSocket)

### Environment Variables
```bash
export DEBUG=False
export SECRET_KEY=your-secret-key
export DATABASE_URL=postgresql://user:pass@localhost/geoplace
export REDIS_URL=redis://localhost:6379/0
```

### Docker Support
Consider containerizing the application with Docker for easier deployment and scaling.

## License

This project is part of the GeoPlace system. See main project documentation for licensing information.

## Support

For issues and questions, refer to the main GeoPlace project documentation or create an issue in the project repository.
