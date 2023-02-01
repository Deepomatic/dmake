import pytest

from dmake.docker_registry import get_image_digest

@pytest.mark.parametrize("image", [
    'ubuntu:12.04',  # available only via old manifest: application/vnd.docker.distribution.manifest.v2+json
    'ubuntu:20.04',  # available only via new manifest: application/vnd.oci.image.index.v1+json
])
def test_image_digest(image):
    assert get_image_digest(image) != ""
