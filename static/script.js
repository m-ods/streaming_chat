let ws;
let recorder;
let isMuted = false;

document.getElementById('join-btn').addEventListener('click', joinChat);
document.getElementById('start-btn').addEventListener('click', startRecording);

function joinChat() {
    const username = document.getElementById('username').value;
    if (!username) return;

    // Connect to WebSocket server
    ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`);
    
    ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'join', username }));
        document.getElementById('login-container').style.display = 'none';
        document.getElementById('chat-container').style.display = 'block';
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        displayMessage(data);
    };
}

function startRecording() {
    const button = document.getElementById('start-btn');
    
    if (recorder && recorder.state !== 'stopped') {
        // Stop recording
        recorder.stopRecording(() => {
            recorder.stream.getTracks().forEach(track => track.stop());
            recorder = null;
        });
        button.textContent = 'Start Recording';
        console.log("Recorder stopped");
        return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            console.log("Starting recording...");
            recorder = new RecordRTC(stream, {
                type: 'audio',
                mimeType: 'audio/wav',
                recorderType: RecordRTC.StereoAudioRecorder,
                timeSlice: 250,
                desiredSampRate: 44100,
                numberOfAudioChannels: 1,
                bufferSize: 4096,
                audioBitsPerSecond: 128000,
                ondataavailable: async (blob) => {
                    if (ws.readyState === WebSocket.OPEN) {
                        const buffer = await blob.arrayBuffer();
                        ws.send(buffer);
                    }
                },
            });
            
            recorder.stream = stream;
            recorder.startRecording();
            console.log("Recorder started");
            button.textContent = 'Stop Recording';
        })
        .catch(err => console.error('Error accessing microphone:', err));
}

function displayMessage(data) {
    console.log("Received message:", data);
    const messagesDiv = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${data.type}`;
    messageDiv.textContent = `${data.username}: ${data.text}`;
    messageDiv.dataset.user = data.username;

    const existingPartial = messagesDiv.querySelector(`[data-user="${data.username}"].partial`);
    if (existingPartial) {
        existingPartial.remove();
    }
    
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
} 