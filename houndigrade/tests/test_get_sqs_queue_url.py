"""Collection of tests for ``cli._get_sqs_queue_url`` function."""
from unittest import TestCase
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from cli import _get_sqs_queue_url


class TestGetSqlQueueUrl(TestCase):
    """Test suite for houndigrade CLI's "_get_sqs_queue_url" function."""

    @patch("cli.boto3")
    def test_get_sqs_queue_url_for_existing_queue(self, mock_boto3):
        """
        Test getting URL for existing SQS queue.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        mock_client.get_queue_url.return_value = {"QueueUrl": expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    @patch("cli.boto3")
    def test_get_sqs_queue_url_creates_new_queue(self, mock_boto3):
        """
        Test getting URL for a SQS queue that does not yet exist.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        error_response = {"Error": {"Code": ".NonExistentQueue"}}
        exception = ClientError(error_response, Mock())
        mock_client.get_queue_url.side_effect = exception
        mock_client.create_queue.return_value = {"QueueUrl": expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)
        mock_client.create_queue.assert_called_with(QueueName=queue_name)
