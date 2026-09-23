"""The local conversion leaves unrelated environment entries alone."""

from scripts.make_vesync_env_plaintext import replace_vesync_values


def test_replaces_only_vesync_values_without_exposing_or_changing_other_lines() -> None:
    before = (
        "# local config\n"
        'VESYNC_EMAIL=varlock("encrypted-email")\n'
        "OTHER_SECRET=keep-this-exactly\n"
        'VESYNC_PASSWORD=varlock("encrypted-password")\n'
    )

    after = replace_vesync_values(
        before,
        {"VESYNC_EMAIL": "person@example.com", "VESYNC_PASSWORD": "a#$=b\\c"},
    )

    assert after == (
        "# local config\n"
        "VESYNC_EMAIL='person@example.com'\n"
        "OTHER_SECRET=keep-this-exactly\n"
        "VESYNC_PASSWORD='a#$=b\\c'\n"
    )
