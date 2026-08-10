from core.config.schemas.global_config import GlobalConfig


class TestFfufWordlistMigration:
    def test_old_single_path_migrates_to_list(self):
        gc = GlobalConfig.model_validate(
            {"ffuf_wordlist_path": "/usr/share/wordlists/common.txt"}
        )
        assert gc.ffuf_wordlist_paths == ["/usr/share/wordlists/common.txt"]

    def test_empty_old_path_migrates_to_empty_list(self):
        gc = GlobalConfig.model_validate({"ffuf_wordlist_path": ""})
        assert gc.ffuf_wordlist_paths == []

    def test_new_list_field_used_directly(self):
        gc = GlobalConfig.model_validate(
            {
                "ffuf_wordlist_paths": [
                    "/path/a.txt",
                    "/path/b.txt",
                ]
            }
        )
        assert gc.ffuf_wordlist_paths == [
            "/path/a.txt",
            "/path/b.txt",
        ]

    def test_default_is_empty_list(self):
        gc = GlobalConfig()
        assert gc.ffuf_wordlist_paths == []
