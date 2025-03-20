import asyncio
import json
import ssl
import websockets
import time
import base64
import os

# Create uploads directory
os.makedirs("uploads", exist_ok=True)

# User credentials
USER_DB = {
    "joe": "joe123",
    "bob": "bob123",
    "jim": "jim123",
    "lee": "lee123",
    "eve": "eve123"
}

# Active connections
active_users = {}  # username -> websocket

# Rate limiting
message_timestamps = {}  # username -> list of timestamps
MAX_MESSAGES = 5
WINDOW_SECONDS = 10

async def broadcast(message):
    """Send message to all connected users"""
    data = json.dumps(message)
    for websocket in active_users.values():
        try:
            await websocket.send(data)
        except:
            pass

async def handle_connection(websocket):
    """Handle a client connection"""
    username = None
    
    try:
        # Authentication
        auth_data = await websocket.recv()
        auth = json.loads(auth_data)
        
        if auth.get("type") != "auth":
            await websocket.close()
            return
            
        username = auth.get("username")
        password = auth.get("password")
        
        # Check if already logged in
        if username in active_users:
            await websocket.send(json.dumps({
                "type": "system",
                "message": "User already logged in from another location."
            }))
            await websocket.close()
            return
            
        # Verify credentials
        if username in USER_DB and USER_DB[username] == password:
            # Login successful
            active_users[username] = websocket
            
            # Notify all users
            await broadcast({
                "type": "system",
                "message": f"{username} joined the chat."
            })
            
            # Send user list to new client
            await websocket.send(json.dumps({
                "type": "users_list",
                "users": list(active_users.keys())
            }))
        else:
            # Login failed
            await websocket.send(json.dumps({
                "type": "system",
                "message": "Authentication failed."
            }))
            await websocket.close()
            return
            
        # Message handling loop
        async for message_data in websocket:
            message = json.loads(message_data)
            msg_type = message.get("type")
            
            # Check rate limit for chat and file messages
            if msg_type in ["chat", "file"]:
                # Update timestamps
                now = time.time()
                timestamps = message_timestamps.get(username, [])
                timestamps = [t for t in timestamps if now - t < WINDOW_SECONDS]
                timestamps.append(now)
                message_timestamps[username] = timestamps
                
                # Check if rate limited
                if len(timestamps) > MAX_MESSAGES:
                    await websocket.send(json.dumps({
                        "type": "system",
                        "message": "You are sending messages too quickly. Please wait."
                    }))
                    continue
            
            # Handle message by type
            if msg_type == "chat":
                await broadcast({
                    "type": "chat",
                    "from": username,
                    "message": message.get("message", "")
                })
                
            elif msg_type == "file":
                # Process file upload
                filename = message.get("filename")
                file_data_b64 = message.get("data")
                
                # Decode file data
                file_data = base64.b64decode(file_data_b64)
                
                # Check file size (10MB limit)
                if len(file_data) > 10 * 1024 * 1024:
                    await websocket.send(json.dumps({
                        "type": "system",
                        "message": "File too large. Maximum size is 10MB."
                    }))
                    continue
                
                # Save file
                safe_filename = os.path.basename(filename)
                file_id = f"{int(time.time())}_{safe_filename}"
                file_path = os.path.join("uploads", file_id)
                
                with open(file_path, "wb") as f:
                    f.write(file_data)
                
                # Notify all users
                await broadcast({
                    "type": "file_shared",
                    "from": username,
                    "filename": safe_filename,
                    "file_id": file_id
                })
                
            elif msg_type == "file_request":
                # Process file download request
                file_id = message.get("file_id")
                
                # Security check
                if '..' in file_id or '/' in file_id:
                    await websocket.send(json.dumps({
                        "type": "system",
                        "message": "Invalid file ID."
                    }))
                    continue
                
                file_path = os.path.join("uploads", file_id)
                
                if not os.path.exists(file_path):
                    await websocket.send(json.dumps({
                        "type": "system",
                        "message": "File not found."
                    }))
                    continue
                
                # Read and send file
                with open(file_path, "rb") as f:
                    file_data = f.read()
                
                filename = file_id.split('_', 1)[1] if '_' in file_id else file_id
                
                await websocket.send(json.dumps({
                    "type": "file_data",
                    "filename": filename,
                    "data": base64.b64encode(file_data).decode('utf-8')
                }))
                
            elif msg_type == "heartbeat":
                # Respond to heartbeat
                await websocket.send(json.dumps({
                    "type": "heartbeat_ack",
                    "timestamp": time.time()
                }))
    
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup on disconnect
        if username and username in active_users:
            del active_users[username]
            
            if message_timestamps.get(username):
                del message_timestamps[username]
            
            # Notify users about disconnect
            await broadcast({
                "type": "system",
                "message": f"{username} left the chat."
            })

async def main():
    """Start the server"""
    # Set up SSL
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    
    try:
        ssl_context.load_cert_chain(certfile="server.crt", keyfile="server.key")
    except FileNotFoundError:
        print("SSL certificate files not found.")
        print("Generate them with: openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes")
        return
    
    # Start server
    server = await websockets.serve(
        handle_connection,
        "localhost",
        8765,
        ssl=ssl_context,
        ping_interval=30,
        ping_timeout=10
    )
    
    print("Chat server running at wss://localhost:8765")
    
    # Keep server running
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())