import asyncio
import json
import ssl
import websockets
import os
import base64
import signal

SERVER_URL = "wss://localhost:8765"
HEARTBEAT_INTERVAL = 10  # seconds

# Create downloads directory
os.makedirs("downloads", exist_ok=True)

async def main():
    # Setup
    shutdown_event = asyncio.Event()
    
    # Handle Ctrl+C
    def signal_handler():
        print("\nExiting chat...")
        shutdown_event.set()
    
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    except:
        pass
    
    # Clear screen and show welcome message
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=== Team Chat Client ===")
    print("Commands: /help, /exit, /users, /file <path>, /download <file_id>, /clear")
    
    # Get credentials
    username = input("Username: ")
    password = input("Password: ")
    
    # Set up SSL
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if not os.path.exists("server.crt"):
        print("Server certificate not found. Generate with:")
        print("openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes")
        return
    
    ssl_context.load_verify_locations("server.crt")
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        # Connect to server
        async with websockets.connect(
            SERVER_URL,
            ssl=ssl_context,
            ping_interval=None
        ) as websocket:
            # Authenticate
            await websocket.send(json.dumps({
                "type": "auth", 
                "username": username, 
                "password": password
            }))
            
            response = await websocket.recv()
            auth_response = json.loads(response)
            
            if auth_response.get("type") == "system" and "Authentication failed" in auth_response.get("message", ""):
                print("Authentication failed.")
                return
            
            print("Connected! Start chatting...")
            
            # Define message handler
            async def handle_messages():
                async for message in websocket:
                    if shutdown_event.is_set():
                        break
                    
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "chat":
                        print(f"\n[{data['from']}] {data['message']}")
                    
                    elif msg_type == "system":
                        print(f"\n[SYSTEM] {data['message']}")
                    
                    elif msg_type == "users_list":
                        users = data.get("users", [])
                        print(f"\nOnline users: {', '.join(users)}")
                    
                    elif msg_type == "file_shared":
                        sender = data.get("from", "Unknown")
                        filename = data.get("filename", "Unknown")
                        file_id = data.get("file_id", "")
                        print(f"\n[FILE] {sender} shared: {filename}")
                        print(f"       To download: /download {file_id}")
                    
                    elif msg_type == "file_data":
                        filename = data.get("filename", "file")
                        file_data = base64.b64decode(data.get("data", ""))
                        
                        file_path = os.path.join("downloads", filename)
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                        
                        print(f"\nDownloaded: {file_path}")
                    
                    print("> ", end="", flush=True)
            
            # Define heartbeat sender
            async def send_heartbeats():
                while not shutdown_event.is_set():
                    try:
                        await asyncio.sleep(HEARTBEAT_INTERVAL)
                        await websocket.send(json.dumps({"type": "heartbeat"}))
                    except:
                        break
            
            # Define input handler
            async def handle_input():
                active_users = []
                
                while not shutdown_event.is_set():
                    message = await loop.run_in_executor(None, input, "\n> ")
                    
                    if message.startswith("/"):
                        cmd = message.split(" ", 1)
                        command = cmd[0].lower()
                        
                        if command == "/exit":
                            shutdown_event.set()
                            break
                            
                        elif command == "/help":
                            print("\nCommands:")
                            print("  /help - Show this help")
                            print("  /exit - Exit the chat")
                            print("  /users - Show active users")
                            print("  /file <path> - Send a file")
                            print("  /download <file_id> - Download a file")
                            print("  /clear - Clear the screen")
                            continue
                            
                        elif command == "/users":
                            print("\nActive users:")
                            for user in active_users:
                                print(f"  {user}")
                            continue
                            
                        elif command == "/file":
                            if len(cmd) < 2:
                                print("Usage: /file <path>")
                                continue
                                
                            file_path = cmd[1].strip()
                            
                            if not os.path.exists(file_path):
                                print(f"File not found: {file_path}")
                                continue
                                
                            if os.path.getsize(file_path) > 10 * 1024 * 1024:
                                print("File too large (max 10MB)")
                                continue
                                
                            with open(file_path, "rb") as f:
                                file_data = f.read()
                            
                            await websocket.send(json.dumps({
                                "type": "file",
                                "filename": os.path.basename(file_path),
                                "data": base64.b64encode(file_data).decode('utf-8')
                            }))
                            
                            print(f"Sending file: {os.path.basename(file_path)}...")
                            continue
                            
                        elif command == "/download":
                            if len(cmd) < 2:
                                print("Usage: /download <file_id>")
                                continue
                                
                            file_id = cmd[1].strip()
                            await websocket.send(json.dumps({
                                "type": "file_request",
                                "file_id": file_id
                            }))
                            
                            print(f"Requesting file: {file_id}...")
                            continue
                            
                        elif command == "/clear":
                            os.system('cls' if os.name == 'nt' else 'clear')
                            continue
                            
                        else:
                            print(f"Unknown command: {command}")
                            continue
                    
                    # Regular chat message
                    await websocket.send(json.dumps({
                        "type": "chat",
                        "message": message
                    }))
            
            # Start tasks
            tasks = [
                asyncio.create_task(handle_messages()),
                asyncio.create_task(send_heartbeats()),
                asyncio.create_task(handle_input())
            ]
            
            # Wait for shutdown
            await shutdown_event.wait()
            
            # Cancel tasks
            for task in tasks:
                task.cancel()
            
    except Exception as e:
        print(f"Error: {e}")
    
    print("Disconnected")

if __name__ == "__main__":
    asyncio.run(main())