import asyncio
import json
import ssl
import websockets
import time

#temp userdb
USER_DB = {
    "joe": "joe123",
    "bob": "bob123",
    "jim": "jim123",
    "lee": "lee123",
    "eve": "eve123"
}

#username -> websocket
active_users = {}

#rate limiting
user_message_timestamps = {}

#rate limiting config
MAX_MESSAGES = 5          # max messages within the time window
WINDOW_SECONDS = 10       # in this many seconds

async def rate_limited(username: str) -> bool:
    
    now = time.time()
    timestamps = user_message_timestamps.get(username, [])

    
    timestamps = [t for t in timestamps if (now - t) < WINDOW_SECONDS]
    timestamps.append(now)

    user_message_timestamps[username] = timestamps
    if len(timestamps) > MAX_MESSAGES:
        return True
    return False

async def broadcast_message(message: dict):
    data = json.dumps(message)
    for user_ws in active_users.values():
        await user_ws.send(data)

async def handle_message(username: str, message: dict):
    msg_type = message.get("type")

    #rate limit check
    if await rate_limited(username):
        warning_msg = {
            "type": "system",
            "message": "You are sending messages too quickly. Please wait."
        }
        await active_users[username].send(json.dumps(warning_msg))
        return

    if msg_type == "chat":
        chat_msg = {
            "type": "chat",
            "from": username,
            "message": message.get("message", "")
        }
        await broadcast_message(chat_msg)


    elif msg_type == "heartbeat":
        #heartbeatfunctionality?
        heartbeat_ack = {
            "type": "heartbeat_ack",
            "message": "pong"
        }
        await active_users[username].send(json.dumps(heartbeat_ack))

async def handle_connection(websocket):
    try:
        #first wait for 'auth' message
        auth_data = await websocket.recv()
        auth_msg = json.loads(auth_data)
        if auth_msg.get("type") != "auth":
            raise ValueError("Invalid authentication message")

        username = auth_msg.get("username")
        password = auth_msg.get("password")

        # authenticate
        if username in USER_DB and USER_DB[username] == password:
            # Successfully authenticated
            active_users[username] = websocket
            join_msg = {
                "type": "system",
                "message": f"{username} joined the chat."
            }
            await broadcast_message(join_msg)
        else:
            # Authentication failed
            error_msg = {
                "type": "system",
                "message": "Authentication failed."
            }
            await websocket.send(json.dumps(error_msg))
            await websocket.close()
            return

        # second listen for messages
        async for msg in websocket:
            data = json.loads(msg)
            await handle_message(username, data)

    except websockets.exceptions.ConnectionClosed:
        pass  #client disconnected
    except Exception as e:
        print(f"General exception: {e}")
    finally:
        # Remove from active users
        if 'username' in locals() and username in active_users:
            del active_users[username]
            leave_msg = {
                "type": "system",
                "message": f"{username} left the chat."
            }
            await broadcast_message(leave_msg)

async def main():
    #create SSL (wss)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    server = await websockets.serve(handle_connection, "localhost", 8765, ssl=ssl_context) 
    
    print("Listening at wss://localhost:8765")
    print("Waiting for clients to connect...")

    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
