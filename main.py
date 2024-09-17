import os
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
os.environ["SPOTIPY_REDIRECT_URI"] = "http://localhost:8080"

# Ollama API endpoint
OLLAMA_API_BASE = "http://localhost:11434"

def setup_spotify():
    scope = "user-read-playback-state,user-modify-playback-state,playlist-read-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
    return sp

def query_ollama(prompt):
    url = f"{OLLAMA_API_BASE}/api/generate"
    data = {
        "model": "llama3.1",
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()['response']
    except requests.RequestException as e:
        print(f"Error querying Ollama: {e}")
        return None

def parse_ollama_response(response):
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end != -1:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass
        print("Failed to parse Ollama response as JSON")
        return None

def get_devices(sp):
    devices = sp.devices()
    return devices['devices']

def categorize_devices(devices):
    categorized = {"phone": [], "laptop": [], "pc": [], "other": []}
    for device in devices:
        if device['type'] == 'Smartphone':
            categorized["phone"].append(device)
        elif device['type'] == 'Computer':
            if 'laptop' in device['name'].lower():
                categorized["laptop"].append(device)
            else:
                categorized["pc"].append(device)
        elif device['type'] == 'Tablet':
            categorized["laptop"].append(device)
        else:
            categorized["other"].append(device)
    return categorized

def find_device_by_category(devices, category):
    categorized = categorize_devices(devices)
    if category in categorized and categorized[category]:
        return categorized[category][0]  # Return the first device in the category
    return None

def list_playlists(sp):
    playlists = sp.current_user_playlists()
    print("Your playlists:")
    for i, playlist in enumerate(playlists['items'], 1):
        print(f"{i}. {playlist['name']}")
    return playlists['items']

def control_spotify(command, current_device_id=None):
    prompt = f"""
    Interpret the following command for Spotify and respond with a JSON object containing 'action' and 'parameters'.
    The command may be in any language, but your response should always be in English.
    Possible actions are: 'play', 'pause', 'next', 'previous', 'volume', 'search', 'list_playlists', 'play_playlist', 'switch_device'.

    Special instructions:
    1. If the command is about skipping or playing the next song, use the 'next' action.
    2. For search queries, and for play and then song name, use the 'search' action and include 'query' and 'type' in parameters.
        - If the command is to play a song by an artist, set type to 'track' and include both song and artist in the query.
    3. For volume changes, use the 'volume' action and include 'level' (0-100) in parameters.
    4. If the command is to resume playback or play without a specific song, use the 'play' action.
    5. For pausing, use the 'pause' action.
    6. If the command is to go back to the previous song, use the 'previous' action.
    7. If the command is to list playlists, use the 'list_playlists' action.
    8. If the command is to play a specific playlist, use the 'play_playlist' action and include the playlist name in the 'name' parameter.
    9. If the command mentions playing on a specific device (e.g., "play on my phone", "spiele auf meinem Handy"), use both the 'switch_device' action and the 'play' action.
        Include the device category ('phone', 'laptop', or 'pc') in the 'device' parameter.

    Examples:
    - "Skip this song" or "Überspringe dieses Lied" should return {{"action": "next"}}
    - "Play Bohemian Rhapsody by Queen" or "Spiele Bohemian Rhapsody von Queen" should return {{"action": "search", "parameters": {{"query": "Bohemian Rhapsody Queen", "type": "track"}}}}
    - "Set volume to 80%" or "Stelle die Lautstärke auf 80%" should return {{"action": "volume", "parameters": {{"level": 80}}}}
    - "Show my playlists" or "Zeige meine Playlists" should return {{"action": "list_playlists"}}
    - "Play my workout playlist" or "Spiele meine Workout-Playlist" should return {{"action": "play_playlist", "parameters": {{"name": "workout"}}}}
    - "Play on my phone" or "Spiele auf meinem Handy" should return {{"action": "switch_device", "parameters": {{"device": "phone"}}, "next_action": "play"}}
    - "Play on my laptop" or "Spiele auf meinem Laptop" should return {{"action": "switch_device", "parameters": {{"device": "laptop"}}, "next_action": "play"}}
    - "Play on my PC" or "Spiele auf meinem PC" should return {{"action": "switch_device", "parameters": {{"device": "pc"}}, "next_action": "play"}}

    Command: {command}
    """

    ollama_response = query_ollama(prompt)
    if ollama_response is None:
        return "Failed to get a response from Ollama"

    result = parse_ollama_response(ollama_response)
    if result is None:
        return "Failed to parse Ollama response"

    print(f"Interpreted command: {result}")

    sp = setup_spotify()
    devices = get_devices(sp)

    action = result.get('action')
    params = result.get('parameters', {})
    next_action = result.get('next_action')

    try:
        if action == 'switch_device':
            device_category = params.get('device', '').lower()
            new_device = find_device_by_category(devices, device_category)
            if new_device:
                current_device_id = new_device['id']
                sp.transfer_playback(device_id=current_device_id)
                print(f"Switched playback to {new_device['name']} ({device_category})")
                if next_action == 'play':
                    sp.start_playback(device_id=current_device_id)
                    return "Playback started on the new device"
            else:
                return f"No {device_category} device found"

        if current_device_id is None:
            active_devices = [d for d in devices if d['is_active']]
            if active_devices:
                current_device_id = active_devices[0]['id']
            else:
                return "No active device found. Please specify a device to play on."

        if action == 'play':
            sp.start_playback(device_id=current_device_id)
        elif action == 'pause':
            sp.pause_playback(device_id=current_device_id)
        elif action == 'next':
            sp.next_track(device_id=current_device_id)
        elif action == 'previous':
            sp.previous_track(device_id=current_device_id)
        elif action == 'volume':
            volume_percent = params.get('level', 50)
            sp.volume(volume_percent, device_id=current_device_id)
        elif action == 'search':
            query = params.get('query', '')
            search_type = params.get('type', 'track')
            results = sp.search(q=query, type=search_type, limit=1)
            if results and results[f'{search_type}s']['items']:
                item = results[f'{search_type}s']['items'][0]
                if search_type == 'track':
                    sp.start_playback(device_id=current_device_id, uris=[item['uri']])
                    return f"Now playing: {item['name']} by {item['artists'][0]['name']}"
                else:
                    sp.start_playback(device_id=current_device_id, context_uri=item['uri'])
                    return f"Now playing: {item['name']}"
            else:
                return f"No results found for '{query}'"
        elif action == 'list_playlists':
            playlists = list_playlists(sp)
            return "Playlists displayed"
        elif action == 'play_playlist':
            playlist_name = params.get('name', '').lower()
            playlists = sp.current_user_playlists()
            for playlist in playlists['items']:
                if playlist_name in playlist['name'].lower():
                    sp.start_playback(device_id=current_device_id, context_uri=playlist['uri'])
                    return f"Now playing playlist: {playlist['name']}"
            return f"Playlist '{playlist_name}' not found"
        else:
            return f"Unknown action: {action}"
    except spotipy.SpotifyException as e:
        if e.http_status == 403 and "Player command failed: Restriction violated" in str(e):
            return "Unable to control playback. This could be due to a non-Premium account or geographical restrictions."
        else:
            return f"Spotify API error: {e}"
    except Exception as e:
        return f"Error performing Spotify action: {e}"

    return f"Command processed successfully: {action}"

def main():
    sp = setup_spotify()
    devices = get_devices(sp)
    categorized_devices = categorize_devices(devices)

    print("Available devices:")
    for category, device_list in categorized_devices.items():
        print(f"\n{category.capitalize()}:")
        for device in device_list:
            print(f"  - {device['name']} ({'Active' if device['is_active'] else 'Inactive'})")

    current_device_id = None
    active_devices = [d for d in devices if d['is_active']]
    if active_devices:
        current_device_id = active_devices[0]['id']
        print(f"\nCurrently active device: {active_devices[0]['name']}")
    else:
        print("\nNo active device found. You can specify a device in your commands.")

    while True:
        command = input("\nEnter a Spotify command (or 'quit' to exit): ")
        if command.lower() == 'quit':
            break
        result = control_spotify(command, current_device_id)
        print(result)

        # Update the current device ID if it was changed
        devices = get_devices(sp)
        active_devices = [d for d in devices if d['is_active']]
        if active_devices:
            current_device_id = active_devices[0]['id']

if __name__ == "__main__":
    main()
