import psutil
import re
import subprocess

who_x_re = re.compile(r'(\S+)\s+.*\((:\d[^\)]*)\)')
_who_x_users = None
_xinit_users = None
_x_users = None


def find_who_x_users():
    """Return users logged into X, based on `who` output

    The list items are (username, $DISPLAY).
    """
    global _who_x_users
    if _who_x_users is not None:
        return _who_x_users

    w_lines = subprocess.check_output(
        ('who',)).decode('ascii').strip().split('\n')
    matches = filter(None, (who_x_re.match(l) for l in w_lines))
    _who_x_users = [m.groups() for m in matches]
    return _who_x_users


def find_xinit_users():
    """Return users logged into X via `xinit`

    The list items are (username, $DISPLAY).
    """
    global _xinit_users
    if _xinit_users is not None:
        return _xinit_users

    # Not actually for looping, just for syntactic user to make it easy to
    # exit the code block in the middle.
    while True:
        users = []
        xinits = []
        for p in psutil.process_iter():
            if p.exe().endswith('/xinit'):
                xinits.append(p)
        if not xinits:
            break
        Xorgs = []
        for p in psutil.process_iter():
            if p.exe().endswith('/Xorg'):
                xinit = any(x for x in xinits if p.ppid() == x.pid)
                if xinit:
                    Xorgs.append((xinit, p))
        if not Xorgs:
            break
        for xinit, Xorg in Xorgs:
            try:
                display = next(a for a in Xorg.cmdline() if a[0] == ':')
            except:
                continue
            try:
                proc = min((p for p in psutil.process_iter()
                            if 'DISPLAY' in p.environ() and
                            p.environ()['DISPLAY'] == display),
                           key=lambda p: p.pid)
            except:
                continue
            users.append((proc.username(), display))
        break
    _xinit_users = users
    return _xinit_users


def find_x_users():
    """Return best guess of all users logged into X

    The list items are (username, $DISPLAY).
    """
    global _x_users
    if _x_users is not None:
        return _x_users
    _x_users = list(set(find_who_x_users()) | set(find_xinit_users()))
    return _x_users


class DBusUser(object):
    """Class for executing shell commands in a user's DBus context"""

    found_users = {}

    def __init__(self, user, display):
        """`user` should be a username, `display` an X $DISPLAY setting

        Raises `KeyError` if an active DBus session for the specified user and
        display can't be located.
        """

        # Find out the user's dbus settings.
        self.user = user
        self.display = display
        which = (user, display)
        try:
            self.environ = self.found_users[which]
            return
        except KeyError:
            pass
        for proc in psutil.process_iter():
            if proc.username() != user:
                continue
            environ = proc.environ()
            if environ.get('DISPLAY', None) != display:
                continue
            if 'DBUS_SESSION_BUS_ADDRESS' not in environ:
                continue
            if environ['DBUS_SESSION_BUS_ADDRESS'].startswith('disabled'):
                continue
            self.found_users[which] = environ
            break
        self.environ = self.found_users[which]

    def __str__(self):
        return("<DBusUser('{}', '{}')>".format(self.user, self.display))

    def command(self, cmd, stderr=None):
        """Executes the specified shell command in the user's DBus context

        `cmd` is interpreted by the shell, so be careful about special
        characters.

        `stderr` is passed on to `subprocess.check_command`.
        """
        return subprocess.check_output(
            ('su', self.user, '-m', '-c', cmd),
            env=self.environ, stderr=stderr).decode('ascii')
