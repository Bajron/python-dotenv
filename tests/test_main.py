import io
import logging
import os
import sys
import textwrap
from unittest import mock

import pytest

try:
    import sh
    with_sh = True
except ImportError:
    with_sh = False

from .utils import as_env

import dotenv


def test_set_key_no_file(tmp_path):
    nx_path = tmp_path / "nx"
    logger = logging.getLogger("dotenv.main")

    with mock.patch.object(logger, "warning"):
        result = dotenv.set_key(nx_path, "foo", "bar")

    assert result == (True, "foo", "bar")
    assert nx_path.exists()


@pytest.mark.parametrize(
    "before,key,value,expected,after",
    [
        ("", "a", "", (True, "a", ""), "a=''\n"),
        ("", "a", "b", (True, "a", "b"), "a='b'\n"),
        ("", "a", "'b'", (True, "a", "'b'"), "a='\\'b\\''\n"),
        ("", "a", "\"b\"", (True, "a", '"b"'), "a='\"b\"'\n"),
        ("", "a", "b'c", (True, "a", "b'c"), "a='b\\'c'\n"),
        ("", "a", "b\"c", (True, "a", "b\"c"), "a='b\"c'\n"),
        ("a=b", "a", "c", (True, "a", "c"), "a='c'\n"),
        ("a=b\n", "a", "c", (True, "a", "c"), "a='c'\n"),
        ("a=b\n\n", "a", "c", (True, "a", "c"), "a='c'\n\n"),
        ("a=b\nc=d", "a", "e", (True, "a", "e"), "a='e'\nc=d"),
        ("a=b\nc=d\ne=f", "c", "g", (True, "c", "g"), "a=b\nc='g'\ne=f"),
        ("a=b\n", "c", "d", (True, "c", "d"), "a=b\nc='d'\n"),
        ("a=b", "c", "d", (True, "c", "d"), "a=b\nc='d'\n"),
    ],
)
def test_set_key(dotenv_path, before, key, value, expected, after):
    logger = logging.getLogger("dotenv.main")
    dotenv_path.write_text(before)

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.set_key(dotenv_path, key, value)

    assert result == expected
    assert dotenv_path.read_text() == after
    mock_warning.assert_not_called()


def test_set_key_encoding(dotenv_path):
    encoding = "latin-1"

    result = dotenv.set_key(dotenv_path, "a", "é", encoding=encoding)

    assert result == (True, "a", "é")
    assert dotenv_path.read_text(encoding=encoding) == "a='é'\n"


def test_set_key_permission_error(dotenv_path):
    dotenv_path.chmod(0o000)

    with pytest.raises(Exception):
        dotenv.set_key(dotenv_path, "a", "b")

    dotenv_path.chmod(0o600)
    assert dotenv_path.read_text() == ""


def test_get_key_no_file(tmp_path):
    nx_path = tmp_path / "nx"
    logger = logging.getLogger("dotenv.main")

    with mock.patch.object(logger, "info") as mock_info, \
            mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.get_key(nx_path, "foo")

    assert result is None
    mock_info.assert_has_calls(
        calls=[
            mock.call("Python-dotenv could not find configuration file %s.", nx_path)
        ],
    )
    mock_warning.assert_has_calls(
        calls=[
            mock.call("Key %s not found in %s.", "foo", nx_path)
        ],
    )


def test_get_key_not_found(dotenv_path):
    logger = logging.getLogger("dotenv.main")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.get_key(dotenv_path, "foo")

    assert result is None
    mock_warning.assert_called_once_with("Key %s not found in %s.", "foo", dotenv_path)


def test_get_key_ok(dotenv_path):
    logger = logging.getLogger("dotenv.main")
    dotenv_path.write_text("foo=bar")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.get_key(dotenv_path, "foo")

    assert result == "bar"
    mock_warning.assert_not_called()


def test_get_key_encoding(dotenv_path):
    encoding = "latin-1"
    dotenv_path.write_text("é=è", encoding=encoding)

    result = dotenv.get_key(dotenv_path, "é", encoding=encoding)

    assert result == "è"


