import urllib.parse


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
