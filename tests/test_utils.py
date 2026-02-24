"""Tests for smooth._utils."""

import base64
import io

import pytest

from smooth._utils import encode_url, process_certificates
from smooth.models import Certificate


class TestEncodeUrl:
  def test_sets_interactive_true(self):
    result = encode_url("https://example.com/view?token=abc", interactive=True, embed=False)
    assert "interactive=true" in result
    assert "embed=false" in result
    assert "token=abc" in result

  def test_sets_interactive_false(self):
    result = encode_url("https://example.com/view", interactive=False, embed=False)
    assert "interactive=false" in result

  def test_sets_embed_true(self):
    result = encode_url("https://example.com/view", interactive=False, embed=True)
    assert "embed=true" in result

  def test_preserves_existing_query_params(self):
    result = encode_url("https://example.com/view?foo=bar&baz=1", interactive=True, embed=False)
    assert "foo=bar" in result
    assert "baz=1" in result
    assert "interactive=true" in result

  def test_url_with_no_query_string(self):
    result = encode_url("https://example.com/view", interactive=True, embed=True)
    assert "interactive=true" in result
    assert "embed=true" in result
    assert result.startswith("https://example.com/view?")

  def test_defaults(self):
    result = encode_url("https://example.com")
    assert "interactive=true" in result
    assert "embed=false" in result


class TestProcessCertificates:
  def test_returns_none_for_none(self):
    assert process_certificates(None) is None

  def test_converts_bytes_io_to_base64(self):
    data = b"fake-cert-binary-data"
    cert = Certificate(file=io.BytesIO(data), password="secret")
    result = process_certificates([cert])
    assert result is not None
    assert len(result) == 1
    assert result[0].file == base64.b64encode(data).decode("utf-8")
    assert result[0].password == "secret"

  def test_passes_through_string_file(self):
    cert = Certificate(file="already-base64-encoded")
    result = process_certificates([cert])
    assert result is not None
    assert result[0].file == "already-base64-encoded"

  def test_handles_dict_input_with_string(self):
    result = process_certificates([{"file": "some-string"}])
    assert result is not None
    assert result[0].file == "some-string"

  def test_handles_dict_input_with_binary_io(self):
    data = b"cert-from-dict"
    result = process_certificates([{"file": io.BytesIO(data)}])
    assert result is not None
    assert result[0].file == base64.b64encode(data).decode("utf-8")

  def test_raises_on_invalid_file_type(self):
    cert = Certificate(file=12345)
    with pytest.raises(TypeError, match="Certificate file must be a string or binary IO"):
      process_certificates([cert])

  def test_does_not_mutate_original(self):
    cert = Certificate(file="original")
    process_certificates([cert])
    assert cert.file == "original"

  def test_multiple_certificates(self):
    certs = [
      Certificate(file=io.BytesIO(b"cert1")),
      Certificate(file="cert2-string"),
    ]
    result = process_certificates(certs)
    assert result is not None
    assert len(result) == 2
    assert result[0].file == base64.b64encode(b"cert1").decode("utf-8")
    assert result[1].file == "cert2-string"