def test_get_key_none(dotenv_path):
    logger = logging.getLogger("dotenv.main")
    dotenv_path.write_text("foo")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.get_key(dotenv_path, "foo")

    assert result is None
    mock_warning.assert_not_called()


def test_unset_with_value(dotenv_path):
    logger = logging.getLogger("dotenv.main")
    dotenv_path.write_text("a=b\nc=d")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.unset_key(dotenv_path, "a")

    assert result == (True, "a")
    assert dotenv_path.read_text() == "c=d"
    mock_warning.assert_not_called()


def test_unset_no_value(dotenv_path):
    logger = logging.getLogger("dotenv.main")
    dotenv_path.write_text("foo")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.unset_key(dotenv_path, "foo")

    assert result == (True, "foo")
    assert dotenv_path.read_text() == ""
    mock_warning.assert_not_called()


def test_unset_encoding(dotenv_path):
    encoding = "latin-1"
    dotenv_path.write_text("é=x", encoding=encoding)

    result = dotenv.unset_key(dotenv_path, "é", encoding=encoding)

    assert result == (True, "é")
    assert dotenv_path.read_text(encoding=encoding) == ""


def test_set_key_unauthorized_file(dotenv_path):
    dotenv_path.chmod(0o000)

    with pytest.raises(PermissionError):
        dotenv.set_key(dotenv_path, "a", "x")


def test_unset_non_existent_file(tmp_path):
    nx_path = tmp_path / "nx"
    logger = logging.getLogger("dotenv.main")

    with mock.patch.object(logger, "warning") as mock_warning:
        result = dotenv.unset_key(nx_path, "foo")

    assert result == (None, "foo")
    mock_warning.assert_called_once_with(
        "Can't delete from %s - it doesn't exist.",
        nx_path,
    )


def prepare_file_hierarchy(path):
    """
    Create a temporary folder structure like the following:

        test_find_dotenv0/
        └── child1
            ├── child2
            │   └── child3
            │       └── child4
            └── .env

    Then try to automatically `find_dotenv` starting in `child4`
    """

    leaf = path / "child1" / "child2" / "child3" / "child4"
    leaf.mkdir(parents=True, exist_ok=True)
    return leaf


def test_find_dotenv_no_file_raise(tmp_path):
    leaf = prepare_file_hierarchy(tmp_path)
    os.chdir(leaf)

    with pytest.raises(IOError):
        dotenv.find_dotenv(raise_error_if_not_found=True, usecwd=True)


def test_find_dotenv_no_file_no_raise(tmp_path):
    leaf = prepare_file_hierarchy(tmp_path)
    os.chdir(leaf)

    result = dotenv.find_dotenv(usecwd=True)

    assert result == ""


def test_find_dotenv_found(tmp_path):
    leaf = prepare_file_hierarchy(tmp_path)
    os.chdir(leaf)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(b"TEST=test\n")

    result = dotenv.find_dotenv(usecwd=True)

    assert result == str(dotenv_path)


@mock.patch.dict(os.environ, {}, clear=True)
def test_load_dotenv_existing_file(dotenv_path):
    dotenv_path.write_text("a=b")

    result = dotenv.load_dotenv(dotenv_path)

    assert result is True
    assert os.environ == as_env({"a": "b"})


def test_load_dotenv_no_file_verbose():
    logger = logging.getLogger("dotenv.main")

    with mock.patch.object(logger, "info") as mock_info:
        result = dotenv.load_dotenv('.does_not_exist', verbose=True)

    assert result is False
    mock_info.assert_called_once_with("Python-dotenv could not find configuration file %s.", ".does_not_exist")


@mock.patch.dict(os.environ, {"a": "c"}, clear=True)
def test_load_dotenv_existing_variable_no_override(dotenv_path):
    dotenv_path.write_text("a=b")

    result = dotenv.load_dotenv(dotenv_path, override=False)

    assert result is True
    assert os.environ == as_env({"a": "c"})


