"""Tests for the per-plugin durable storage convention (plugins/plugin_storage).

The contract under test: data lives under ``<marcel home>/plugin-data/<name>/``
(NOT the ``plugins/<name>/`` install tree), names that could escape the root
are rejected, and the sqlite helper opens a WAL-mode connection inside the
data dir.
"""

from __future__ import annotations

import pytest

from marcel_constants import reset_marcel_home_override, set_marcel_home_override
from plugins.plugin_storage import plugin_data_dir, plugin_db


@pytest.fixture
def marcel_home(tmp_path):
    token = set_marcel_home_override(str(tmp_path))
    try:
        yield tmp_path
    finally:
        reset_marcel_home_override(token)


def test_data_dir_lives_outside_the_install_tree(marcel_home):
    root = plugin_data_dir("my-plugin")

    assert root == marcel_home / "plugin-data" / "my-plugin"
    assert root.is_dir()
    # The invariant that motivated the module: data must not live under the
    # install tree that `marcel plugins remove` deletes.
    assert (marcel_home / "plugins") not in root.parents


def test_data_dir_is_stable_across_calls(marcel_home):
    assert plugin_data_dir("p") == plugin_data_dir("p")


@pytest.mark.parametrize("bad", ["", ".", "..", "../escape", "a/b", "a\\b", "x" * 65])
def test_hostile_names_are_rejected(marcel_home, bad):
    with pytest.raises(ValueError):
        plugin_data_dir(bad)


def test_plugin_db_opens_wal_sqlite_in_the_data_dir(marcel_home):
    conn = plugin_db("board")
    try:
        conn.execute("CREATE TABLE t (x)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()

        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
    finally:
        conn.close()

    assert (marcel_home / "plugin-data" / "board" / "data.db").exists()


def test_plugin_db_rejects_path_shaped_filenames(marcel_home):
    with pytest.raises(ValueError):
        plugin_db("board", filename="../outside.db")
    with pytest.raises(ValueError):
        plugin_db("board", filename="")
