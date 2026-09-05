"""Flask entrypoint detected by Vercel. Business logic is shared with local mode."""
import io
from flask import Flask, request, Response
from server import Handler

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 4_000_000

class WebHandler(Handler):
    def __init__(self):
        self.headers = request.headers
        self.command = request.method
        self.path = request.full_path.rstrip('?')
        self.rfile = io.BytesIO(request.get_data())
        self.client_address = (request.remote_addr or '', 0)
        self.response = None

    def send_response(self, status):
        self.status = status
        self.response_headers = {}
        self.wfile = io.BytesIO()

    def send_header(self, name, value):
        self.response_headers[name] = str(value)

    def end_headers(self):
        pass

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def dispatch(path):
    handler = WebHandler()
    handler.run(request.method == 'POST')
    return Response(handler.wfile.getvalue(), status=handler.status,
                    headers=handler.response_headers)

@app.errorhandler(413)
def too_large(error):
    return {'error': 'คำขอใหญ่เกินกำหนด เลือกภาพไม่เกิน 2.5 MB'}, 413

if __name__ == '__main__':
    from database import initialize
    initialize()
    app.run(host='127.0.0.1', port=8765)
