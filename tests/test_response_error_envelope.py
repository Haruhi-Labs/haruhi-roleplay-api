from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.api.responses import (  # noqa: E402
    error_body_from_mapping,
    error_response,
    response_status,
    success_response,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import DTOValidationError, RequestId  # noqa: E402


class ResponseErrorEnvelopeTests(unittest.TestCase):
    def test_success_response_contains_data_and_request_id(self) -> None:
        response = success_response({"reply": "hello"}, RequestId("req-1"))

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"], {"reply": "hello"})
        self.assertEqual(response["request_id"], "req-1")
        self.assertNotIn("error", response)

    def test_validation_error_response(self) -> None:
        response = error_response(DTOValidationError("appId is required"), "req-2")

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-2")
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response["error"]["message"], "appId is required")
        self.assertEqual(
            response_status(DTOValidationError("appId is required")),
            400,
        )

    def test_app_error_uses_stable_code_and_default_message(self) -> None:
        error = AppError(code=ErrorCode.PERSONA_NOT_FOUND)
        response = error_response(error, "req-3")

        self.assertEqual(response["error"]["code"], "PERSONA_NOT_FOUND")
        self.assertEqual(response["error"]["message"], "Character was not found.")
        self.assertEqual(response_status(error), 404)

    def test_error_details_are_omitted_by_default(self) -> None:
        error = AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            details={"provider_raw_error": "secret provider stack trace"},
        )

        response = error_response(error, "req-4")

        self.assertNotIn("details", response["error"])

    def test_error_details_are_opt_in(self) -> None:
        error = AppError(
            code=ErrorCode.VALIDATION_ERROR,
            details={"field": "message"},
        )

        response = error_response(error, "req-5", include_details=True)

        self.assertEqual(
            error_body_from_mapping(response)["details"], {"field": "message"}
        )


if __name__ == "__main__":
    unittest.main()
