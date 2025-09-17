"""
WebSocket consumers for real-time updates
"""
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
import logging

logger = logging.getLogger('geoplace')


class CanvasConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for canvas real-time updates"""
    
    async def connect(self):
        self.room_group_name = 'canvas_updates'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Canvas WebSocket connected: {self.channel_name}")
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"Canvas WebSocket disconnected: {self.channel_name}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'tile_update':
                # Broadcast tile update to all clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'tile_update_message',
                        'tile_x': data.get('tile_x'),
                        'tile_y': data.get('tile_y'),
                        'timestamp': timezone.now().isoformat(),
                        'sender': self.channel_name
                    }
                )
            
            elif message_type == 'cursor_position':
                # Broadcast cursor position
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'cursor_position_message',
                        'x': data.get('x'),
                        'y': data.get('y'),
                        'user_id': data.get('user_id'),
                        'sender': self.channel_name
                    }
                )
            
            elif message_type == 'viewport_change':
                # Broadcast viewport change
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'viewport_change_message',
                        'viewport_x': data.get('viewport_x'),
                        'viewport_y': data.get('viewport_y'),
                        'zoom': data.get('zoom'),
                        'user_id': data.get('user_id'),
                        'sender': self.channel_name
                    }
                )
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing canvas message: {e}")
    
    async def tile_update_message(self, event):
        # Don't send back to sender
        if event['sender'] != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'tile_update',
                'tile_x': event['tile_x'],
                'tile_y': event['tile_y'],
                'timestamp': event['timestamp']
            }))
    
    async def cursor_position_message(self, event):
        # Don't send back to sender
        if event['sender'] != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'cursor_position',
                'x': event['x'],
                'y': event['y'],
                'user_id': event['user_id']
            }))
    
    async def viewport_change_message(self, event):
        # Don't send back to sender
        if event['sender'] != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'viewport_change',
                'viewport_x': event['viewport_x'],
                'viewport_y': event['viewport_y'],
                'zoom': event['zoom'],
                'user_id': event['user_id']
            }))


class GenerationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for generation job updates"""
    
    async def connect(self):
        self.room_group_name = 'generation_updates'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Generation WebSocket connected: {self.channel_name}")
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"Generation WebSocket disconnected: {self.channel_name}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'subscribe_job':
                # Subscribe to specific job updates
                job_id = data.get('job_id')
                if job_id:
                    await self.channel_layer.group_add(
                        f'job_{job_id}',
                        self.channel_name
                    )
                    await self.send(text_data=json.dumps({
                        'type': 'subscribed',
                        'job_id': job_id
                    }))
            
            elif message_type == 'unsubscribe_job':
                # Unsubscribe from job updates
                job_id = data.get('job_id')
                if job_id:
                    await self.channel_layer.group_discard(
                        f'job_{job_id}',
                        self.channel_name
                    )
                    await self.send(text_data=json.dumps({
                        'type': 'unsubscribed',
                        'job_id': job_id
                    }))
                    
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing generation message: {e}")
    
    async def job_status_update(self, event):
        """Send job status update to client"""
        await self.send(text_data=json.dumps({
            'type': 'job_status_update',
            'job_id': event['job_id'],
            'status': event['status'],
            'progress': event['progress'],
            'total_tiles': event['total_tiles'],
            'current_tile': event['current_tile'],
            'error_message': event.get('error_message', ''),
            'timestamp': event['timestamp']
        }))
    
    async def job_completed(self, event):
        """Send job completion notification"""
        await self.send(text_data=json.dumps({
            'type': 'job_completed',
            'job_id': event['job_id'],
            'success': event['success'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))


class WorldConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for 3D world updates"""
    
    async def connect(self):
        self.room_group_name = 'world_updates'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"World WebSocket connected: {self.channel_name}")
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"World WebSocket disconnected: {self.channel_name}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'camera_position':
                # Broadcast camera position updates
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'camera_position_message',
                        'position': data.get('position'),
                        'rotation': data.get('rotation'),
                        'user_id': data.get('user_id'),
                        'sender': self.channel_name
                    }
                )
            
            elif message_type == 'object_interaction':
                # Broadcast object interactions
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'object_interaction_message',
                        'object_id': data.get('object_id'),
                        'interaction': data.get('interaction'),
                        'user_id': data.get('user_id'),
                        'timestamp': timezone.now().isoformat(),
                        'sender': self.channel_name
                    }
                )
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing world message: {e}")
    
    async def camera_position_message(self, event):
        # Don't send back to sender
        if event['sender'] != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'camera_position',
                'position': event['position'],
                'rotation': event['rotation'],
                'user_id': event['user_id']
            }))
    
    async def object_interaction_message(self, event):
        # Don't send back to sender
        if event['sender'] != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'object_interaction',
                'object_id': event['object_id'],
                'interaction': event['interaction'],
                'user_id': event['user_id'],
                'timestamp': event['timestamp']
            }))
    
    async def new_object_created(self, event):
        """Send new object creation notification"""
        await self.send(text_data=json.dumps({
            'type': 'new_object_created',
            'object': event['object'],
            'timestamp': event['timestamp']
        }))
    
    async def object_updated(self, event):
        """Send object update notification"""
        await self.send(text_data=json.dumps({
            'type': 'object_updated',
            'object_id': event['object_id'],
            'changes': event['changes'],
            'timestamp': event['timestamp']
        }))
