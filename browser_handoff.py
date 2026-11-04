"""
Interactive Browser Handoff Engine for Pico (Hand #2).
Enables human-in-the-loop web logins with real-time mobile touch/type takeover
and persistent session cookie storage (~/.pico/sessions).
"""

import os
import sys
import time
import json
import asyncio
import logging
import subprocess
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import aiohttp
from aiohttp import web

logger = logging.getLogger("pico.browser_handoff")


# =====================================================================
# 1. SESSION VAULT (Cookie & Storage Persistence)
# =====================================================================

class SessionVault:
    """Manages saved authentication cookies and sessions across visits."""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.expanduser("~/.pico/sessions")
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, domain: str) -> str:
        clean = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
        # remove leading dots or www.
        if clean.startswith("www."):
            clean = clean[4:]
        clean = clean.strip(".").replace(":", "_")
        return os.path.join(self.storage_dir, f"{clean}.json")

    def save_session(self, domain: str, cookies: List[Dict[str, Any]], current_url: str = "") -> str:
        filepath = self._get_path(domain)
        payload = {
            "domain": domain,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "last_url": current_url,
            "cookie_count": len(cookies),
            "cookies": cookies
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Saved {len(cookies)} cookies for {domain} -> {filepath}")
        return filepath

    def load_session(self, domain: str) -> List[Dict[str, Any]]:
        filepath = self._get_path(domain)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                return data.get("cookies", [])
        except Exception as e:
            logger.error(f"Failed to load cookies from {filepath}: {e}")
            return []

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        sessions = {}
        if not os.path.exists(self.storage_dir):
            return sessions
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        data = json.load(f)
                        domain = data.get("domain", fname[:-5])
                        sessions[domain] = {
                            "domain": domain,
                            "cookie_count": data.get("cookie_count", len(data.get("cookies", []))),
                            "saved_at": data.get("saved_at", "unknown"),
                            "last_url": data.get("last_url", "")
                        }
                except Exception:
                    pass
        return sessions

    def delete_session(self, domain: str) -> bool:
        fpath = self._get_path(domain)
        if os.path.exists(fpath):
            os.remove(fpath)
            return True
        return False


# =====================================================================
# 2. CHROME DEVTOOLS PROTOCOL (CDP) CLIENT
# =====================================================================

class CDPClient:
    """Async client communicating with Chromium via Chrome DevTools Protocol."""

    def __init__(self, cdp_http_url: str = "http://127.0.0.1:9222"):
        self.cdp_http_url = cdp_http_url
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._req_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._active_tab_ws: Optional[str] = None
        self.current_url: str = ""
        self.current_title: str = ""

    async def connect(self) -> bool:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        try:
            async with self._session.get(f"{self.cdp_http_url}/json/list", timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status != 200:
                    return False
                tabs = await resp.json()
                if not tabs:
                    # Create a new tab if none exist
                    async with self._session.put(f"{self.cdp_http_url}/json/new?about:blank") as nresp:
                        tab = await nresp.json()
                        self._active_tab_ws = tab.get("webSocketDebuggerUrl")
                else:
                    self._active_tab_ws = tabs[0].get("webSocketDebuggerUrl")

            if self._active_tab_ws:
                self._ws = await self._session.ws_connect(self._active_tab_ws)
                if self._reader_task and not self._reader_task.done():
                    self._reader_task.cancel()
                self._reader_task = asyncio.create_task(self._reader_loop())
                return True
        except Exception as e:
            logger.warning(f"CDP connection attempt failed: {e}")
        return False

    async def _reader_loop(self):
        try:
            while self._ws and not self._ws.closed:
                msg = await self._ws.receive_json()
                req_id = msg.get("id")
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"CDP reader loop closed: {e}")

    async def send_command(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
        if not self._ws or self._ws.closed:
            connected = await self.connect()
            if not connected:
                return {"error": "Could not connect to CDP WebSocket"}

        self._req_id += 1
        msg_id = self._req_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[msg_id] = fut

        try:
            await self._ws.send_json(payload)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            return {"error": f"Timeout waiting for CDP response for {method}"}
        except Exception as e:
            self._pending.pop(msg_id, None)
            logger.warning(f"CDP command {method} failed: {e}")
            return {"error": str(e)}

    async def navigate(self, url: str) -> bool:
        res = await self.send_command("Page.navigate", {"url": url})
        self.current_url = url
        await asyncio.sleep(1.0)
        return "error" not in res

    async def capture_screenshot(self, format: str = "jpeg", quality: int = 70) -> Optional[bytes]:
        import base64
        res = await self.send_command("Page.captureScreenshot", {"format": format, "quality": quality})
        data = res.get("result", {}).get("data")
        if data:
            return base64.b64decode(data)
        return None

    async def get_cookies(self) -> List[Dict[str, Any]]:
        res = await self.send_command("Network.getCookies", {})
        return res.get("result", {}).get("cookies", [])

    async def set_cookies(self, cookies: List[Dict[str, Any]]) -> bool:
        if not cookies:
            return False
        res = await self.send_command("Network.setCookies", {"cookies": cookies})
        return "error" not in res

    async def dispatch_mouse_click(self, x: float, y: float, button: str = "left") -> bool:
        await self.send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": int(x),
            "y": int(y),
            "button": button,
            "clickCount": 1
        })
        await self.send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": int(x),
            "y": int(y),
            "button": button
        })
        return True

    async def dispatch_mouse_wheel(self, x: float, y: float, delta_x: float, delta_y: float) -> bool:
        await self.send_command("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": int(x),
            "y": int(y),
            "deltaX": int(delta_x),
            "deltaY": int(delta_y)
        })
        return True

    async def dispatch_key(self, text: str) -> bool:
        for char in text:
            await self.send_command("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char,
                "unmodifiedText": char
            })
            await self.send_command("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "text": char,
                "unmodifiedText": char
            })
        return True

    async def dispatch_special_key(self, key_name: str) -> bool:
        key_map = {
            "enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            "backspace": {"key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
            "tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
            "escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
            "space": {"key": " ", "code": "Space", "windowsVirtualKeyCode": 32},
        }
        km = key_map.get(key_name.lower())
        if not km:
            return False
        await self.send_command("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "key": km["key"],
            "code": km["code"],
            "windowsVirtualKeyCode": km["windowsVirtualKeyCode"]
        })
        await self.send_command("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": km["key"],
            "code": km["code"],
            "windowsVirtualKeyCode": km["windowsVirtualKeyCode"]
        })
        return True

    async def close(self):
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()


