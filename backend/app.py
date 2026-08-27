import os
import sqlite3
import json
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from datetime import datetime, timedelta

# Create Flask app
app = Flask(__name__, static_folder="../frontend")
app.config['SECRET_KEY'] = 'networkguardian_secret!'
# Initialize SocketIO with eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

DB_PATH = os.environ.get("METRICS_DB_PATH", "/app/data/metrics.db")

def get_db_connection():
    # Only connect if file exists
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_link_health(conn, link_id):
    """Assess link health based on recent metrics."""
    cursor = conn.cursor()
    # Get the 5 most recent metrics
    cursor.execute('''
        SELECT latency_ms, packet_loss_percent, timestamp
        FROM metrics
        WHERE link_id = ?
        ORDER BY timestamp DESC LIMIT 5
    ''', (link_id,))
    rows = cursor.fetchall()
    
    if not rows:
        return "unknown"
        
    recent_loss = [r['packet_loss_percent'] for r in rows if r['packet_loss_percent'] is not None]
    
    if not recent_loss:
        return "unknown"
        
    avg_loss = sum(recent_loss) / len(recent_loss)
    
    if avg_loss >= 20.0:
        return "down"
    elif avg_loss > 5.0:
        return "degraded"
    else:
        return "healthy"

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/topology', methods=['GET'])
def get_topology():
    conn = get_db_connection()
    if not conn:
        return jsonify({"nodes": [], "links": []})
        
    cursor = conn.cursor()
    # Get all known links
    cursor.execute('SELECT DISTINCT link_id FROM metrics')
    rows = cursor.fetchall()
    
    nodes = set()
    links = []
    
    for row in rows:
        link_id = row['link_id']
        # link_id format is e.g. "h1-s1", "s1-s2"
        parts = link_id.split('-')
        if len(parts) == 2:
            src, dst = parts
            nodes.add(src)
            nodes.add(dst)
            health = get_link_health(conn, link_id)
            links.append({
                "id": link_id,
                "source": src,
                "target": dst,
                "health": health
            })
            
    # Format nodes for D3
    nodes_list = [{"id": node, "type": "switch" if node.startswith("s") else "host"} for node in nodes]
    
    conn.close()
    return jsonify({"nodes": nodes_list, "links": links})

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    # Return recent latency and packet loss for charting
    conn = get_db_connection()
    if not conn:
        return jsonify({})
        
    cursor = conn.cursor()
    
    # Get last 5 minutes of data
    five_mins_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    
    cursor.execute('''
        SELECT link_id, timestamp, latency_ms, packet_loss_percent
        FROM metrics
        WHERE timestamp > ?
        ORDER BY timestamp ASC
    ''', (five_mins_ago,))
    
    rows = cursor.fetchall()
    
    metrics_by_link = {}
    for row in rows:
        link_id = row['link_id']
        if link_id not in metrics_by_link:
            metrics_by_link[link_id] = {"timestamps": [], "latencies": [], "losses": []}
            
        metrics_by_link[link_id]["timestamps"].append(row['timestamp'])
        metrics_by_link[link_id]["latencies"].append(row['latency_ms'] or 0)
        metrics_by_link[link_id]["losses"].append(row['packet_loss_percent'] or 0)
        
    conn.close()
    return jsonify(metrics_by_link)

@app.route('/api/event', methods=['POST'])
def receive_event():
    """Endpoint for agent/controller to post live events to the dashboard."""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400
        
    event_type = data.get("type", "info")
    message = data.get("message", "")
    link_id = data.get("link_id")
    
    # Create event payload
    event_payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": event_type,
        "message": message,
        "link_id": link_id
    }
    
    # Broadcast to all connected WebSocket clients
    socketio.emit('network_event', event_payload)
    
    return jsonify({"status": "broadcasted"}), 200

@socketio.on('connect')
def handle_connect():
    print('Client connected to WebSocket')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected from WebSocket')

if __name__ == '__main__':
    # Run server on port 5000
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
