"""Tests for the HashDB post/creator processed logs (metadata-level dedup)."""

from kemonodownloader.hash_db import HashDB


class TestPostProcessedLog:
    def test_mark_and_check(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        assert not db.is_post_processed("fanbox", "77", "12345")
        db.mark_post_processed("fanbox", "77", "12345")
        assert db.is_post_processed("fanbox", "77", "12345")

    def test_post_key_is_scoped_by_creator(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        db.mark_post_processed("fanbox", "77", "12345")
        assert not db.is_post_processed("fanbox", "78", "12345")
        assert not db.is_post_processed("patreon", "77", "12345")

    def test_mark_post_processed_is_idempotent(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        db.mark_post_processed("fanbox", "77", "1")
        db.mark_post_processed("fanbox", "77", "1")
        assert db.is_post_processed("fanbox", "77", "1")


class TestCreatorProcessedLog:
    def test_mark_and_check(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        assert not db.is_creator_processed("fanbox", "77")
        db.mark_creator_processed("fanbox", "77")
        assert db.is_creator_processed("fanbox", "77")

    def test_get_processed_creators(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        assert db.get_processed_creators() == set()
        db.mark_creator_processed("fanbox", "77")
        db.mark_creator_processed("patreon", "9")
        assert db.get_processed_creators() == {("fanbox", "77"), ("patreon", "9")}


class TestProcessedLogsIndependentOfFileHashes:
    def test_processed_logs_do_not_affect_file_count(self, isolated_hash_dir):
        db = HashDB(isolated_hash_dir)
        assert db.count() == 0
        db.mark_post_processed("fanbox", "77", "1")
        db.mark_creator_processed("fanbox", "77")
        # Processed logs live in separate tables, not the file_hashes store.
        assert db.count() == 0
