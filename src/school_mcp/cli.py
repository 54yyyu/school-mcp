"""`coursework` / `cw` command-line interface: Canvas and Gradescope from the terminal.

Commands that talk to a school accept -a/--account to use another configured
account for that one call; every command accepts --json for machine output.
"""

import json
import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Optional

import click

from .config import (
    get_active_account,
    get_config,
    get_download_path,
    has_gradescope,
    list_accounts,
    save_download_path,
    set_active_account,
)

CONTEXT_SETTINGS = {'help_option_names': ['-h', '--help'], 'max_content_width': 100}


# =====================
# Helpers
# =====================

def common(f):
    """Add --json to a command and turn errors into clean messages."""
    @click.option('--json', 'as_json', is_flag=True, help='Print JSON instead of text.')
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except click.ClickException:
            raise
        except Exception as e:
            raise click.ClickException(str(e))
    return wrapper


def with_account(f):
    """Add -a/--account plus everything `common` adds."""
    return common(click.option(
        '-a', '--account', default=None,
        help='Account to use for this call (default: the active account).')(f))


def emit_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def local_time(iso: Optional[str]) -> str:
    """ISO timestamp from Canvas -> 'Mon 09-21 14:05' in local time."""
    if not iso:
        return '-'
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone().strftime('%a %m-%d %H:%M')
    except ValueError:
        return iso


def status(msg: str) -> None:
    """Progress notes go to stderr so --json output stays clean."""
    click.echo(msg, err=True)


# =====================
# Root
# =====================

@click.group(context_settings=CONTEXT_SETTINGS)
def main():
    """Canvas + Gradescope for your school accounts (Columbia, MIT, ...).

    \b
    Start with:  cw deadlines      cw announcements      cw inbox
    Details:     cw COMMAND --help

    `cw` and `coursework` are the same command.
    """


# =====================
# Accounts
# =====================

@main.command()
@common
def accounts(as_json):
    """List configured accounts and show which one is active."""
    try:
        active = get_active_account()
    except ValueError:
        active = None
    rows = []
    for name in list_accounts():
        try:
            c = get_config(name)
            rows.append({'account': name, 'canvas_domain': c['canvas_domain'],
                         'gradescope': has_gradescope(c), 'active': name == active})
        except ValueError as e:
            rows.append({'account': name, 'error': str(e)})
    if as_json:
        return emit_json(rows)
    for r in rows:
        mark = '*' if r.get('active') else ' '
        if 'error' in r:
            click.echo(f"{mark} {r['account']:<10} error: {r['error']}")
        else:
            gs = 'gradescope' if r['gradescope'] else 'no gradescope'
            click.echo(f"{mark} {r['account']:<10} {r['canvas_domain']}  ({gs})")


@main.command()
@click.argument('account_name')
@common
def use(account_name, as_json):
    """Switch the active account (persists; e.g. `cw use columbia`)."""
    name = set_active_account(account_name)
    domain = get_config(name)['canvas_domain']
    if as_json:
        return emit_json({'active': name, 'canvas_domain': domain})
    click.echo(f"Active account: {name} ({domain})")


# =====================
# Courses & deadlines
# =====================

@main.command()
@with_account
def courses(account, as_json):
    """List active Canvas courses (id, code, name)."""
    from .canvas_reader import CanvasReader
    rows = CanvasReader(account).course_list()
    if as_json:
        return emit_json(rows)
    for r in rows:
        click.echo(f"{r['id']:<8} {r['code']:<12} {r['name']}")


def fetch_deadlines(account, days, source='all'):
    """Unsubmitted assignments from the chosen source(s): all, canvas or gradescope."""
    from .deadline_scraper import DeadlineScraper
    scraper = DeadlineScraper(account, include_gradescope=source != 'canvas')
    if source == 'gradescope' and not scraper.gradescope_configured:
        raise click.ClickException(
            f"Account '{scraper.account}' has no Gradescope credentials "
            f"({scraper.account.upper()}_GRADESCOPE_EMAIL / _PASSWORD in .env).")
    return scraper.get_all_assignments(days, include_canvas=source != 'gradescope')


SOURCE_OPTION = click.option(
    '-s', '--source', type=click.Choice(['all', 'canvas', 'gradescope']), default='all',
    show_default=True,
    help='Where to look. "all" = Canvas, plus Gradescope when the account has it configured.')


