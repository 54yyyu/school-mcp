---
name: coursework
description: Check the user's courses through the `cw` CLI — Canvas LMS (MIT, Columbia) plus Gradescope. Use for deadlines/homework due, course announcements, Canvas inbox messages from instructors, grades, course lists, downloading course files, or syncing deadlines to macOS Reminders. Not for HTML <canvas> drawing.
---

# coursework (`cw`)

`cw` is on PATH (`coursework` is the same command). Prefer `cw`.

| Need | Command |
|---|---|
| What's due | `cw deadlines` (`-d DAYS`, `-s canvas\|gradescope`) |
| Announcements | `cw announcements` (`-c COURSE`, `-u` unread, `-f` full text) |
| Inbox | `cw inbox` (`-u` unread), then `cw message ID` for the thread |
| Grades | `cw grades` or `cw grades COURSE` |
| Courses | `cw courses` |
| What files a course has / what's new | `cw files COURSE` (`--since 7d`, `--compare DIR --missing`) |
| Download course files | `cw download COURSE` (`--id ID`, `-p DIR`, `--flat`) |
| Accounts | `cw accounts`, `cw use mit\|columbia` |
| Reminders sync | `cw reminders` |

- COURSE can be a code (`20.201`), a name fragment (`crispr`), or a Canvas id.
- `-a ACCOUNT` targets another account for one call; `--json` gives machine output.
- For any other option, run `cw COMMAND -h` rather than guessing.

Ask before running these, since they change things:
- `cw reminders`: wipes and rewrites a Reminders list.
- `cw use`: switches the saved active account.
- `cw download`: writes files. To sync, run `cw files COURSE --compare DIR --missing` first, then `cw download COURSE --id ...`. Never download into the user's own course folders unless asked.
- `cw message --mark-read`: marks the thread read.

Everything else is read-only. Reading a message does not mark it read.
