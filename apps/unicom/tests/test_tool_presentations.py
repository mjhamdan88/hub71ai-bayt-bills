from django.test import SimpleTestCase

from unicom.services.tool_presentations import extract_tool_presentation


class ToolPresentationTests(SimpleTestCase):
    def test_explicit_image_presentation_is_extracted(self):
        raw = {"tool_response": {"result": {"status": "SUCCESS", "result": '{"result":"Image inspected","_unicom_presentation":{"type":"image","url":"data:image/png;base64,AAAA","alt":"Preview","caption":"/photo.png"}}'}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "image", "url": "data:image/png;base64,AAAA",
            "alt": "Preview", "caption": "/photo.png",
        })

    def test_responses_image_block_supports_historical_results(self):
        raw = {"tool_response": {"result": {"result": '{"path":"/old.png","_responses_content":[{"type":"input_image","image_url":"data:image/png;base64,OLD"}]}'}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "image", "url": "data:image/png;base64,OLD",
            "alt": "Tool image", "caption": "/old.png",
        })

    def test_unsafe_image_url_is_rejected(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {"type": "image", "url": "javascript:alert(1)"}}}}
        self.assertIsNone(extract_tool_presentation(raw))

    def test_inline_svg_is_rejected(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {"type": "image", "url": "data:image/svg+xml,<svg onload=alert(1)>"}}}}
        self.assertIsNone(extract_tool_presentation(raw))

    def test_browser_gallery_is_bounded_and_validated(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {
            "type": "gallery", "images": [
                {"url": "data:image/jpeg;base64,ONE", "caption": "Step 1"},
                {"url": "javascript:alert(1)"},
            ],
        }}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "gallery", "images": [{
                "url": "data:image/jpeg;base64,ONE", "alt": "Browser screenshot", "caption": "Step 1",
            }],
        })

    def test_device_video_descriptor_has_no_direct_untrusted_url(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {
            "type": "video", "device_id": 12, "source_path": "/home/me/run.webm",
            "poster": "data:image/jpeg;base64,POSTER", "caption": "Run",
        }}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "video", "device_id": 12, "source_path": "/home/me/run.webm",
            "poster": "data:image/jpeg;base64,POSTER", "caption": "Run",
        })

    def test_video_rejects_relative_device_path(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {
            "type": "video", "device_id": 12, "source_path": "run.webm",
        }}}}
        self.assertIsNone(extract_tool_presentation(raw))

    def test_public_links_are_bounded_and_require_https(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {
            "type": "public_links", "links": [
                {"url": "https://app.example.test", "label": "Open port 80", "port": 80},
                {"url": "javascript:alert(1)", "label": "Unsafe"},
            ],
        }}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "public_links",
            "links": [{
                "url": "https://app.example.test", "label": "Open port 80", "port": 80,
            }],
        })

    def test_terminal_presentation_is_bounded(self):
        raw = {"tool_response": {"result": {"_unicom_presentation": {
            "type": "terminal", "command": "npm test", "exit_code": 0,
            "stdout": "passed", "stderr": "", "duration_seconds": 2.5,
        }}}}
        self.assertEqual(extract_tool_presentation(raw), {
            "type": "terminal", "command": "npm test", "exit_code": 0,
            "stdout": "passed", "stderr": "", "timed_out": False,
            "duration_seconds": 2.5,
        })
