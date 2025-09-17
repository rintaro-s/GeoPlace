from ._anvil_designer import WorldFormTemplate
from anvil import *
import anvil.server
import time

class WorldForm(WorldFormTemplate):
    def __init__(self, **properties):
        # Set Form properties and Data Bindings.
        self.init_components(**properties)
        
        # 3D World state
        self.camera_position = [0, 5, 10]
        self.camera_rotation = [0, 0, 0]
        self.objects = []
        self.selected_object = None
        
        # Movement state
        self.movement_keys = {
            'w': False, 's': False, 'a': False, 'd': False,
            'space': False, 'shift': False
        }
        
        # Setup 3D world
        self.setup_world()
        self.load_3d_objects()
        
    def setup_world(self):
        """Initialize 3D world display"""
        # Setup A-Frame scene (simplified for Anvil)
        self.scene_html = """
        <a-scene embedded style="height: 600px; width: 100%;">
          <a-sky color="#87CEEB"></a-sky>
          <a-plane position="0 0 0" rotation="-90 0 0" width="1000" height="1000" color="#90EE90"></a-plane>
          
          <!-- Lighting -->
          <a-light type="ambient" color="#404040"></a-light>
          <a-light type="directional" position="10 10 10" color="#FFFFFF"></a-light>
          
          <!-- Camera with controls -->
          <a-entity id="cameraRig" position="0 5 10">
            <a-camera id="camera" look-controls wasd-controls></a-camera>
          </a-entity>
          
          <!-- Objects will be added here -->
          <a-entity id="objects"></a-entity>
        </a-scene>
        """
        
        # Set HTML content (in real Anvil, you'd use proper 3D components)
        self.world_display.content = self.scene_html
        
    def load_3d_objects(self):
        """Load and display 3D objects"""
        try:
            self.objects = anvil.server.call('get_3d_objects')
            self.update_objects_list()
            self.render_objects()
        except Exception as e:
            self.status_label.text = f"オブジェクト読み込みエラー: {e}"
    
    def update_objects_list(self):
        """Update the objects list display"""
        self.objects_list.clear()
        
        for obj in self.objects:
            item = {
                'id': obj['id'],
                'position': f"({obj['x']:.1f}, {obj['y']:.1f}, {obj['z']:.1f})",
                'scale': obj.get('scale', 1.0),
                'created': time.strftime('%H:%M:%S', time.localtime(obj.get('created_at', 0)))
            }
            self.objects_list.add_component(Label(text=f"{item['id']} - {item['position']} - Scale: {item['scale']}"))
        
        self.objects_count_label.text = f"オブジェクト数: {len(self.objects)}"
    
    def render_objects(self):
        """Render objects in 3D scene"""
        # In a real implementation, this would update the A-Frame scene
        # For now, we'll just update the display info
        objects_info = []
        for obj in self.objects:
            info = f"ID: {obj['id']}, Position: ({obj['x']}, {obj['y']}, {obj['z']}), Scale: {obj.get('scale', 1.0)}"
            objects_info.append(info)
        
        if objects_info:
            self.scene_info.text = "\n".join(objects_info[:5])  # Show first 5 objects
            if len(objects_info) > 5:
                self.scene_info.text += f"\n... and {len(objects_info) - 5} more objects"
        else:
            self.scene_info.text = "3Dオブジェクトがありません"
    
    def refresh_objects_click(self, **event_args):
        """Refresh 3D objects from server"""
        self.load_3d_objects()
        alert("オブジェクトを更新しました")
    
    def teleport_click(self, **event_args):
        """Teleport to specified coordinates"""
        try:
            x = float(self.teleport_x.text or 0)
            y = float(self.teleport_y.text or 5)
            z = float(self.teleport_z.text or 0)
            
            self.camera_position = [x, y, z]
            self.update_camera_info()
            
            # In real implementation, this would update the A-Frame camera
            alert(f"座標 ({x}, {y}, {z}) にテレポートしました")
            
        except ValueError:
            alert("有効な座標を入力してください")
    
    def preset_teleport_click(self, **event_args):
        """Teleport to preset locations"""
        sender = event_args.get('sender')
        
        presets = {
            'origin': [0, 5, 0],
            'overview': [0, 50, 50],
            'corner': [100, 5, 100]
        }
        
        if hasattr(sender, 'tag') and sender.tag in presets:
            pos = presets[sender.tag]
            self.camera_position = pos
            self.teleport_x.text = str(pos[0])
            self.teleport_y.text = str(pos[1])
            self.teleport_z.text = str(pos[2])
            self.update_camera_info()
            alert(f"プリセット位置 {sender.tag} にテレポートしました")
    
    def update_camera_info(self):
        """Update camera position display"""
        pos = self.camera_position
        self.camera_info.text = f"カメラ位置: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})"
    
    def movement_help_click(self, **event_args):
        """Show movement help"""
        help_text = """
3D世界の操作方法:

移動:
- W, A, S, D: 前後左右移動
- Space: 上昇
- Shift: 下降
- マウス: 視点回転

機能:
- テレポート: 座標を入力して瞬間移動
- プリセット: よく使う場所への移動
- オブジェクト一覧: 配置された3Dオブジェクトの確認

注意: この画面は3Dオブジェクトの表示のみです。
ペイントは「ペイント画面に戻る」から行ってください。
        """
        alert(help_text)
    
    def back_to_paint_click(self, **event_args):
        """Return to paint form"""
        from .PaintForm import PaintForm
        paint_form = PaintForm()
        paint_form.show()
    
    def clear_objects_click(self, **event_args):
        """Clear all 3D objects (with confirmation)"""
        if confirm("すべての3Dオブジェクトを削除しますか？この操作は取り消せません。"):
            try:
                # In real implementation, this would call a server function to clear objects
                # anvil.server.call('clear_all_objects')
                alert("オブジェクトクリア機能は未実装です")
            except Exception as e:
                alert(f"オブジェクトクリアエラー: {e}")
    
    def export_objects_click(self, **event_args):
        """Export objects data"""
        try:
            objects_json = str(self.objects)
            # In real implementation, this would create a downloadable file
            alert(f"オブジェクトデータ:\n{objects_json[:200]}...")
        except Exception as e:
            alert(f"エクスポートエラー: {e}")
    
    def form_show(self, **event_args):
        """Called when form is shown"""
        self.update_camera_info()
        self.load_3d_objects()
