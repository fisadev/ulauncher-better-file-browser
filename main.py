import logging
from pathlib import Path

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import (
    KeywordQueryEvent,
    PreferencesEvent,
    PreferencesUpdateEvent,
)
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
from ulauncher.api.shared.action.OpenAction import OpenAction

logger = logging.getLogger(__name__)

try:
    from gi.repository import Gtk, Gio
except:
    Gtk, Gio = None, None


DEFAULT_FILE_ICON = "images/default_file.png"
DEFAULT_FOLDER_ICON = "images/default_folder.png"
IMAGE_EXTENSIONS = (
    '.png',
    '.jpg', '.jpeg',
)


def get_icon_for_file(path, size=256):
    """
    Get the gtk icon path for a specific file or folder (defined by its path).
    """
    if path.name.lower().endswith(IMAGE_EXTENSIONS):
        return str(path)

    if Gtk is not None:
        try:
            if path.is_dir():
                icon = Gio.content_type_get_icon("folder")
            else:
                mimetype = Gio.content_type_guess(path.name)[0]
                icon = Gio.content_type_get_icon(mimetype)

            theme = Gtk.IconTheme.get_default()
            actual_icon = theme.choose_icon(icon.get_names(), size, 0)
            if actual_icon:
                return actual_icon.get_filename()
        except Exception:
            logger.exception("Failed to get icon for path: %s", path)

    if path.is_dir():
        return DEFAULT_FOLDER_ICON
    else:
        return DEFAULT_FILE_ICON


def matches_filter(file_name, filter_):
    """
    Determine if a given file_name matches a given fuzzy filter.
    Hidden files can match filters, but only if a filter is actually being used, else they don't
    match the "empty" filter.
    """
    if filter_:
        filter_ = filter_.lower().replace(' ', '').strip()
        # iterate over the filter chars. If they are found inside the file name in the same order,
        # the name matches the filter. So "fisa" matches the filter "fa", but not "af"
        rest = file_name.lower()
        for filter_char in filter_:
            try:
                index = rest.index(filter_char)
                rest = rest[index:]
            except ValueError:
                return False
        # if we got here, we din't stop at any unfound char
        return True
    else:
        # no filter specified, just determine if it's a hidden file or not
        return not file_name.startswith('.')


class FileBrowserExtension(Extension):
    """
    Extension that shows a list of directories and files under the current path, and allows the
    user to navigate them.
    """
    def __init__(self):
        super(FileBrowserExtension, self).__init__()
        self.preferences = {}

        # this event is risen when the user starts using our extension, and also every time the
        # query changes
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        # events risen when the preferences change (on boot and on change)
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesEventListener())


class PreferencesEventListener(EventListener):
    """
    On boot and on preferences changes, update the preferences in the extension instance.
    """
    def on_event(self, event, extension):
        if hasattr(event, 'preferences'):
            extension.preferences = event.preferences
        else:
            extension.preferences[event.id] = event.new_value


class KeywordQueryEventListener(EventListener):
    """
    On query, show the contents of the current folder and filter them if needed.
    """
    def on_event(self, event, extension):
        keyword = event.get_keyword()
        argument = event.get_argument()

        if argument and '/' in argument:
            # there's an argument and has a "/", we must interpret it like this:
            # "f /foo/bar/baz else" == "search 'baz else' inside /foo/bar/"
            bits = argument.split('/')
            current_path = Path('/'.join(bits[:-1]))
            current_filter = bits[-1]
        else:
            # there's no argument, or the argument has no "/". Search inside the default path
            current_path = Path(extension.preferences.get('fb_default_path'))
            current_filter = argument

        current_path = current_path.expanduser()
        items = []

        # if we aren't filtering stuff inside the current dir, show an option to open the current
        # dir in the OS's file browser
        if not current_filter:
            item = ExtensionResultItem(
                icon=get_icon_for_file(current_path),
                name="[ Open folder in external file browser ]",
                on_enter=OpenAction(str(current_path)),
            )
            items.append(item)

        # children items, filtered, and folders first
        sorted_children = list(sorted(
            current_path.iterdir(),
            key=lambda child_path: (not child_path.is_dir(), child_path.name),
        ))

        items_limit = extension.preferences.get('fb_items_limit')
        if items_limit is not None:
            try:
                items_limit = int(items_limit)
            except ValueError:
                pass

        show_hidden = extension.preferences.get('fb_show_hidden') == 'Yes'

        # show each one of them
        items_count = 0
        for child_path in sorted_children:
            if show_hidden or not child_path.name.startswith('.'):
                if matches_filter(child_path.name, current_filter):
                    if child_path.is_dir():
                        item_action = SetUserQueryAction("{} {}/".format(keyword, str(child_path)))
                    else:
                        item_action = OpenAction(str(child_path))

                    item = ExtensionResultItem(
                        icon=get_icon_for_file(child_path),
                        name=child_path.name,
                        on_enter=item_action,
                    )
                    items.append(item)

                    items_count += 1
                    if items_limit is not None and items_count == items_limit:
                        break

        return RenderResultListAction(items)


if __name__ == '__main__':
    FileBrowserExtension().run()