# =====================================================================
# 3. INTERACTIVE MOBILE TAKEOVER WEB INTERFACE
# =====================================================================

TAKEOVER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Pico Cloud Browser Takeover 🎮</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
    body {
      background: #0f172a;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }
    header {
      background: #1e293b;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #334155;
      gap: 10px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      font-size: 15px;
      color: #38bdf8;
    }
    .url-bar {
      flex: 1;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      color: #94a3b8;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .btn-done {
      background: #10b981;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 8px 14px;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 5px;
      box-shadow: 0 2px 8px rgba(16, 185, 129, 0.4);
    }
    .btn-done:active { transform: scale(0.97); }
    #viewport-container {
      flex: 1;
      position: relative;
      background: #000;
      overflow: auto;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #browser-screen {
      max-width: 100%;
      max-height: 100%;
      display: block;
      cursor: crosshair;
      object-fit: contain;
    }
    #floating-keyboard-bar {
      background: #1e293b;
      padding: 8px 12px;
      display: flex;
      gap: 8px;
      border-top: 1px solid #334155;
      align-items: center;
    }
    .key-input {
      flex: 1;
      background: #0f172a;
      border: 1px solid #475569;
      color: white;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 14px;
    }
    .key-btn {
      background: #3b82f6;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 8px 12px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
    }
    .quick-key {
      background: #334155;
      color: #e2e8f0;
      border: none;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }
    #status-toast {
      position: absolute;
      top: 60px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid #38bdf8;
      color: #38bdf8;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.3s;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">🌟 Pico</div>
    <div class="url-bar" id="url-display">Loading browser...</div>
    <button class="btn-done" id="btn-takeover">🚀 Pico, Take Over!</button>
  </header>

  <div id="viewport-container">
    <div id="status-toast">Screen active</div>
    <img id="browser-screen" alt="Live Browser Screencast" />
  </div>

  <div id="floating-keyboard-bar">
    <input type="text" id="text-input" class="key-input" placeholder="Type text, username, password..." autocomplete="off" />
    <button class="key-btn" id="btn-send">Send</button>
    <button class="quick-key" id="btn-tab">⇥ Tab</button>
    <button class="quick-key" id="btn-enter">↵ Enter</button>
    <button class="quick-key" id="btn-backspace">⌫ Del</button>
  </div>

  <script>
    const img = document.getElementById('browser-screen');
    const toast = document.getElementById('status-toast');
    const urlDisplay = document.getElementById('url-display');
    const textInput = document.getElementById('text-input');

    function showToast(text, duration = 1500) {
      toast.innerText = text;
      toast.style.opacity = '1';
      setTimeout(() => { toast.style.opacity = '0'; }, duration);
    }

    // Connect WebSocket
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProto}//${window.location.host}/ws/stream`);

    ws.onopen = () => {
      showToast('🟢 Connected to Pico Browser!');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'frame') {
          img.src = 'data:image/jpeg;base64,' + msg.data;
          if (msg.url) urlDisplay.innerText = msg.url;
        } else if (msg.type === 'done_ack') {
          showToast('🎉 Done! Pico has captured the session cookies!', 4000);
          setTimeout(() => {
            alert('Session saved successfully! You can switch back to Telegram.');
          }, 500);
        }
      } catch (e) {
        console.error(e);
      }
    };

    // Handle touch/click on the browser image
    img.addEventListener('click', (e) => {
      const rect = img.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      // Map to 1280x800 Chromium viewport
      const targetWidth = 1280;
      const targetHeight = 800;
      const scaleX = targetWidth / rect.width;
      const scaleY = targetHeight / rect.height;

      const x = Math.round(clickX * scaleX);
      const y = Math.round(clickY * scaleY);

      ws.send(JSON.stringify({ type: 'click', x: x, y: y }));
      showToast(`Tapped (${x}, ${y})`, 500);
      textInput.focus();
    });

    // Send typing
    function sendText() {
      const val = textInput.value;
      if (val) {
        ws.send(JSON.stringify({ type: 'type', text: val }));
        textInput.value = '';
        showToast('Sent text! ⌨️', 600);
      }
    }

    document.getElementById('btn-send').addEventListener('click', sendText);
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        sendText();
      }
    });

    document.getElementById('btn-tab').addEventListener('click', () => {
      ws.send(JSON.stringify({ type: 'special_key', key: 'tab' }));
    });
    document.getElementById('btn-enter').addEventListener('click', () => {
      ws.send(JSON.stringify({ type: 'special_key', key: 'enter' }));
    });
    document.getElementById('btn-backspace').addEventListener('click', () => {
      ws.send(JSON.stringify({ type: 'special_key', key: 'backspace' }));
    });

    // Takeover Done Button
    document.getElementById('btn-takeover').addEventListener('click', () => {
      ws.send(JSON.stringify({ type: 'done' }));
    });
  </script>
