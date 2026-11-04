import hashlib
import unittest
from unittest.mock import Mock, patch

import requests

import checkin


class CheckinChallengeTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.headers = {"cookie": "test-session"}
        self.session.post.return_value.json.return_value = {"code": 0}

    @patch("checkin.time.sleep")
    @patch("checkin.api_get")
    def test_submits_challenge_using_first_party_protocol(self, api_get, sleep):
        api_get.return_value = {"code": 0, "nonce": "test-nonce"}
        result = checkin.checkin_request(self.session, self.headers)
        api_get.assert_called_once_with(self.session, checkin.CHALLENGE_URL, self.headers)
        sleep.assert_called_once_with(2.5)
        payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual(payload, {
            "token": "glados.rocks",
            "nonce": "test-nonce",
            "proof": hashlib.sha256(b"test-nonce.glados-observe-v1").hexdigest(),
        })
        self.assertEqual(result, {"code": 0})

    @patch("checkin.time.sleep")
    @patch("checkin.api_get")
    def test_rejected_or_missing_challenge_does_not_post(self, api_get, sleep):
        for challenge in ({"code": -1}, {"code": 0}, {"code": 0, "nonce": ""}):
            with self.subTest(challenge=challenge):
                api_get.return_value = challenge
                with self.assertRaises(RuntimeError):
                    checkin.checkin_request(self.session, self.headers)
        self.session.post.assert_not_called()
        sleep.assert_not_called()

    @patch("checkin.time.sleep")
    @patch("checkin.api_get")
    def test_transient_post_failure_fetches_a_fresh_nonce(self, api_get, sleep):
        api_get.side_effect = [
            {"code": 0, "nonce": "first"},
            {"code": 0, "nonce": "second"},
        ]
        response = Mock()
        response.json.return_value = {"code": 0}
        self.session.post.side_effect = [requests.Timeout(), response]
        self.assertEqual(checkin.checkin_request(self.session, self.headers), {"code": 0})
        self.assertEqual([
            call.kwargs["json"]["nonce"] for call in self.session.post.call_args_list
        ], ["first", "second"])


if __name__ == "__main__":
    unittest.main()