@mock.patch.dict(os.environ, {"a": "c"}, clear=True)
def test_load_dotenv_existing_variable_override(dotenv_path):
    dotenv_path.write_text("a=b")

    result = dotenv.load_dotenv(dotenv_path, override=True)

    assert result is True
    assert os.environ == as_env({"a": "b"})


@mock.patch.dict(os.environ, {"a": "c"}, clear=True)
def test_load_dotenv_redefine_var_used_in_file_no_override(dotenv_path):
    dotenv_path.write_text('a=b\nd="${a}"')

    result = dotenv.load_dotenv(dotenv_path)

    assert result is True
    if os.name == 'nt':
        # Variable is not overwritten, but variable expansion
        # uses the lowercase variable that was just defined in the file.
        assert os.environ == as_env({"a": "c", "d": "b"})
    else:
        assert os.environ == as_env({"a": "c", "d": "c"})


@mock.patch.dict(os.environ, {"a": "c"}, clear=True)
def test_load_dotenv_redefine_var_used_in_file_with_override(dotenv_path):
    dotenv_path.write_text('a=b\nd="${a}"')

    result = dotenv.load_dotenv(dotenv_path, override=True)

    assert result is True
    assert os.environ == as_env({"a": "b", "d": "b"})


@mock.patch.dict(os.environ, {}, clear=True)
def test_load_dotenv_string_io_utf_8():
    stream = io.StringIO("a=à")

    result = dotenv.load_dotenv(stream=stream)

    assert result is True
    assert os.environ == as_env({"a": "à"})


@mock.patch.dict(os.environ, {}, clear=True)
def test_load_dotenv_file_stream(dotenv_path):
    dotenv_path.write_text("a=b")

    with dotenv_path.open() as f:
        result = dotenv.load_dotenv(stream=f)

    assert result is True
    assert os.environ == as_env({"a": "b"})


@pytest.mark.skipif(not with_sh, reason="sh module is not available")
def test_load_dotenv_in_current_dir(tmp_path):
    dotenv_path = tmp_path / '.env'
    dotenv_path.write_bytes(b'a=b')
    code_path = tmp_path / 'code.py'
    code_path.write_text(textwrap.dedent("""
        import dotenv
        import os

        dotenv.load_dotenv(verbose=True)
        print(os.environ['a'])
    """))
    os.chdir(tmp_path)

    result = sh.Command(sys.executable)(code_path)

    assert result == 'b\n'


def test_dotenv_values_file(dotenv_path):
    dotenv_path.write_text("a=b")

    result = dotenv.dotenv_values(dotenv_path)

    assert result == {"a": "b"}


@pytest.mark.parametrize(
    "env,variables,override,expected",
    [
        ({"B": "c"}, {"a": "$B"}.items(), True, {"a": "$B"}),
        ({"B": "c"}, {"a": "${B}"}.items(), False, {"a": "c"}),

        ({"B": "c"}, [("B", "d"), ("a", "${B}")], False, {"a": "c", "B": "d"}),
        ({"B": "c"}, [("B", "d"), ("a", "${B}")], True, {"a": "d", "B": "d"}),

        ({"B": "c"}, [("B", "${X:-d}"), ("a", "${B}")], True, {"a": "d", "B": "d"}),

        ({"B": "c"}, {"a": "x${B}y"}.items(), True, {"a": "xcy"}),

        # Unfortunate sequence
        ({"B": "c"}, [("C", "${B}"), ("B", "${A}"), ("A", "1")], True, {"C": "c", "B": "", "A": "1"}),
        ({"B": "c"}, [("C", "${B}"), ("B", "${A}"), ("A", "1")], False, {"C": "c", "B": "", "A": "1"}),

        ({"B": "c"}, [("B", "x"), ("B", "${B}"), ("B", "${B}")], True, {"B": "x"}),
        ({"B": "c"}, [("B", "x"), ("B", "${B}"), ("B", "${B}")], False, {"B": "c"}),
        ({"B": "c"}, [("B", "x"), ("B", "${B}"), ("B", "y")], False, {"B": "y"}),
    ],
)
def test_resolve_variables(env, variables, override, expected):
    with mock.patch.dict(os.environ, env, clear=True):
        result = dotenv.main.resolve_variables(variables, override=override)
        assert result == expected


