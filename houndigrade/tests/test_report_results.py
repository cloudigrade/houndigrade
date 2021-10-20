"""Collection of tests for ``cli.report_results`` function."""
from datetime import datetime
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from cli import generate_results_key, report_results


class TestGenerateResultsKey(TestCase):
    """Test suite for houndigrade CLI's "generate_results_key" function."""

    def test_generate_results_key(self):
        """Test generating the key."""
        test_now = datetime.now()
        test_uuid = uuid4()
        test_time_path = test_now.strftime("%Y-%m/%d/%H.%M.%S")

        test_key = f"InspectionResults/{test_time_path}-{test_uuid}.json"

        with patch("cli.datetime") as mock_datetime, patch("cli.uuid4") as mock_uuid4:
            mock_datetime.now.return_value = test_now
            mock_uuid4.return_value = test_uuid

            result_key = generate_results_key()

        self.assertEqual(test_key, result_key)

    @patch("cli.boto3")
    @patch("cli.b64encode")
    @patch("cli.md5")
    @patch("cli.jsonpickle")
    def test_report_results(
        self, mock_jsonpickle, mock_md5, mock_b64encode, mock_boto3
    ):
        """Verify we correctly report results."""
        mock_results = {"test": "results"}
        mock_results_bucket_name = "TestBucket"
        mock_json_encode = mock_jsonpickle.encode
        mock_utf_json = mock_json_encode.return_value.encode
        mock_md5_digest = mock_md5.return_value.digest
        mock_b64_decode = mock_b64encode.return_value.decode
        mock_resource = mock_boto3.resource
        mock_bucket = mock_resource.return_value.Bucket
        mock_put_object = mock_bucket.return_value.put_object

        with patch.dict(
            "os.environ", {"RESULTS_BUCKET_NAME": mock_results_bucket_name}
        ):
            report_results(mock_results)

        mock_json_encode.assert_called_once_with(mock_results)
        mock_utf_json.assert_called_once()
        mock_md5.assert_called_once_with(mock_utf_json.return_value)
        mock_md5_digest.assert_called_once()
        mock_b64encode.assert_called_once_with(mock_md5_digest.return_value)
        mock_b64_decode.assert_called_once()

        mock_resource.assert_called_once_with("s3")
        mock_bucket.assert_called_once_with(mock_results_bucket_name)
        mock_put_object.assert_called_once()
