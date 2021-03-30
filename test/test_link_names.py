import pytest

from dmake.deepobuild import LinkNames, NeededServiceSerializer, DockerLinkSerializer
from dmake.serializer import ValidationError


# docker_links

def test_docker_links_different_simple_service_same_file():
    """multiple docker_links can have different link names"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo2'})

def test_docker_links_different_simple_service_different_files():
    """multiple docker_links can have different link names"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    DockerLinkSerializer()._validate_('dmake2.yml', None, {'image_name': 'foo', 'link_name': 'foo2'})


def test_docker_links_same_simple_service_same_file():
    """multiple docker_links *cannot* have same link_name"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'docker_link' in 'dmake.yml', was previously defined as 'docker_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_docker_links_same_simple_service_different_files():
    """multiple docker_links *cannot* have same link_name"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        DockerLinkSerializer()._validate_('dmake2.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'docker_link' in 'dmake2.yml', was previously defined as 'docker_link' in 'dmake.yml'" == excinfo.value.args[0]


# needed_services

def test_needed_services_same_simple_service_same_file():
    """multiple services can need same simple service"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})

def test_needed_services_same_simple_service_different_files():
    """multiple services can need same simple service"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo'})


def test_needed_services_same_simple_service_different_link_names_same_file():
    """multiple services can need same simple service with different link names"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo2'})

def test_needed_services_same_simple_service_different_link_names_different_files():
    """multiple services can need same simple service with different link names"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo2'})


def test_needed_services_different_service_name_same_file():
    """multiple services *cannot* need different services with same link_name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo2', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_needed_services_different_service_name_different_files():
    """multiple services *cannot* need different services with same link_name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo2', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake2.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_needed_services_simple_specialized_env_same_file():
    """multiple services *cannot* need simple and specialized for same link name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo',  'env': {'FOO': 'bar'}})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_needed_services_simple_specialized_env_different_files():
    """multiple services *cannot* need simple and specialized for same link name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo',  'env': {'FOO': 'bar'}})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake2.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]


def test_needed_services_same_specialized_env_service_same_file():
    """multiple services can need same specialized"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})

def test_needed_services_same_specialized_env_service_different_files():
    """multiple services can need same specialized"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})


def test_needed_services_different_specialized_env_service_same_file():
    """multiple services *cannot* need different specialized env for same link name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar2'}})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_needed_services_different_specialized_env_service_different_files():
    """multiple services *cannot* need different specialized env for same link name"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar2'}})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake2.yml', was previously defined as 'needed_link' in 'dmake.yml'" == excinfo.value.args[0]


def test_needed_services_same_specialized_env_different_env_exports_service_same_file():
    """multiple services can need same specialized but different env_exports"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}, 'env_exports': {'EXPORT': '1'}})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}, 'env_exports': {'EXPORT': '2'}})

def test_needed_services_same_specialized_env_different_env_exports_service_different_files():
    """multiple services can need same specialized but different env_exports"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}, 'env_exports': {'EXPORT': '1'}})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}, 'env_exports': {'EXPORT': '2'}})


def test_needed_services_same_specialized_env_service_different_link_name_same_file():
    """multiple services can need same specialized service with different link names"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo2', 'env': {'FOO': 'bar2'}})

def test_needed_services_same_specialized_env_service_different_link_name_different_files():
    """multiple services can need same specialized service with different link names"""
    LinkNames.reset()
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo', 'env': {'FOO': 'bar'}})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo2', 'env': {'FOO': 'bar2'}})


# mix needed_services and docker_links

def test_mix_links_different_link_names_same_file():
    """mix docker_links, needed_services can have different link names"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo2'})

def test_mix_links_different_link_names_different_files():
    """mix docker_links, needed_services can have different link names"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo2'})


def test_mix_links_same_link_names_same_file():
    """mix docker_links, needed_services *cannot* have same link name"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake.yml', was previously defined as 'docker_link' in 'dmake.yml'" == excinfo.value.args[0]

def test_mix_links_same_link_names_different_files():
    """mix docker_links, needed_services *cannot* have same link name"""
    LinkNames.reset()
    DockerLinkSerializer()._validate_('dmake.yml', None, {'image_name': 'foo', 'link_name': 'foo'})
    with pytest.raises(ValidationError) as excinfo:
        NeededServiceSerializer()._validate_('dmake2.yml', None, {'service_name': 'foo', 'link_name': 'foo'})
    assert "Duplicate link name 'foo' with different definitions: 'needed_link' in 'dmake2.yml', was previously defined as 'docker_link' in 'dmake.yml'" == excinfo.value.args[0]
