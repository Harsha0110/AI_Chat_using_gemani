import json
import speech_recognition as sr
from channels.generic.websocket import AsyncWebsocketConsumer
import asyncio
import wave
import io
import google.generativeai as genai
from django.conf import settings

class AudioChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_recording = False
        self.audio_data = []
        self.recognizer = sr.Recognizer()
        # Initialize Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    async def connect(self):
        await self.accept()
        print("WebSocket connected")

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected with code: {close_code}")
        self.is_recording = False

    def save_audio_to_wav(self, audio_data):
        with io.BytesIO() as wav_io:
            with wave.open(wav_io, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b''.join(audio_data))
            return wav_io.getvalue()

    async def get_gemini_response(self, text):
        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                text
            )
            return response.text
        except Exception as e:
            print(f"Gemini API error: {str(e)}")
            return f"Error getting AI response: {str(e)}"

    async def process_audio(self):
        try:
            wav_data = self.save_audio_to_wav(self.audio_data)
            
            with sr.AudioFile(io.BytesIO(wav_data)) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                print(f"Transcribed text: {text}")

                # Send transcribed text to Gemini
                response = await self.get_gemini_response(text)
                
                await self.send(text_data=json.dumps({
                    'type': 'transcription',
                    'text': text,
                    'ai_response': response
                }))

        except sr.UnknownValueError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Could not understand audio'
            }))
        except sr.RequestError as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error with the speech recognition service: {str(e)}'
            }))
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing audio: {str(e)}'
            }))

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            if data.get('type') == 'recording_state':
                if data.get('state') == 'started':
                    self.is_recording = True
                    self.audio_data = []
                elif data.get('state') == 'stopped':
                    self.is_recording = False
                    await self.process_audio()

        elif bytes_data and self.is_recording:
            self.audio_data.append(bytes_data)
            await self.send(text_data=json.dumps({
                'type': 'audio_status',
                'message': 'Audio chunk received'
            }))