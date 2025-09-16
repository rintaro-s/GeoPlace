"""Flask server (minimal skeleton)

提供されているエンドポイントの最小実装を含みます。
"""
from flask import Flask, request, jsonify
import uuid

app = Flask(__name__)

# In-memory job store (demo)
JOBS = {}

@app.route('/api/paint', methods=['POST'])
def paint():
    payload = request.get_json()
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {'status': 'queued', 'payload': payload}
    # 本番では Redis / RQ などに enqueue
    return jsonify({'job_id': job_id}), 202

@app.route('/api/status/<job_id>', methods=['GET'])
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'job_id': job_id, 'status': job['status']})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
