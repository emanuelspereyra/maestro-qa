import os

from maestro_qa import config


def test_load_env_file_sets_unset_variables(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MAESTRO_TEST_VAR=hello\n# comment\nMAESTRO_TEST_OTHER='quoted'\n")
    os.environ.pop("MAESTRO_TEST_VAR", None)
    os.environ.pop("MAESTRO_TEST_OTHER", None)
    try:
        config.load_env_file(env_file)
        assert os.environ["MAESTRO_TEST_VAR"] == "hello"
        assert os.environ["MAESTRO_TEST_OTHER"] == "quoted"
    finally:
        os.environ.pop("MAESTRO_TEST_VAR", None)
        os.environ.pop("MAESTRO_TEST_OTHER", None)


def test_load_env_file_never_overwrites_already_set_variable(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MAESTRO_TEST_VAR=from_file\n")
    os.environ["MAESTRO_TEST_VAR"] = "from_process"
    try:
        config.load_env_file(env_file)
        assert os.environ["MAESTRO_TEST_VAR"] == "from_process"
    finally:
        os.environ.pop("MAESTRO_TEST_VAR", None)


def test_load_env_file_missing_file_does_nothing(tmp_path):
    config.load_env_file(tmp_path / "does-not-exist.env")


def test_env_status_never_exposes_values():
    os.environ["MAESTRO_TEST_SECRET"] = "super-secret-value"
    try:
        status = config.env_status(["MAESTRO_TEST_SECRET", "MAESTRO_TEST_MISSING"])
        assert status == {"MAESTRO_TEST_SECRET": True, "MAESTRO_TEST_MISSING": False}
        assert "super-secret-value" not in str(status)
    finally:
        os.environ.pop("MAESTRO_TEST_SECRET", None)
