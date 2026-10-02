from django.test import SimpleTestCase

from unicom.services.webchat.send_webchat_message import _message_body


class WebChatMediaMessageTests(SimpleTestCase):
    def test_media_only_generated_image_gets_text_fallback(self):
        text, html = _message_body({
            "file_path": "media/generated.png",
            "media_type": "image",
        })

        self.assertEqual(text, "Generated image")
        self.assertEqual(html, "")

    def test_empty_text_without_media_remains_invalid(self):
        self.assertEqual(_message_body({"text": "  "}), ("", ""))
