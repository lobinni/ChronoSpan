"""Publisher evidence: parsing, checksum verification, cross-publisher
agreement, the earlier-expiry rule and content addressing."""

import hashlib
import json

import pytest


def test_both_publishers_normalize_to_the_same_record(core, schedule, fetcher):
    fetch = fetcher()
    record = core["acquire"](fetch)

    assert fetch.calls == list(core["PUBLISHERS"])
    assert record["schema"] == "chronospan/v1"
    assert record["rows"] == schedule["rows"]
    assert record["expires_ntp"] == schedule["expires_ntp"]
    assert record["sources"] == schedule["sources"]


def test_canonical_form_is_byte_identical_and_key_sorted(core, schedule):
    text = core["canonical"](schedule)
    assert text == core["canonical"](json.loads(text))
    assert " " not in text
    assert text.index('"expires_ntp"') < text.index('"rows"') < text.index('"schema"')


def test_content_digest_addresses_the_record_not_the_caller(core, schedule):
    first = core["content_digest"](core["canonical"](schedule))
    second = core["content_digest"](core["canonical"](schedule))
    assert first == second == hashlib.sha256(
        core["canonical"](schedule).encode("utf-8")
    ).hexdigest()

    altered = json.loads(core["canonical"](schedule))
    altered["expires_ntp"] += 1
    assert core["content_digest"](core["canonical"](altered)) != first


@pytest.mark.parametrize(
    "transform, message",
    [
        (lambda body: body.replace(b"3692217600  37", b"3692217600  36"),
         "invalid leap-second transition"),
        (lambda body: body.replace(b"3992312697", b"3992312698"),
         "publisher checksum mismatch"),
        (lambda body: body.split(b"#h")[0], "incomplete leap-second list"),
        (lambda body: body + b"\n#@ 4023129600", "duplicate leap-second metadata"),
        (lambda body: b"\xff" + body, "utf-8"),
        (lambda body: body.replace(b"2272060800  10\n", b"", 1),
         "incomplete leap-second list"),
        (lambda body: body.replace(b"2287785600  11", b"2287785601  11"),
         "invalid leap-second transition"),
        (lambda body: b"#@ 0\n" + body, "duplicate leap-second metadata"),
    ],
)
def test_rejects_corrupt_or_incomplete_publisher_files(
    core, document, transform, message
):
    with pytest.raises(ValueError, match=message):
        core["parse_leap_list"](transform(document(0)))


def test_rejects_oversized_and_empty_bodies(core):
    with pytest.raises(ValueError, match="oversized"):
        core["parse_leap_list"](b" " * 16385)
    with pytest.raises(ValueError, match="oversized"):
        core["parse_leap_list"](b"")


def test_disagreeing_transition_rows_are_rejected(core, schedule, document, fetcher):
    """Each file still carries a valid self-checksum, so only the
    cross-publisher comparison can catch the divergence."""
    shortened = document(1, rows=schedule["rows"][:-1])
    fetch = fetcher(bodies=[document(0), shortened])

    with pytest.raises(ValueError, match="transition rows disagree"):
        core["acquire"](fetch)


def test_effective_expiry_is_the_earlier_publisher_expiry(
    core, schedule, document, fetcher
):
    earlier = schedule["expires_ntp"] - 86400
    fetch = fetcher(bodies=[document(0), document(1, expires=earlier)])

    record = core["acquire"](fetch)

    assert record["expires_ntp"] == earlier
    assert [source["expires_ntp"] for source in record["sources"]] == [
        schedule["sources"][0]["expires_ntp"],
        earlier,
    ]


def test_unreachable_publisher_fails_the_whole_import(core, fetcher):
    with pytest.raises(ValueError, match="unavailable"):
        core["acquire"](fetcher(status=404))


def test_normalize_requires_at_least_one_source(core, schedule):
    with pytest.raises(ValueError, match="no publisher evidence"):
        core["normalize"](schedule["rows"], [])


def test_fixture_record_has_a_stable_content_id(core, schedule):
    """The canonical fixture record must keep hashing to the same table id:
    deployments/chronospan.studionet.json and docs/ quote it."""
    assert core["content_digest"](core["canonical"](schedule)) == (
        "4594dd3d32ae3e871a79c1bf4b100f7147a70ca7eddd5788d32a37ebfb94033b"
    )


def test_canned_publisher_files_parse_and_agree(core, schedule, fetcher):
    """samples/publisher_files/ must stay byte-exact: they are what a coder
    mocks gl.nondet.web.get with."""
    from pathlib import Path

    directory = Path(__file__).resolve().parents[1] / "samples" / "publisher_files"
    bodies = [None, None]
    for name, index in (("iers_bulletin_c.list", 0), ("nist_leap_seconds.list", 1)):
        body = (directory / name).read_bytes()
        rows, metadata = core["parse_leap_list"](body)
        assert rows == schedule["rows"]
        assert metadata["expires_ntp"] == schedule["sources"][index]["expires_ntp"]
        bodies[index] = body

    assert core["acquire"](fetcher(bodies=bodies)) == schedule
