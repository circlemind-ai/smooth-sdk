import base64
import io
import logging
import urllib.parse
from typing import Any

from .models import Certificate

# Configure logging
logger = logging.getLogger("smooth")


def encode_url(url: str, interactive: bool = True, embed: bool = False) -> str:
  parsed_url = urllib.parse.urlparse(url)
  params = urllib.parse.parse_qs(parsed_url.query)
  params.update(
    {
      "interactive": ["true" if interactive else "false"],
      "embed": ["true" if embed else "false"],
    }
  )
  return urllib.parse.urlunparse(parsed_url._replace(query=urllib.parse.urlencode(params, doseq=True)))


def process_certificates(
  certificates: list[Certificate | dict[str, Any]] | None,
) -> list[Certificate] | None:
  """Process certificates, converting binary IO to base64-encoded strings.

  Args:
      certificates: List of certificates with file field as string or binary IO.

  Returns:
      List of certificates with file field as base64-encoded string, or None if input is None.
  """
  if certificates is None:
    return None

  processed_certs: list[Certificate] = []
  for cert in certificates:
    processed_cert = Certificate(**cert) if isinstance(cert, dict) else cert.model_copy()  # Create a copy

    file_content = processed_cert.file
    if isinstance(file_content, io.IOBase):
      # Read the binary content and encode to base64
      binary_data = file_content.read()
      processed_cert.file = base64.b64encode(binary_data).decode("utf-8")
    elif not isinstance(file_content, str):
      raise TypeError(f"Certificate file must be a string or binary IO, got {type(file_content)}")

    processed_certs.append(processed_cert)

  return processed_certs
