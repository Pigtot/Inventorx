"""Browser regression for VR startup. Uses fake XR sessions; never connects to hardware.

Run on the club Windows PC:
    ~/venvs/xarm/Scripts/python.exe -m unittest discover -s code/tests -p test_vr_startup.py -v
"""
import functools
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

VR = Path(__file__).resolve().parents[1] / "vr_teleop"
sys.path.insert(0, str(VR))
import vr_teleop


FAKE_XR = """
<script>
window.xrTest = { requests: 0, nextSession: null, failSetup: false };
Object.defineProperty(navigator, "xr", { value: {
  isSessionSupported: async () => true,
  requestSession: () => {
    xrTest.requests++;
    return xrTest.nextSession ? Promise.resolve(xrTest.nextSession) :
      new Promise((resolve, reject) => { xrTest.reject = reject; });
  },
} });
</script>
"""

CHECKS = """
// These checks run inside the actual page module, so they exercise its real click handler.
(async () => {
  const check = (value, reason) => { if (!value) throw new Error(reason); };
  const fakeSession = () => {
    const session = new EventTarget();
    session.visibilityState = "visible";
    session.ends = 0;
    session.requestAnimationFrame = () => 1;
    session.end = async () => { session.ends++; session.dispatchEvent(new Event("end")); };
    return session;
  };
  try {
    await new Promise(resolve => setTimeout(resolve, 0)); // let the support check enable Enter VR
    check(!vrBtn.disabled, "Support check did not enable Enter VR");
    check(!renderer.capabilities.isWebGL2, "VR must use the WebGL 1 path that passed the headset check");
    check(!renderer.getContext().getContextAttributes().antialias, "VR must match the working test's graphics settings");
    // Draw the actual HUD and scene with real WebGL before substituting fake XR lifecycle methods.
    drawLiveView();
    vr.hudChanged();
    vr.update({ motion: false }, { left: null, right: null }, false);
    renderer.render(vr.scene, eyes);
    check(renderer.getContext().getError() === renderer.getContext().NO_ERROR, "VR scene failed to render with WebGL 1");
    renderer.xr.setSession = async () => {
      if (xrTest.failSetup) throw new Error("graphics setup failed");
    };
    renderer.setAnimationLoop = callback => { xrTest.loop = callback; };
    let pending = vrBtn.onclick();
    check(vrBtn.disabled, "Button must be disabled while session request is pending");
    await vrBtn.onclick();
    check(xrTest.requests === 1, "Repeated clicks started overlapping requests");
    xrTest.reject(new DOMException("Permission refused for test", "NotAllowedError"));
    await pending;
    check(!vrBtn.disabled && !inVR, "Request refusal must allow retry");
    check(msg.textContent.includes("NotAllowedError"), "Request error must be visible");

    xrTest.nextSession = fakeSession();
    await vrBtn.onclick();
    check(inVR && vrBtn.disabled, "Active session must block another start");
    await vrBtn.onclick();
    check(xrTest.requests === 2, "Active session started another request");
    await xrTest.nextSession.end();
    check(!inVR && !vrBtn.disabled && xrTest.loop === null, "Session exit must clear rendering and allow retry");

    xrTest.failSetup = true;
    xrTest.nextSession = fakeSession();
    await vrBtn.onclick();
    check(xrTest.nextSession.ends === 1, "Failed graphics setup must end the allocated session");
    check(!inVR && !vrBtn.disabled, "Failed setup must allow retry");
    check(msg.textContent.includes("graphics setup failed"), "Graphics error must be visible");
    document.body.dataset.vrTest = "PASS";
  } catch (error) {
    document.body.dataset.vrTest = "FAIL: " + error.message;
    console.error(error);
  }
})();
"""


class StartupTests(unittest.TestCase):
    def test_pending_active_refused_and_failed_sessions(self):
        chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
        if not chrome.is_file():
            self.skipTest("Requires Google Chrome on the club Windows PC")
        html = (VR / "index.html").read_text(encoding="utf-8")
        html = html.replace('<script type="module">', FAKE_XR + '<script type="module">', 1)
        html = html.replace("renderer.getContext().makeXRCompatible()", "Promise.resolve()")
        # Keep test timings out of the operator's real debug log.
        html = html.replace('fetch("/log", { method: "POST", body: line }).catch(() => {});', "")
        at = html.rfind("</script>")
        html = (html[:at] + CHECKS + html[at:]).encode("utf-8")

        class TestHandler(vr_teleop.Handler):
            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                else:
                    super().do_GET()

        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(TestHandler, directory=str(VR)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory(prefix="vr-startup-test-") as profile:
                result = subprocess.run([
                    str(chrome), "--headless=new", "--no-first-run", "--no-default-browser-check",
                    "--disable-extensions", "--disable-background-networking", "--disable-component-update",
                    "--disable-sync", "--enable-logging=stderr", "--log-level=0",
                    "--user-data-dir=" + profile, "--dump-dom", "--virtual-time-budget=2000",
                    f"http://127.0.0.1:{server.server_port}/",
                ], capture_output=True, timeout=25)
                dom = result.stdout.decode("utf-8", errors="replace")
                errors = result.stderr.decode("utf-8", errors="replace")
                self.assertEqual(result.returncode, 0, errors[-4000:])
                self.assertTrue('data-vr-test="PASS"' in dom, dom[:3000] + errors[-2000:])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
