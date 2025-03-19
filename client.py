import asyncio
import json
import ssl
import websockets
import os
import threading

SERVER_URL = "wss://localhost:8765"

async def authenticate(websocket, username, password):
    #send auth (handshake)
    auth_msg = json.dumps({"type": "auth", "username": username, "password": password})
    await websocket.send(auth_msg)
    response = await websocket.recv()
    response_data = json.loads(response)

    if response_data.get("type") == "system" and "Authentication failed" in response_data.get("message", ""):
        print("Authentication failed. Exiting...")
        return False
    print("Authentication successful. Welcome to the chat!")
    return True

async def send_message(websocket, username):
    #user msgs
    loop = asyncio.get_running_loop()
    
    while True:
        message = await loop.run_in_executor(None, input, "Enter message or/exit to leave): ")

        if message.lower() == "/exit":
            print("Exiting chat" )
            await websocket.close()
            break
        else:
            chat_msg = {"type": "chat", "message": message}
            await websocket.send(json.dumps(chat_msg))

async def receive_messages(websocket):
    try:
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "chat":
                print(f"\n {data['from']}: {data['message']}")
            elif data["type"] == "system":
                print(f"\n {data['message']}")
            elif data["type"] == "heartbeat_ack":
                print("Server heartbeat")
    except websockets.exceptions.ConnectionClosed:
        print("Connection lost.")
        await reconnect()

async def send_heartbeat(websocket):
    while True:
        try:
            await asyncio.sleep(5)
            await websocket.send(json.dumps({"type": "heartbeat"}))
        except websockets.exceptions.ConnectionClosed:
            print("Connection lost. Attempting to reconnect...")
            await reconnect()
            break

async def reconnect():
    while True:
        try:
            await asyncio.sleep(3)
            print("Reconnecting...")
            await main()
            break
        except:
            print("Reconnection failed, retrying...")

async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations("server.crt")  

    async with websockets.connect(SERVER_URL, ssl=ssl_context) as websocket:
        username = input("Enter username: ")
        password = input("Enter password: ")

        if not await authenticate(websocket, username, password):
            return
        
        
        receive_task = asyncio.create_task(receive_messages(websocket))
        send_task = asyncio.create_task(send_message(websocket, username))
        heartbeat_task = asyncio.create_task(send_heartbeat(websocket))

        await asyncio.gather(receive_task, send_task, heartbeat_task)

if __name__ == "__main__":
    asyncio.run(main())