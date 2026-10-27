from pathlib import Path

from rgcopy.engine.rsync import (
    BACKUP_SUFFIX,
    TransferOptions,
    build_command,
    exclude_pattern,
    is_file_name,
    parse_progress_line,
)


def test_progress_line_with_counters():
    line = "     21,233,664  70%   19.55MB/s    0:00:01 (xfr#1, to-chk=3/5)"
    parsed = parse_progress_line(line)
    assert parsed is not None
    assert parsed.bytes_done == 21_233_664
    assert parsed.percent == 70
    assert parsed.speed == 19.55 * 1024**2
    assert parsed.eta_s == 1
    assert (parsed.transferred, parsed.to_check, parsed.total_entries) == (1, 3, 5)


def test_progress_line_human_readable_and_incremental():
    parsed = parse_progress_line("          1.23G  45%  512.00kB/s    1:02:03 (xfr#12, ir-chk=1000/2000)")
    assert parsed is not None
    assert parsed.bytes_done == int(1.23 * 1024**3)
    assert parsed.speed == 512 * 1024
    assert parsed.eta_s == 3723
    assert parsed.to_check == 1000


def test_progress_line_without_counters():
    parsed = parse_progress_line("         32,768   0%    0.00kB/s    0:00:00")
    assert parsed is not None
    assert parsed.bytes_done == 32_768
    assert parsed.transferred is None


def test_names_and_noise():
    assert is_file_name("album/one.txt")
    assert is_file_name("album/ñandú b.txt")
    assert not is_file_name("album/")
    assert not is_file_name("")
    assert not is_file_name("sending incremental file list")
    assert not is_file_name("sent 1,234 bytes  received 35 bytes  2,538.00 bytes/sec")
    assert not is_file_name("total size is 30,000,005  speedup is 1.00")
    assert parse_progress_line("album/one.txt") is None


def test_copy_command_keeps_sources_inside_destination():
    argv = build_command("rsync", [Path("/a/photos"), Path("/a/-n.txt")], Path("/b/"), TransferOptions())
    assert argv[0] == "rsync"
    assert "-a" in argv
    assert "--info=progress2,name1" in argv
    # Options end before the paths, so names starting with "-" are never options
    assert argv[argv.index("--") + 1 :] == ["/a/photos", "/a/-n.txt", "/b/"]
    assert "--remove-source-files" not in argv


def test_command_options():
    options = TransferOptions(mode="move", conflict="backup", checksum=True, preserve=False, bwlimit=500)
    argv = build_command("rsync", [Path("/a/x")], Path("/b"), options)
    assert "-rlt" in argv and "-a" not in argv
    assert "--remove-source-files" in argv
    assert "--checksum" in argv
    assert "--bwlimit=500" in argv
    assert "--backup" in argv and f"--suffix={BACKUP_SUFFIX}" in argv
    assert "--ignore-existing" in build_command(
        "rsync", [Path("/a")], Path("/b"), TransferOptions(conflict="skip")
    )
    assert "--update" in build_command("rsync", [Path("/a")], Path("/b"), TransferOptions(conflict="update"))


def test_exclude_patterns_are_literal_and_anchored():
    assert exclude_pattern("album/a[1]*?.jpg") == "/album/a\\[1]\\*\\?.jpg"
    assert exclude_pattern("back\\slash") == "/back\\\\slash"


def test_verify_command_changes_nothing_and_keeps_the_rule():
    options = TransferOptions(mode="move", conflict="update", bwlimit=100, checksum=False)
    argv = build_command("rsync", [Path("/a/x")], Path("/b"), options, excludes=["x/skip.me"], verify=True)
    assert "--dry-run" in argv and "--checksum" in argv and "--itemize-changes" in argv
    assert "--remove-source-files" not in argv
    assert "--bwlimit=100" not in argv
    assert not any(a.startswith("--info=") for a in argv)
    # Files kept by the rule are not reported as different
    assert "--update" in argv
    assert "--exclude=/x/skip.me" in argv
