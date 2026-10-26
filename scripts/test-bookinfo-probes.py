"""Stdlib tests for probe content checks, failure handling and metric rendering."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

source = Path(__file__).resolve().parents[1] / 'addons/alloy/bookinfo-probes/base/probes.py'
spec = importlib.util.spec_from_file_location('probes', source)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class ProbeTests(unittest.TestCase):
    def response(self, body):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = body
        return response

    def test_http_200_missing_content_is_failure(self):
        with patch.object(probe.urllib.request, 'urlopen', return_value=self.response(b'partial page')):
            self.assertFalse(probe.fetch('http://example', ['ISBN-10'])[0])

    def test_expected_content_is_success(self):
        with patch.object(probe.urllib.request, 'urlopen', return_value=self.response(b'ISBN-10')):
            self.assertTrue(probe.fetch('http://example', ['ISBN-10'])[0])

    def test_http_errors_record_code(self):
        with patch.object(probe.urllib.request, 'urlopen', side_effect=HTTPError('http://example',503,'error',{},None)):
            result = probe.fetch('http://example', [])
            self.assertFalse(result[0])
            self.assertEqual(result[2],503)

    def test_timeout_is_failure(self):
        with patch.object(probe.urllib.request, 'urlopen', side_effect=TimeoutError()):
            self.assertFalse(probe.fetch('http://example', [])[0])

    def test_zero_failure_and_infinite_histogram_exported(self):
        text = probe.metrics()
        self.assertIn('bookinfo_probe_requests_total{probe="ingress_productpage",outcome="failure"} 0', text)
        self.assertIn('le="+Inf"', text)
        self.assertIn('bookinfo_probe_last_run_timestamp_seconds', text)

unittest.main()
