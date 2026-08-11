from core.config.schemas.global_config import GlobalConfig


class TestFfufWordlistMigration:
    def test_old_wordlist_path_stripped_on_load(self):
        gc = GlobalConfig.model_validate(
            {"ffuf_wordlist_path": "/usr/share/wordlists/common.txt"}
        )
        assert not hasattr(gc, "ffuf_wordlist_path")

    def test_new_wordlist_paths_stripped_on_load(self):
        gc = GlobalConfig.model_validate(
            {
                "ffuf_wordlist_paths": [
                    "/path/a.txt",
                    "/path/b.txt",
                ]
            }
        )
        assert not hasattr(gc, "ffuf_wordlist_paths")

    def test_both_old_and_new_fields_discarded(self):
        gc = GlobalConfig.model_validate(
            {
                "ffuf_wordlist_path": "/single.txt",
                "ffuf_wordlist_paths": ["/multi.txt"],
            }
        )
        assert not hasattr(gc, "ffuf_wordlist_path")
        assert not hasattr(gc, "ffuf_wordlist_paths")
