import pytest

from udr_publish import cloudinary_client as C

from conftest import FakeResponse


def test_signature_matches_cloudinary_documentation_example():
    # https://cloudinary.com/documentation/authentication_signatures (exemple officiel)
    params = {"eager": "w_400,h_300,c_pad|w_260,h_200,c_crop", "public_id": "sample_image",
              "timestamp": "1315060510"}
    assert C.sign(params, "abcd") == "bfd09f95f331f558cbd1320e67aa8d488770583e"


class Recorder:
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, headers=None, files=None, timeout=None):
        self.calls.append((headers, len(files["file"][1])))
        return FakeResponse(200, {"secure_url": "https://res.cloudinary.com/dl8itl9nw/video/upload/v42/x.mp4",
                                  "version": 42, "public_id": "x", "bytes": 5})


def test_large_files_are_sent_in_chunks_with_one_upload_id(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CHUNK_SIZE", 1000)
    f = tmp_path / "big.mp4"
    f.write_bytes(b"\0" * 2500)
    rec = Recorder()
    result = C.CloudinaryClient(rec, "dl8itl9nw", "k", "s").upload_video(f, "udr/x")
    assert [h["Content-Range"] for h, _ in rec.calls] == [
        "bytes 0-999/2500", "bytes 1000-1999/2500", "bytes 2000-2499/2500"]
    assert len({h["X-Unique-Upload-Id"] for h, _ in rec.calls}) == 1
    assert result.secure_url.endswith("/v42/x.mp4")


def test_unversioned_url_is_rejected(tmp_path):
    class Bad(Recorder):
        def post(self, *a, **k):
            return FakeResponse(200, {"secure_url": "https://res.cloudinary.com/x.mp4", "version": 7})
    f = tmp_path / "a.mp4"
    f.write_bytes(b"1")
    with pytest.raises(C.CloudinaryError, match="non versionnée"):
        C.CloudinaryClient(Bad(), "dl8itl9nw", "k", "s").upload_video(f, "p")