@pytest.mark.parametrize(
    "env,variables,value,override,expected",
    [
        ({"B": "c"}, {"B": "d"}, "$B", True, "$B"),
        ({"B": "c"}, {"B": "d"}, "${B}", True, "d"),
        ({"B": "c"}, {"B": "d"}, "${B}", False, "c"),

        ({}, {"B": "d"}, "${B}", False, "d"),
        ({"B": "c"}, {}, "${B}", True, "c"),

        ({"B": "c"}, {"A": "d"}, "${B}${A}", True, "cd"),

        ({"B": "c"}, {"B": "d"}, "$B$B$B", True, "$B$B$B"),
        ({"B": "c"}, {"B": "d"}, "${B}${B}${B}", True, "ddd"),
        ({"B": "c"}, {"B": "d"}, "${B}${B}${B}", False, "ccc"),

        ({"B": "c"}, {"B": "d"}, "${C}", False, ""),
        ({"B": "c"}, {"B": "d"}, "${C}", True, ""),
        ({"B": "c"}, {"B": "d"}, "${C}${C}${C}", True, ""),
        ({"B": "c"}, {"B": "d"}, "${C}a${C}b${C}", True, "ab"),
    ],
)
def test_resolve_variable(env, variables, value, override, expected):
    with mock.patch.dict(os.environ, env, clear=True):
        result = dotenv.main.resolve_variable(value, variables, override=override)
        assert result == expected


@pytest.mark.parametrize(
    "env,string,interpolate,expected",
    [
        # Use uppercase when setting up the env to be compatible with Windows

        # Defined in environment, with and without interpolation
        ({"B": "c"}, "a=$B", False, {"a": "$B"}),
        ({"B": "c"}, "a=$B", True, {"a": "$B"}),
        ({"B": "c"}, "a=${B}", False, {"a": "${B}"}),
        ({"B": "c"}, "a=${B}", True, {"a": "c"}),
        ({"B": "c"}, "a=${B:-d}", False, {"a": "${B:-d}"}),
        ({"B": "c"}, "a=${B:-d}", True, {"a": "c"}),

        # Defined in file
        ({}, "b=c\na=${b}", True, {"a": "c", "b": "c"}),

        # Undefined
        ({}, "a=${b}", True, {"a": ""}),
        ({}, "a=${b:-d}", True, {"a": "d"}),

        # With quotes
        ({"B": "c"}, 'a="${B}"', True, {"a": "c"}),
        ({"B": "c"}, "a='${B}'", True, {"a": "c"}),

        # With surrounding text
        ({"B": "c"}, "a=x${B}y", True, {"a": "xcy"}),

        # Self-referential
        ({"A": "b"}, "A=${A}", True, {"A": "b"}),
        ({}, "a=${a}", True, {"a": ""}),
        ({"A": "b"}, "A=${A:-c}", True, {"A": "b"}),
        ({}, "a=${a:-c}", True, {"a": "c"}),

        # Reused
        ({"B": "c"}, "a=${B}${B}", True, {"a": "cc"}),

        # Re-defined and used in file
        ({"B": "c"}, "B=d\na=${B}", True, {"a": "d", "B": "d"}),
        ({}, "a=b\na=c\nd=${a}", True, {"a": "c", "d": "c"}),
        ({}, "a=b\nc=${a}\nd=e\nc=${d}", True, {"a": "b", "c": "e", "d": "e"}),

        # No value
        ({}, "a\nb=${a}", True, {"a": None, "b": ""}),
        ({}, "a\nb=${a}", False, {"a": None, "b": "${a}"}),
    ],
)
def test_dotenv_values_string_io(env, string, interpolate, expected):
    with mock.patch.dict(os.environ, env, clear=True):
        stream = io.StringIO(string)
        stream.seek(0)

        result = dotenv.dotenv_values(stream=stream, interpolate=interpolate)

        assert result == expected


