from ._anvil_designer import PaintFormTemplate
from anvil import *
import anvil.server
import anvil.media
import time

class PaintForm(PaintFormTemplate):
    def __init__(self, **properties):
        # Set Form properties and Data Bindings.
        self.init_components(**properties)
        
        # Initialize canvas
        self.canvas_info = anvil.server.call('get_canvas_info')
        self.tile_size = self.canvas_info['tile_size']
        self.current_tool = 'brush'
        self.current_color = '#FF0000'
        self.brush_size = 2
        self.zoom_level = 1.0
        self.view_x = 0
        self.view_y = 0
        
        # Drawing state
        self.is_drawing = False
        self.last_pos = None
        
        # Tile cache
        self.tile_cache = {}
        
        # Setup UI
        self.setup_canvas()
        self.setup_tools()
        self.update_status()
        
    def setup_canvas(self):
        """Initialize the drawing canvas"""
        # Set canvas size for viewport
        self.canvas.width = 800
        self.canvas.height = 600
        
        # Bind mouse events
        self.canvas.add_event_handler('mouse_down', self.canvas_mouse_down)
        self.canvas.add_event_handler('mouse_move', self.canvas_mouse_move)
        self.canvas.add_event_handler('mouse_up', self.canvas_mouse_up)
        
        # Initial canvas draw
        self.redraw_canvas()
    
    def setup_tools(self):
        """Setup drawing tools UI"""
        # Color picker
        self.color_picker.foreground = self.current_color
        
        # Brush size slider
        self.brush_size_slider.min = 1
        self.brush_size_slider.max = 10
        self.brush_size_slider.step = 1
        self.brush_size_slider.value = self.brush_size
        
        # Zoom slider
        self.zoom_slider.min = 0.1
        self.zoom_slider.max = 5.0
        self.zoom_slider.step = 0.1
        self.zoom_slider.value = self.zoom_level
    
    def canvas_mouse_down(self, x, y, button, **event_args):
        """Handle mouse down on canvas"""
        if button == 1:  # Left click
            self.is_drawing = True
            self.last_pos = (x, y)
            self.draw_at_position(x, y)
    
    def canvas_mouse_move(self, x, y, **event_args):
        """Handle mouse move on canvas"""
        # Update coordinate display
        world_x, world_y = self.canvas_to_world(x, y)
        tile_x, tile_y = self.world_to_tile(world_x, world_y)
        self.coord_label.text = f"座標: ({world_x:.0f}, {world_y:.0f}) タイル: ({tile_x}, {tile_y})"
        
        if self.is_drawing and self.last_pos:
            self.draw_line(self.last_pos[0], self.last_pos[1], x, y)
            self.last_pos = (x, y)
    
    def canvas_mouse_up(self, x, y, button, **event_args):
        """Handle mouse up on canvas"""
        if button == 1:
            self.is_drawing = False
            self.last_pos = None
            self.save_modified_tiles()
    
    def draw_at_position(self, canvas_x, canvas_y):
        """Draw at canvas position"""
        world_x, world_y = self.canvas_to_world(canvas_x, canvas_y)
        
        # Draw circle
        ctx = self.canvas.get_context_2d()
        ctx.fillStyle = self.current_color
        ctx.beginPath()
        ctx.arc(canvas_x, canvas_y, self.brush_size, 0, 2 * 3.14159)
        ctx.fill()
        
        # Mark tile as modified
        tile_x, tile_y = self.world_to_tile(world_x, world_y)
        self.mark_tile_modified(tile_x, tile_y)
    
    def draw_line(self, x1, y1, x2, y2):
        """Draw line between two points"""
        ctx = self.canvas.get_context_2d()
        ctx.strokeStyle = self.current_color
        ctx.lineWidth = self.brush_size * 2
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
        
        # Mark tiles along line as modified
        world_x1, world_y1 = self.canvas_to_world(x1, y1)
        world_x2, world_y2 = self.canvas_to_world(x2, y2)
        
        # Simple line rasterization
        steps = max(abs(x2 - x1), abs(y2 - y1))
        if steps > 0:
            for i in range(int(steps) + 1):
                t = i / steps
                x = x1 + t * (x2 - x1)
                y = y1 + t * (y2 - y1)
                world_x, world_y = self.canvas_to_world(x, y)
                tile_x, tile_y = self.world_to_tile(world_x, world_y)
                self.mark_tile_modified(tile_x, tile_y)
    
    def canvas_to_world(self, canvas_x, canvas_y):
        """Convert canvas coordinates to world coordinates"""
        world_x = (canvas_x / self.zoom_level) + self.view_x
        world_y = (canvas_y / self.zoom_level) + self.view_y
        return world_x, world_y
    
    def world_to_tile(self, world_x, world_y):
        """Convert world coordinates to tile coordinates"""
        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)
        return tile_x, tile_y
    
    def mark_tile_modified(self, tile_x, tile_y):
        """Mark a tile as modified"""
        if (tile_x, tile_y) not in self.tile_cache:
            self.tile_cache[(tile_x, tile_y)] = {'modified': True, 'data': None}
        else:
            self.tile_cache[(tile_x, tile_y)]['modified'] = True
    
    def save_modified_tiles(self):
        """Save all modified tiles to server"""
        modified_count = 0
        for (tile_x, tile_y), tile_info in self.tile_cache.items():
            if tile_info.get('modified', False):
                try:
                    # Extract pixel data from canvas for this tile
                    pixel_data = self.extract_tile_pixels(tile_x, tile_y)
                    result = anvil.server.call('save_tile_data', tile_x, tile_y, pixel_data)
                    if result.get('success'):
                        tile_info['modified'] = False
                        modified_count += 1
                except Exception as e:
                    print(f"Failed to save tile {tile_x},{tile_y}: {e}")
        
        if modified_count > 0:
            self.update_status()
            alert(f"{modified_count} タイルを保存しました")
    
    def extract_tile_pixels(self, tile_x, tile_y):
        """Extract pixel data for a specific tile from canvas"""
        # This is a simplified version - in a real implementation,
        # you'd extract the actual pixel data from the canvas
        # For now, return a simple pattern based on current color
        pixels = []
        color_rgb = self.hex_to_rgb(self.current_color)
        
        for y in range(self.tile_size):
            for x in range(self.tile_size):
                # Simple pattern - you'd replace this with actual canvas pixel extraction
                pixels.append([color_rgb[0], color_rgb[1], color_rgb[2], 255])
        
        return pixels
    
    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def redraw_canvas(self):
        """Redraw the entire canvas"""
        ctx = self.canvas.get_context_2d()
        ctx.clearRect(0, 0, self.canvas.width, self.canvas.height)
        
        # Draw grid
        self.draw_grid(ctx)
        
        # Load and draw tiles in viewport
        self.draw_tiles(ctx)
    
    def draw_grid(self, ctx):
        """Draw tile grid"""
        ctx.strokeStyle = '#333333'
        ctx.lineWidth = 1
        
        # Calculate visible tile range
        start_tile_x = int(self.view_x // self.tile_size)
        start_tile_y = int(self.view_y // self.tile_size)
        end_tile_x = start_tile_x + int(self.canvas.width // (self.tile_size * self.zoom_level)) + 2
        end_tile_y = start_tile_y + int(self.canvas.height // (self.tile_size * self.zoom_level)) + 2
        
        # Draw vertical lines
        for tile_x in range(start_tile_x, end_tile_x):
            x = (tile_x * self.tile_size - self.view_x) * self.zoom_level
            if 0 <= x <= self.canvas.width:
                ctx.beginPath()
                ctx.moveTo(x, 0)
                ctx.lineTo(x, self.canvas.height)
                ctx.stroke()
        
        # Draw horizontal lines
        for tile_y in range(start_tile_y, end_tile_y):
            y = (tile_y * self.tile_size - self.view_y) * self.zoom_level
            if 0 <= y <= self.canvas.height:
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(self.canvas.width, y)
                ctx.stroke()
    
    def draw_tiles(self, ctx):
        """Draw tiles in viewport"""
        # Calculate visible tile range
        start_tile_x = int(self.view_x // self.tile_size)
        start_tile_y = int(self.view_y // self.tile_size)
        end_tile_x = start_tile_x + int(self.canvas.width // (self.tile_size * self.zoom_level)) + 2
        end_tile_y = start_tile_y + int(self.canvas.height // (self.tile_size * self.zoom_level)) + 2
        
        for tile_x in range(start_tile_x, end_tile_x):
            for tile_y in range(start_tile_y, end_tile_y):
                self.draw_tile(ctx, tile_x, tile_y)
    
    def draw_tile(self, ctx, tile_x, tile_y):
        """Draw a single tile"""
        try:
            # Get tile from server
            tile_media = anvil.server.call('get_tile', tile_x, tile_y)
            
            # Calculate position on canvas
            x = (tile_x * self.tile_size - self.view_x) * self.zoom_level
            y = (tile_y * self.tile_size - self.view_y) * self.zoom_level
            size = self.tile_size * self.zoom_level
            
            # Draw tile (simplified - in real implementation you'd draw the actual image)
            if tile_media:
                # For now, just draw a colored rectangle to represent the tile
                ctx.fillStyle = '#CCCCCC'
                ctx.fillRect(x, y, size, size)
            
        except Exception as e:
            print(f"Failed to draw tile {tile_x},{tile_y}: {e}")
    
    def update_status(self):
        """Update status display"""
        try:
            modified_tiles = anvil.server.call('get_modified_tiles')
            self.status_label.text = f"変更されたタイル: {len(modified_tiles)}"
        except Exception as e:
            self.status_label.text = f"ステータス取得エラー: {e}"
    
    # Event handlers for UI controls
    def color_picker_change(self, **event_args):
        """Handle color picker change"""
        self.current_color = self.color_picker.foreground
    
    def brush_size_slider_change(self, **event_args):
        """Handle brush size change"""
        self.brush_size = self.brush_size_slider.value
        self.brush_size_label.text = f"ブラシサイズ: {self.brush_size}"
    
    def zoom_slider_change(self, **event_args):
        """Handle zoom change"""
        self.zoom_level = self.zoom_slider.value
        self.zoom_label.text = f"ズーム: {self.zoom_level:.1f}x"
        self.redraw_canvas()
    
    def pan_up_click(self, **event_args):
        """Pan view up"""
        self.view_y -= 50
        self.redraw_canvas()
    
    def pan_down_click(self, **event_args):
        """Pan view down"""
        self.view_y += 50
        self.redraw_canvas()
    
    def pan_left_click(self, **event_args):
        """Pan view left"""
        self.view_x -= 50
        self.redraw_canvas()
    
    def pan_right_click(self, **event_args):
        """Pan view right"""
        self.view_x += 50
        self.redraw_canvas()
    
    def generate_3d_click(self, **event_args):
        """Start 3D generation"""
        try:
            result = anvil.server.call('start_3d_generation')
            if result.get('success'):
                job_id = result['job_id']
                tiles_count = len(result['tiles'])
                alert(f"3D生成を開始しました (ジョブID: {job_id}, タイル数: {tiles_count})")
                
                # Monitor job progress
                self.monitor_generation_job(job_id)
            else:
                alert(f"3D生成の開始に失敗: {result.get('message', 'Unknown error')}")
        except Exception as e:
            alert(f"3D生成エラー: {e}")
    
    def monitor_generation_job(self, job_id):
        """Monitor generation job progress"""
        def check_progress():
            try:
                status = anvil.server.call('get_job_status', job_id)
                progress = status.get('progress', 0)
                total = status.get('total', 1)
                current_tile = status.get('current_tile', '')
                
                self.generation_progress.text = f"進捗: {progress}/{total} - {current_tile}"
                
                if status.get('status') == 'completed':
                    alert("3D生成が完了しました！")
                    self.generation_progress.text = "3D生成完了"
                    self.update_status()
                elif status.get('status') == 'processing':
                    # Continue monitoring
                    anvil.timer.call_later(2, check_progress)
                    
            except Exception as e:
                print(f"Progress monitoring error: {e}")
        
        # Start monitoring
        anvil.timer.call_later(1, check_progress)
    
    def clear_canvas_click(self, **event_args):
        """Clear the canvas"""
        if confirm("キャンバスをクリアしますか？"):
            ctx = self.canvas.get_context_2d()
            ctx.clearRect(0, 0, self.canvas.width, self.canvas.height)
            self.tile_cache.clear()
            self.redraw_canvas()
    
    def save_canvas_click(self, **event_args):
        """Save current canvas state"""
        self.save_modified_tiles()
    
    def world_view_click(self, **event_args):
        """Switch to 3D world view"""
        # This would open the 3D world view form
        from .WorldForm import WorldForm
        world_form = WorldForm()
        world_form.show()
