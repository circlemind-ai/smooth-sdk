"""Tests for smooth._exceptions."""

from smooth._exceptions import ApiError


class TestApiError:
  def test_stores_attributes(self):
    err = ApiError(status_code=404, detail="Not found", response_data={"code": "NOT_FOUND"})
    assert err.status_code == 404
    assert err.detail == "Not found"
    assert err.response_data == {"code": "NOT_FOUND"}

  def test_message_format(self):
    err = ApiError(status_code=500, detail="Internal error")
    assert str(err) == "API Error 500: Internal error"
