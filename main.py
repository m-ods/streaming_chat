import asyncio
import json
import websockets
import assemblyai as aai
from typing import Dict
from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import base64
from fastapi.middleware.cors import CORSMiddleware

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize AssemblyAI client
aai.settings.api_key = "523d85f64d974fc0a84bdb53c8a8615d"

class ChatSession:
    def __init__(self, websocket: WebSocket, username: str, chat_room: 'ChatRoom'):
        self.websocket = websocket
        self.username = username
        self.chat_room = chat_room
        self.loop = asyncio.get_event_loop()
        self.assemblyai_ws = None
        
        # Start the AssemblyAI connection
        asyncio.create_task(self.connect_to_assemblyai())

    async def connect_to_assemblyai(self):
        try:
            self.assemblyai_ws = await websockets.connect(
                "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=44100",
                extra_headers={"Authorization": aai.settings.api_key},
                ping_interval=5,
                ping_timeout=20
            )
            
            # Receive the SessionBegins message
            await self.assemblyai_ws.recv()
            logger.info(f"AssemblyAI connection opened for {self.username}")
            
            # Start the receiving task
            asyncio.create_task(self.receive_transcripts())
            
        except Exception as e:
            logger.error(f"Error connecting to AssemblyAI for {self.username}: {e}")

    async def receive_transcripts(self):
        try:
            async for message in self.assemblyai_ws:
                result = json.loads(message)
                if 'text' in result and result['text']:
                    is_final = result.get('message_type', '') == 'FinalTranscript'
                    
                    message = {
                        "type": "final" if is_final else "partial",
                        "username": self.username,
                        "text": result['text']
                    }
                    
                    logger.info(f"[TRANSCRIPT] {self.username}: {result['text']} ({'final' if is_final else 'partial'})")
                    await self.chat_room.broadcast(message)
                    
        except Exception as e:
            logger.error(f"Error receiving transcripts for {self.username}: {e}")

    async def handle_audio(self, audio_data: bytes):
        try:
            if self.assemblyai_ws:
                # Convert audio to base64 and send
                data = base64.b64encode(audio_data).decode("utf-8")
                await self.assemblyai_ws.send(json.dumps({"audio_data": str(data)}))
        except Exception as e:
            logger.error(f"[ERROR] Processing audio from {self.username}: {e}")

    def __del__(self):
        logger.info(f"Cleaning up connection for {self.username}")
        if hasattr(self, 'assemblyai_ws') and self.assemblyai_ws:
            asyncio.create_task(self.assemblyai_ws.close())

class ChatRoom:
    def __init__(self):
        self.sessions: Dict[WebSocket, ChatSession] = {}

    async def register(self, websocket: WebSocket, username: str):
        session = ChatSession(websocket, username, self)
        self.sessions[websocket] = session
        logger.info(f"User {username} joined the chat")

    async def unregister(self, websocket: WebSocket):
        if websocket in self.sessions:
            username = self.sessions[websocket].username
            del self.sessions[websocket]
            logger.info(f"User {username} left the chat")

    async def broadcast(self, message: dict):
        logger.debug(f"Broadcasting message: {message}")
        for session in self.sessions.values():
            try:
                await session.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to {session.username}: {e}")

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your actual domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=0
)

# Initialize templates
templates = Jinja2Templates(directory="static")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Update the index route to use Jinja2 templates
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

chat_room = ChatRoom()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        # Wait for join message
        data = await websocket.receive_json()
        
        if data["type"] == "join":
            await chat_room.register(websocket, data["username"])
            session = chat_room.sessions[websocket]
            
            # Handle audio data
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.receive" and "bytes" in message:
                    await session.handle_audio(message["bytes"])
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await chat_room.unregister(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080) 