@main.command()
@click.option('-d', '--days', default=14, show_default=True, help='How many days ahead to look.')
@SOURCE_OPTION
@with_account
def deadlines(days, source, account, as_json):
    """Unsubmitted assignments (Canvas + Gradescope) due in the next N days."""
    rows = fetch_deadlines(account, days, source)
    if as_json:
        return emit_json(rows)
    if not rows:
        return click.echo(f"No unsubmitted deadlines in the next {days} days.")
    for r in rows:
        click.echo(f"{r['due_date']:<24} [{r['platform']}] {r['course_name']} — {r['assignment_name']}")
        extra = [f"in {r['time_remaining']}"]
        if r.get('points_possible'):
            extra.append(f"{r['points_possible']:g} pts")
        if r.get('url'):
            extra.append(r['url'])
        click.echo(f"{'':<24} {'  '.join(extra)}")


@main.command()
@click.option('-d', '--days', default=14, show_default=True, help='How many days ahead to look.')
@click.option('--list', 'list_name', default='Course Assignments', show_default=True,
              help='Reminders list to write to.')
@SOURCE_OPTION
@with_account
def reminders(days, list_name, source, account, as_json):
    """Sync upcoming deadlines into a macOS Reminders list.

    Replaces the list's contents: every existing reminder in LIST is deleted
    first, then one reminder is added per deadline.
    """
    from .reminders import ReminderManager
    rows = fetch_deadlines(account, days, source)
    if not rows:
        return emit_json([]) if as_json else click.echo('No upcoming deadlines to add.')
    result = ReminderManager(list_name).add_assignments(rows)
    if as_json:
        return emit_json(result)
    click.echo(f"{result['message']} (list: {list_name})")


# =====================
# Announcements & inbox
# =====================

@main.command()
@click.option('-c', '--course', default=None, help='Course id, code (20.201) or name fragment.')
@click.option('-d', '--days', default=14, show_default=True, help='How many days back to look.')
@click.option('-u', '--unread', is_flag=True, help='Only unread announcements.')
@click.option('-f', '--full', is_flag=True, help='Print each announcement body in full.')
@with_account
def announcements(course, days, unread, full, account, as_json):
    """Course announcements from the last N days, newest first."""
    from .canvas_reader import CanvasReader
    rows = CanvasReader(account).announcements(course, days, unread)
    if as_json:
        return emit_json(rows)
    if not rows:
        return click.echo(f"No announcements in the last {days} days.")
    for r in rows:
        flag = ' (unread)' if r['read_state'] == 'unread' else ''
        click.echo(f"{local_time(r['posted_at'])}  {r['course']:<10} {r['title']}{flag}")
        if full:
            click.echo(f"  by {r['author']}  {r['url']}")
            click.echo('  ' + r['message'].replace('\n', '\n  ') + '\n')


@main.command()
@click.option('-u', '--unread', 'scope', flag_value='unread', help='Only unread conversations.')
@click.option('--sent', 'scope', flag_value='sent', help='Sent conversations.')
@click.option('--archived', 'scope', flag_value='archived', help='Archived conversations.')
@click.option('--starred', 'scope', flag_value='starred', help='Starred conversations.')
@click.option('-n', '--limit', default=20, show_default=True, help='Max conversations to show.')
@with_account
def inbox(scope, limit, account, as_json):
    """Canvas inbox conversations (messages from instructors etc.), newest first.

    Read a whole thread with `cw message ID`.
    """
    from .canvas_reader import CanvasReader
    rows = CanvasReader(account).inbox(scope, limit)
    if as_json:
        return emit_json(rows)
    if not rows:
        return click.echo('No conversations.')
    for r in rows:
        flag = '*' if r['state'] == 'unread' else ' '
        click.echo(f"{flag} {r['id']:<10} {local_time(r['last_message_at'])}  {r['subject']}")
        names = [p for p in r['participants'] if p]
        who = ', '.join(names[:3]) + (f" +{len(names) - 3} more" if len(names) > 3 else '')
        click.echo(f"  {'':<10} {r['course'] or ''}  {who}")