@pytest.mark.parametrize(
    "string,expected_xx",
    [
        ("XX=${NOT_DEFINED-ok}", "ok"),
        ("XX=${NOT_DEFINED:-ok}", "ok"),
        ("XX=${EMPTY-ok}", ""),
        ("XX=${EMPTY:-ok}", "ok"),
        ("XX=${TEST-ok}", "tt"),
        ("XX=${TEST:-ok}",  "tt"),

        ("XX=${NOT_DEFINED+ok}", ""),
        ("XX=${NOT_DEFINED:+ok}", ""),
        ("XX=${EMPTY+ok}",  "ok"),
        ("XX=${EMPTY:+ok}",  ""),
        ("XX=${TEST+ok}", "ok"),
        ("XX=${TEST:+ok}", "ok"),

        ("XX=${EMPTY?no throw}", ""),
        ("XX=${TEST?no throw}",  "tt"),
        ("XX=${TEST:?no throw}",  "tt"),
    ],
)
def test_variable_expansions(string, expected_xx):
    test_env = {"TEST": "tt", "EMPTY": "", }
    with mock.patch.dict(os.environ, test_env, clear=True):
        stream = io.StringIO(string)
        stream.seek(0)

        result = dotenv.dotenv_values(stream=stream, interpolate=True)

        assert result["XX"] == expected_xx


@pytest.mark.parametrize(
    "string,message",
    [
        ("XX=${EMPTY:?throw}", "EMPTY: throw"),
        ("XX=${NOT_DEFINED:?throw}", "NOT_DEFINED: throw"),
        ("XX=${NOT_DEFINED?throw}", "NOT_DEFINED: throw"),
    ],
)
def test_required_variable_throws(string, message):
    test_env = {"TEST": "tt", "EMPTY": "", }
    with mock.patch.dict(os.environ, test_env, clear=True):
        stream = io.StringIO(string)
        stream.seek(0)

        with pytest.raises(LookupError, match=message):
            dotenv.dotenv_values(stream=stream, interpolate=True)


@pytest.mark.parametrize(
    "string,expected_xx",
    [
        ("XX=TEST", "TEST"),
        ("XX=\"TE\"ST", "TEST"),
        ("XX='TE\'ST", "TEST"),
        ("XX=\"TE\"'ST'", "TEST"),
        ("XX=TE'ST'", "TEST"),
        ("XX=TE\"ST\"", "TEST"),
        ("XX=TE ST", "TE ST"),
        ("XX=TE \"ST\"", "TE ST"),
        ("XX=$TEST", "$TEST"),
        ("XX=${TEST}", "tt"),
        ("XX=\"${TEST}\"", "tt"),
        ("XX='${TEST}'", "tt"),
        ("XX='$TEST'", "$TEST"),
        ("XX='\\$\\{TEST\\}'", "\\$\\{TEST\\}"),
        ("XX=\\$\\{TEST\\}", "\\$\\{TEST\\}"),
        ("XX=\"\\$\\{TEST\\}\"", "\\$\\{TEST\\}"),
    ],
)
def test_document_expansions(string, expected_xx):
    test_env = {"TEST": "tt"}
    with mock.patch.dict(os.environ, test_env, clear=True):
        stream = io.StringIO(string)
        stream.seek(0)

        result = dotenv.dotenv_values(stream=stream, interpolate=True)

        assert result["XX"] == expected_xx


@pytest.mark.parametrize(
    "string,expected_xx",
    [
        ("XX=${TEST}", "tt"),
        ("XX=\"${TEST}\"", "tt"),
        ("XX='${TEST}'", "${TEST}"),
    ],
)
def test_single_quote_expansions(string, expected_xx):
    test_env = {"TEST": "tt"}
    with mock.patch.dict(os.environ, test_env, clear=True):
        stream = io.StringIO(string)
        stream.seek(0)

        result = dotenv.dotenv_values(stream=stream, interpolate=True, single_quotes_expand=False)

        assert result["XX"] == expected_xx


def test_dotenv_values_file_stream(dotenv_path):
    dotenv_path.write_text("a=b")

    with dotenv_path.open() as f:
        result = dotenv.dotenv_values(stream=f)

    assert result == {"a": "b"}
