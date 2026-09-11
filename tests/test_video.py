import unittest
from pathlib import Path

from workbench.video import VideoRequest, estimate_cost, redacted_payload, request_payload


class VideoPricingTests(unittest.TestCase):
    def test_estimates_token_priced_portrait_video(self):
        model = {
            "id": "seedance",
            "pricing_skus": {
                "video_tokens": "0.0000024",
                "video_tokens_without_audio": "0.0000012",
            },
        }
        self.assertAlmostEqual(estimate_cost(model, 4, "480x640", False), 0.03456)

    def test_estimates_second_priced_video(self):
        model = {
            "id": "veo",
            "pricing_skus": {
                "duration_seconds_without_audio_720p": "0.03",
                "duration_seconds_with_audio_720p": "0.05",
            },
        }
        self.assertAlmostEqual(estimate_cost(model, 4, "720x1280", False), 0.12)

    def test_redacts_embedded_frame(self):
        path = Path(__file__)
        payload = request_payload(
            VideoRequest("model", "move", 4, "480x640", first_frame=path)
        )
        redacted = redacted_payload(payload)
        url = redacted["frame_images"][0]["image_url"]["url"]
        self.assertIn("<base64:", url)
        self.assertNotIn("class VideoPricingTests", url)


if __name__ == "__main__":
    unittest.main()