@main.command()
@click.argument('conversation_id', type=int)
@click.option('--mark-read', is_flag=True, help='Mark the conversation read (default leaves it as is).')
@with_account
def message(conversation_id, mark_read, account, as_json):
    """Show one inbox conversation in full (id from `cw inbox`)."""
    from .canvas_reader import CanvasReader
    conv = CanvasReader(account).message(conversation_id, mark_read)
    if as_json:
        return emit_json(conv)
    click.echo(f"{conv['subject']}  [{conv['course'] or ''}]")
    names = [p for p in conv['participants'] if p]
    who = ', '.join(names[:5]) + (f" +{len(names) - 5} more" if len(names) > 5 else '')
    click.echo(f"Participants: {who}\n")
    for m in conv['messages']:
        click.echo(f"--- {m['author']}  {local_time(m['created_at'])}")
        click.echo(m['body'])
        for a in m['attachments']:
            click.echo(f"  [attachment] {a['filename']}  {a['url']}")
        click.echo()


# =====================
# Grades
# =====================

@main.command()
@click.argument('course', required=False)
@with_account
def grades(course, account, as_json):
    """Canvas grades: overall score per course, or per-assignment for COURSE."""
    from .canvas_reader import CanvasReader
    reader = CanvasReader(account)
    if not course:
        rows = reader.grade_summary()
        if as_json:
            return emit_json(rows)
        for r in rows:
            score = '-' if r['current_score'] is None else f"{r['current_score']:g}%"
            grade = r['current_grade'] or ''
            click.echo(f"{r['code']:<12} {score:>8}  {grade}")
        return

    data = reader.course_grades(course)
    if as_json:
        return emit_json(data)
    click.echo(f"{data['code']} — {data['name']}")
    for a in data['assignments']:
        score = '-' if a['score'] is None else f"{a['score']:g}"
        total = '' if a['points_possible'] is None else f"/{a['points_possible']:g}"
        notes = ' '.join(n for n, on in (('late', a['late']), ('missing', a['missing'])) if on)
        click.echo(f"{local_time(a['due_at']):<16} {score + total:>10}  {a['assignment']}  {notes}")


# =====================
# Files
# =====================

def parse_since(value: Optional[str]) -> Optional[datetime]:
    """'2026-09-20' (local midnight) or '7d' (7 days ago) -> aware datetime."""
    if not value:
        return None
    v = value.strip().lower()
    if v.endswith('d') and v[:-1].isdigit():
        return datetime.now().astimezone() - timedelta(days=int(v[:-1]))
    try:
        return datetime.fromisoformat(value).astimezone()
    except ValueError:
        raise click.BadParameter(f"'{value}' is not a date (YYYY-MM-DD) or a day count like 7d.",
                                 param_hint="'--since'")


def human_size(n: Optional[int]) -> str:
    if n is None:
        return '-'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f"{n:.0f} {unit}" if unit == 'B' else f"{n:.1f} {unit}"
        n /= 1024


SINCE_OPTION = click.option(
    '--since', default=None,
    help='Only files created/updated since DATE (YYYY-MM-DD) or N days ago (e.g. 7d).')


@main.command()
@click.argument('course')
@SINCE_OPTION
@click.option('--compare', 'compare_dir', type=click.Path(file_okay=False), default=None,
              help='Mark each file have/changed/missing against a local folder (any layout; '
                   'matches by name+size, then content hash). Read-only.')
@click.option('--missing', 'only_missing', is_flag=True,
              help='With --compare: show only files that are not "have".')
