import urllib.request
import urllib.parse
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    expected_state = None
    
    def do_GET(self):
        # Extract the query parameters
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if 'code' in query_params:
            # Verify CSRF state parameter before accepting the code
            received_state = query_params.get('state', [None])[0]
            if received_state != OAuthCallbackHandler.expected_state:
                self.send_response(403)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"State mismatch - possible CSRF attack. Authentication rejected.")
                return
            OAuthCallbackHandler.auth_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            success_html = """
            <html>
            <head><title>Authentication Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #4CAF50;">Authentication Successful!</h1>
                <p>The backup tool has successfully retrieved your credentials.</p>
                <p>You can safely close this browser window and return to your terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authorization code not found in request.")

    def log_message(self, format, *args):
        # Suppress standard HTTP server logging
        pass

def run_local_auth_flow(client_id: str, client_secret: str, port: int = 8080) -> str:
    """
    Spins up a local HTTP server, launches a browser to standard Google OAuth,
    catches the redirect, and exchanges the authorization code for a permanent refresh_token.
    """
    redirect_uri = f"http://localhost:{port}/"
    
    # Generate a cryptographic state token to prevent CSRF attacks
    csrf_state = secrets.token_urlsafe(32)
    
    # 1. Start the HTTP server bound to loopback ONLY (not 0.0.0.0)
    server_address = ('127.0.0.1', port)
    from socket import error as SocketError
    try:
        httpd = HTTPServer(server_address, OAuthCallbackHandler)
    except SocketError as e:
        raise Exception(f"Failed to securely bind to port {port}. Is another application blocking it? Try using the --port flag. Error: {e}")
        
    OAuthCallbackHandler.auth_code = None
    OAuthCallbackHandler.expected_state = csrf_state
    
    server_thread = threading.Thread(target=httpd.handle_request)
    server_thread.daemon = True
    server_thread.start()
    
    # 2. Build the exact authentication URL requested by Google
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        "response_type=code&"
        "scope=https://www.googleapis.com/auth/drive&"
        "access_type=offline&"
        "prompt=consent&"
        f"state={csrf_state}"
    )
    
    print("\n" + "="*60)
    print("Launching Browser for Authentication...")
    print("If your browser does not open automatically, copy this URL:")
    print(auth_url)
    print("="*60 + "\n")
    
    webbrowser.open(auth_url)
    
    # Wait for the HTTP server to catch the callback
    print(f"Waiting for authorization callback on localhost:{port}...")
    server_thread.join(timeout=300) # 5 minute timeout
    
    if not OAuthCallbackHandler.auth_code:
        raise Exception("Authentication timed out or was cancelled.")
        
    print("Code intercepted successfully! Exchanging for Refresh Token...")
    
    # 3. Exchange the short-lived code for a permanent refresh token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = urllib.parse.urlencode({
        "code": OAuthCallbackHandler.auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }).encode("utf-8")
    
    req = urllib.request.Request(token_url, data=token_data, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            token_info = json.loads(response.read().decode('utf-8'))
            refresh_token = token_info.get("refresh_token")
            if not refresh_token:
                raise Exception("Google responded to the token exchange but no refresh_token was provided. You may need to revoke the app permissions and try again.")
            return refresh_token
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        raise Exception(f"Token exchange failed with HTTP {e.code}: {err_body}")
