"""Unit tests for infrastructure.apidocs.route_id module."""

import json

import pytest

from infrastructure.apidocs.route_id import check, normalize_path, route_id


class TestNormalizePath:
    """Tests for normalize_path function."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            # Curly-brace params
            ("/users/{id}", "/users/{}"),
            ("/posts/{post_id}/comments/{comment_id}", "/posts/{}/comments/{}"),
            # Colon params
            ("/users/:id", "/users/{}"),
            ("/posts/:post_id/comments/:comment_id", "/posts/{}/comments/{}"),
            # Angle-bracket params
            ("/users/<int:id>", "/users/{}"),
            ("/posts/<int:id>/comments/<comment_id>", "/posts/{}/comments/{}"),
            # Square-bracket params
            ("/users/[id]", "/users/{}"),
            ("/posts/[post_id]/comments/[comment_id]", "/posts/{}/comments/{}"),
            # Catch-all params
            ("/files/[...path]", "/files/{}"),
            ("/static/[...slug]", "/static/{}"),
            # Mixed param styles
            ("/api/{id}/:name/[value]", "/api/{}/{}/{}"),
            # Case normalization
            ("/Users/ID", "/users/id"),
            ("/POSTS/{ID}", "/posts/{}"),
            # Trailing slash removal
            ("/users/", "/users"),
            ("/posts/{id}/", "/posts/{}"),
            ("/USERS/{ID}/", "/users/{}"),
            # Empty and root paths
            ("", "/"),
            ("/", "/"),
            # Whitespace trimming
            ("  /users  ", "/users"),
            ("  /users/  ", "/users"),
            # Complex path
            (
                "/api/v1/users/{user_id}/posts/:post_id/[...tags]",
                "/api/v1/users/{}/posts/{}/{}",
            ),
        ],
        ids=[
            "curly_single",
            "curly_multiple",
            "colon_single",
            "colon_multiple",
            "angle_int",
            "angle_mixed",
            "square_single",
            "square_multiple",
            "catchall_path",
            "catchall_slug",
            "mixed_styles",
            "case_lower",
            "case_upper",
            "trailing_slash",
            "trailing_slash_param",
            "trailing_slash_mixed",
            "empty_string",
            "root_slash",
            "whitespace_start_end",
            "whitespace_trailing",
            "complex_mixed",
        ],
    )
    def test_normalize_path_patterns(self, path, expected):
        """Test parameter pattern normalization."""
        assert normalize_path(path) == expected

    def test_normalize_path_returns_string(self):
        """Test that normalize_path returns a string."""
        result = normalize_path("/users")
        assert isinstance(result, str)

    def test_normalize_path_idempotent(self):
        """Test that normalizing twice gives the same result."""
        path = "/Users/{ID}/"
        normalized_once = normalize_path(path)
        normalized_twice = normalize_path(normalized_once)
        assert normalized_once == normalized_twice


class TestRouteId:
    """Tests for route_id function."""

    def test_route_id_format(self):
        """Test that route_id produces a 12-character hex string."""
        result = route_id("GET", "/users", "web", "v1")
        assert isinstance(result, str)
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_route_id_deterministic(self):
        """Test that same inputs always produce same output."""
        id1 = route_id("GET", "/users", "web", "v1")
        id2 = route_id("GET", "/users", "web", "v1")
        assert id1 == id2

    def test_route_id_method_case_insensitive(self):
        """Test that HTTP method case does not affect uniqueness."""
        id_upper = route_id("GET", "/users", "web", "v1")
        id_lower = route_id("get", "/users", "web", "v1")
        id_mixed = route_id("Get", "/users", "web", "v1")
        assert id_upper == id_lower == id_mixed

    def test_route_id_path_case_normalized(self):
        """Test that path case is normalized."""
        id_lower = route_id("GET", "/users", "web", "v1")
        id_upper = route_id("GET", "/USERS", "web", "v1")
        assert id_lower == id_upper

    def test_route_id_path_params_normalized(self):
        """Test that different param styles produce same ID."""
        id_curly = route_id("GET", "/users/{id}", "web", "v1")
        id_colon = route_id("GET", "/users/:id", "web", "v1")
        id_angle = route_id("GET", "/users/<int:id>", "web", "v1")
        assert id_curly == id_colon == id_angle

    def test_route_id_uniqueness_by_method(self):
        """Test that different methods produce different IDs."""
        get_id = route_id("GET", "/users", "web", "v1")
        post_id = route_id("POST", "/users", "web", "v1")
        put_id = route_id("PUT", "/users", "web", "v1")
        assert get_id != post_id != put_id

    def test_route_id_uniqueness_by_path(self):
        """Test that different paths produce different IDs."""
        users_id = route_id("GET", "/users", "web", "v1")
        posts_id = route_id("GET", "/posts", "web", "v1")
        assert users_id != posts_id

    def test_route_id_uniqueness_by_app(self):
        """Test that different apps produce different IDs."""
        web_id = route_id("GET", "/users", "web", "v1")
        api_id = route_id("GET", "/users", "api", "v1")
        assert web_id != api_id

    def test_route_id_uniqueness_by_api_version(self):
        """Test that different API versions produce different IDs."""
        v1_id = route_id("GET", "/users", "api", "v1")
        v2_id = route_id("GET", "/users", "api", "v2")
        assert v1_id != v2_id

    def test_route_id_empty_api_version(self):
        """Test that empty API version is handled."""
        id_empty = route_id("GET", "/users", "web", "")
        id_none = route_id("GET", "/users", "web", "")
        assert id_empty == id_none
        assert isinstance(id_empty, str)
        assert len(id_empty) == 12


class TestCheck:
    """Tests for check function."""

    def test_check_valid_file_returns_zero(self, tmp_path):
        """Test that check returns 0 for valid routes file."""
        routes_file = tmp_path / "routes.jsonl"
        routes = [
            {
                "method": "GET",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": route_id("GET", "/users", "web", "v1"),
            },
            {
                "method": "POST",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": route_id("POST", "/users", "web", "v1"),
            },
        ]
        with open(routes_file, "w") as f:
            for route in routes:
                f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 0

    def test_check_mismatched_id_returns_one(self, tmp_path, capsys):
        """Test that check returns 1 when ID doesn't match."""
        routes_file = tmp_path / "routes.jsonl"
        route = {
            "method": "GET",
            "path": "/users",
            "app": "web",
            "api_version": "v1",
            "id": "wrong_id_12345",
        }
        with open(routes_file, "w") as f:
            f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 1
        captured = capsys.readouterr()
        assert "id wrong_id_12345 != computed" in captured.out

    def test_check_duplicate_ids_returns_one(self, tmp_path, capsys):
        """Test that check returns 1 when there are duplicate IDs."""
        routes_file = tmp_path / "routes.jsonl"
        shared_id = route_id("GET", "/users", "web", "v1")
        routes = [
            {
                "method": "GET",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": shared_id,
            },
            {
                "method": "GET",
                "path": "/posts",
                "app": "web",
                "api_version": "v1",
                "id": shared_id,
            },
        ]
        with open(routes_file, "w") as f:
            for route in routes:
                f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 1
        captured = capsys.readouterr()
        assert "duplicate id" in captured.out

    def test_check_ignores_empty_lines(self, tmp_path):
        """Test that check ignores empty lines."""
        routes_file = tmp_path / "routes.jsonl"
        route = {
            "method": "GET",
            "path": "/users",
            "app": "web",
            "api_version": "v1",
            "id": route_id("GET", "/users", "web", "v1"),
        }
        with open(routes_file, "w") as f:
            f.write(json.dumps(route) + "\n")
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 1  # Duplicate ID (both same route)

    def test_check_missing_api_version_field(self, tmp_path):
        """Test that check handles missing api_version field."""
        routes_file = tmp_path / "routes.jsonl"
        route = {
            "method": "GET",
            "path": "/users",
            "app": "web",
            "id": route_id("GET", "/users", "web", ""),
        }
        with open(routes_file, "w") as f:
            f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 0

    def test_check_prints_summary(self, tmp_path, capsys):
        """Test that check prints route count and problem count."""
        routes_file = tmp_path / "routes.jsonl"
        routes = [
            {
                "method": "GET",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": route_id("GET", "/users", "web", "v1"),
            },
            {
                "method": "POST",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": route_id("POST", "/users", "web", "v1"),
            },
        ]
        with open(routes_file, "w") as f:
            for route in routes:
                f.write(json.dumps(route) + "\n")

        check(str(routes_file))
        captured = capsys.readouterr()
        assert "2 routes" in captured.out
        assert "0 problem(s)" in captured.out

    def test_check_multiple_problems(self, tmp_path, capsys):
        """Test that check counts multiple problems."""
        routes_file = tmp_path / "routes.jsonl"
        shared_id = "badid123456"
        routes = [
            {
                "method": "GET",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": shared_id,
            },
            {
                "method": "POST",
                "path": "/users",
                "app": "web",
                "api_version": "v1",
                "id": shared_id,
            },
        ]
        with open(routes_file, "w") as f:
            for route in routes:
                f.write(json.dumps(route) + "\n")

        result = check(str(routes_file))
        assert result == 1
        captured = capsys.readouterr()
        assert "3 problem(s)" in captured.out

    def test_check_line_numbers_in_error_messages(self, tmp_path, capsys):
        """Test that error messages include line numbers."""
        routes_file = tmp_path / "routes.jsonl"
        route1 = {
            "method": "GET",
            "path": "/users",
            "app": "web",
            "api_version": "v1",
            "id": route_id("GET", "/users", "web", "v1"),
        }
        route2 = {
            "method": "POST",
            "path": "/posts",
            "app": "web",
            "api_version": "v1",
            "id": "wrong_id_12345",
        }
        with open(routes_file, "w") as f:
            f.write(json.dumps(route1) + "\n")
            f.write(json.dumps(route2) + "\n")

        check(str(routes_file))
        captured = capsys.readouterr()
        assert "line 2" in captured.out