@with_account
def files(course, since, compare_dir, only_missing, account, as_json):
    """List every file `cw download` would fetch for COURSE, without downloading.

    Same discovery as `cw download`: modules, assignments, Files tab, Pages,
    announcements, deduped by file id. Fetch selected ones with
    `cw download COURSE --id ID ...`.
    """
    from .canvas_reader import CanvasReader
    from .file_downloader import CanvasDownloader, compare_with_local, filter_since
    if only_missing and not compare_dir:
        raise click.UsageError('--missing needs --compare DIR.')
    c = CanvasReader(account).resolve_course(course)
    downloader = CanvasDownloader(account)
    listing = downloader.list_course_files(c.id)
    entries = filter_since(listing['files'], parse_since(since))
    if compare_dir:
        compare_with_local(entries, compare_dir, downloader)
        if only_missing:
            entries = [e for e in entries if e['local']['status'] != 'have']

    if as_json:
        out = dict(listing, files=entries)
        return emit_json(out)

    click.echo(f"{listing['course_name']}: {len(entries)} file(s)")
    for e in entries:
        mark = f"{e['local']['status']:<8} " if compare_dir else ''
        stamp = local_time(e['updated_at'] or e['created_at'])
        click.echo(f"{mark}{e['id']:<9} {human_size(e['size']):>9}  {stamp}  {e['display_name']}")
        detail = f"{e['source']}: {e['source_name']}  -> {e['rel_path']}"
        if e['locked']:
            detail += f"  [locked: {e['lock_explanation']}]"
        if compare_dir and e['local']['path']:
            detail += f"  (local: {os.path.relpath(e['local']['path'], os.path.expanduser(compare_dir))})"
        click.echo(f"{' ' * len(mark)}{'':<9} {detail}")
    if compare_dir:
        counts = {}
        for e in entries:
            counts[e['local']['status']] = counts.get(e['local']['status'], 0) + 1
        click.echo('  '.join(f"{k}: {v}" for k, v in sorted(counts.items()))
                   or 'Nothing missing: every file is already in the local folder.')
    for note in listing['notes']:
        click.echo(f"note: {note}")
    for err in listing['errors']:
        click.echo(f"error: {err['message']}")


@main.command()
@click.argument('course')
@click.option('-p', '--path', default=None,
              help='Download root for this run only (the saved default is set with `cw download-path`).')
@click.option('-i', '--id', 'file_ids', multiple=True,
              help='Only these file ids (repeatable, or comma-separated); see `cw files`.')
@SINCE_OPTION
@click.option('--flat', is_flag=True,
              help='Put files directly in the root, without <course>/<section>/ folders.')
@with_account
def download(course, path, file_ids, since, flat, account, as_json):
    """Download a course's files (all, or a selection).

    Covers modules, assignments (attachments and files linked in the
    description), the Files tab, and files linked from Pages and announcements.
    Linked files are fetched even when the Files tab is disabled. Preview the
    list first with `cw files COURSE`.

    COURSE is an id, code (20.201) or name fragment. Files land in
    <download root>/<course name>/<section>/; files already present with the
    same size are skipped.
    """
    from .canvas_reader import CanvasReader
    from .file_downloader import CanvasDownloader
    ids = None
    if file_ids:
        try:
            ids = [int(x) for raw in file_ids for x in raw.replace(',', ' ').split()]
        except ValueError:
            raise click.BadParameter('file ids must be numbers.', param_hint="'--id'")
    c = CanvasReader(account).resolve_course(course)
    status(f"Downloading {c.name} ...")
    result = CanvasDownloader(account).download_all_course_files(
        c.id, path, file_ids=ids, since=parse_since(since), flat=flat)
    if as_json:
        return emit_json(result)
    s = result['stats']
    click.echo(f"{result['course_name']} -> {result['base_path']}")
    locked = f", {s['locked']} locked" if s.get('locked') else ''
    click.echo(f"{s['successful']} downloaded, {s['skipped']} skipped{locked}, {s['failed']} failed")
    for note in result.get('notes', []):
        click.echo(f"  note: {note}")
    for f in result['files']:
        if f['status'] == 'locked':
            click.echo(f"  locked: {f['filename']}: {f['message']}")
        elif f['status'] == 'error':
            click.echo(f"  failed: {f['filename']}: {f['message']}")


@main.command('download-path')
@click.argument('path', required=False)
@common
def download_path(path, as_json):
    """Show the default download root, or set it to PATH (created if missing)."""
    if path:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.exists(path) and not os.path.isdir(path):
            raise click.ClickException(f"'{path}' exists and is not a directory.")
        if not os.path.isdir(path):
            os.makedirs(path)
            status(f"Created {path}")
        save_download_path(path)
    current = get_download_path()
    if as_json:
        return emit_json({'download_path': current})
    click.echo(current)


# =====================
# MCP server
# =====================

@main.command()
def serve():
    """Run the MCP server over stdio (for Claude Desktop / MCP clients)."""
    from .server import mcp
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