</body>
</html>
"""


# =====================================================================
# 4. BROWSER HANDOFF ENGINE
# =====================================================================

class BrowserHandoffEngine:
    """
    Coordinates headless Chromium, CDP live screencast,
    the mobile web takeover server, and session persistence.
    """

    def __init__(self, cdp_port: int = 9222, web_port: int = 8765):
        self.cdp_port = cdp_port
        self.web_port = web_port
        self.vault = SessionVault()
        self.cdp = CDPClient(f"http://127.0.0.1:{cdp_port}")
        self.chromium_proc: Optional[subprocess.Popen] = None
        self.web_app: Optional[web.Application] = None
        self.web_runner: Optional[web.AppRunner] = None
        self.active_ws_clients: List[web.WebSocketResponse] = []
        self.is_streaming = False
        self.stream_task: Optional[asyncio.Task] = None
        self.on_handoff_complete_callback = None
        self.current_domain: str = ""
        self.current_url: str = ""

    def ensure_chromium_running(self) -> bool:
        """Starts Chromium with remote debugging if not already alive."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = (s.connect_ex(("127.0.0.1", self.cdp_port)) == 0)

        if in_use:
            return True

        profile_dir = os.path.expanduser("~/.pico/browser_profile")
        os.makedirs(profile_dir, exist_ok=True)

        cmd = [
            "chromium-browser",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--password-store=basic",
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            f"--remote-debugging-port={self.cdp_port}",
            "--window-size=1280,800",
            f"--user-data-dir={profile_dir}",
            "about:blank"
        ]

        try:
            self.chromium_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.5)
            logger.info(f"Spawned Chromium (PID {self.chromium_proc.pid}) on port {self.cdp_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to launch Chromium: {e}")
            return False

    async def start_web_server(self):
        """Starts the mobile-friendly web handoff server."""
        if self.web_runner:
            return

        app = web.Application()
        app.router.add_get("/takeover", self._handle_takeover_page)
        async def _favicon(r): return web.Response(status=204)
        app.router.add_get("/favicon.ico", _favicon)
        app.router.add_get("/screenshot", self._handle_screenshot_get)
        app.router.add_post("/api/action", self._handle_action_post)
        app.router.add_get("/ws/stream", self._handle_ws_stream)

        self.web_app = app
        self.web_runner = web.AppRunner(app)
        await self.web_runner.setup()
        site = web.TCPSite(self.web_runner, "0.0.0.0", self.web_port)
        await site.start()
        logger.info(f"Browser Handoff Web Server live at http://0.0.0.0:{self.web_port}/takeover")

    async def _handle_takeover_page(self, request):
        return web.Response(text=TAKEOVER_HTML, content_type="text/html")

    async def _handle_screenshot_get(self, request):
        bytes_data = await self.cdp.capture_screenshot()
        if bytes_data:
            return web.Response(body=bytes_data, content_type="image/jpeg")
        return web.Response(status=500, text="Failed to capture screenshot")

    async def _handle_action_post(self, request):
        data = await request.json()
        action = data.get("action")
        if action == "click":
            await self.cdp.dispatch_mouse_click(data.get("x", 0), data.get("y", 0))
        elif action == "type":
            await self.cdp.dispatch_key(data.get("text", ""))
        elif action == "done":
            await self.finalize_session()
        return web.json_response({"status": "ok"})

    async def _handle_ws_stream(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.active_ws_clients.append(ws)

        if not self.is_streaming:
            self.is_streaming = True
            self.stream_task = asyncio.create_task(self._stream_screencast_loop())

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    mtype = data.get("type")
                    if mtype == "click":
                        await self.cdp.dispatch_mouse_click(data.get("x", 0), data.get("y", 0))
                    elif mtype == "type":
                        await self.cdp.dispatch_key(data.get("text", ""))
                    elif mtype == "special_key":
                        await self.cdp.dispatch_special_key(data.get("key", ""))
                    elif mtype == "done":
                        res = await self.finalize_session()
                        await ws.send_json({"type": "done_ack", "result": res})
        finally:
            if ws in self.active_ws_clients:
                self.active_ws_clients.remove(ws)
            if not self.active_ws_clients and self.stream_task:
                self.is_streaming = False
                self.stream_task.cancel()

        return ws

    async def _stream_screencast_loop(self):
        """Continuously captures frames and pushes to connected mobile viewers."""
        import base64
        while self.is_streaming:
            if self.active_ws_clients:
                try:
                    raw_bytes = await self.cdp.capture_screenshot(format="jpeg", quality=60)
                    if raw_bytes:
                        b64 = base64.b64encode(raw_bytes).decode("ascii")
                        frame_msg = json.dumps({
                            "type": "frame",
                            "data": b64,
                            "url": self.current_url or self.current_domain
                        })
                        for ws in list(self.active_ws_clients):
                            if not ws.closed:
                                await ws.send_str(frame_msg)
                except Exception as e:
                    logger.debug(f"Frame capture glitch: {e}")
            await asyncio.sleep(0.4)

    async def start_takeover(self, url: str) -> Dict[str, Any]:
        """
        Navigates to the website, restores any existing cookies,
        and prepares the takeover link for the user.
        """
        self.ensure_chromium_running()
        await self.start_web_server()

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        self.current_domain = domain
        self.current_url = url

        await self.cdp.connect()

        # Restore existing cookies if we have them
        saved_cookies = self.vault.load_session(domain)
        if saved_cookies:
            await self.cdp.set_cookies(saved_cookies)
            logger.info(f"Pre-loaded {len(saved_cookies)} cookies for {domain}")

        await self.cdp.navigate(url)
        await asyncio.sleep(2.0)

        # Initial screenshot
        initial_ss = await self.cdp.capture_screenshot()

        takeover_url = f"http://localhost:{self.web_port}/takeover"
        return {
            "success": True,
            "url": url,
            "domain": domain,
            "takeover_url": takeover_url,
            "screenshot_bytes": initial_ss,
            "preloaded_cookies": len(saved_cookies)
        }

    async def finalize_session(self) -> Dict[str, Any]:
        """Extracts and saves cookies after user finishes logging in."""
        cookies = await self.cdp.get_cookies()
        domain = self.current_domain or "session"
        saved_path = self.vault.save_session(domain, cookies, self.current_url)

        res = {
            "domain": domain,
            "cookie_count": len(cookies),
            "saved_path": saved_path,
            "status": "authenticated"
        }

        if self.on_handoff_complete_callback:
            try:
                await self.on_handoff_complete_callback(res)
            except Exception as e:
                logger.error(f"Handoff callback failed: {e}")

        return res

    async def capture_current_screenshot(self) -> Optional[bytes]:
        return await self.cdp.capture_screenshot()

    async def cleanup(self):
        self.is_streaming = False
        if self.stream_task:
            self.stream_task.cancel()
        for ws in list(self.active_ws_clients):
            if not ws.closed:
                await ws.close()
        await self.cdp.close()
        if self.web_runner:
            await self.web_runner.cleanup()
            self.web_runner = None
        self.close()

    def close(self):
        if self.chromium_proc:
            try:
                self.chromium_proc.terminate()
            except Exception:
                pass
