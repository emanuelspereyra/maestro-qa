import maestro_qa


def test_package_imports_and_has_version():
    assert maestro_qa.__version__ == "0.1.0"
