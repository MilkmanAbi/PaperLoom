"""
Builds PaperLoom's default component library.

Each component is a folder with meta.json + PySide/C++ templates. Styling comes
from the app theme's role system (core/app_theme.py) - a template sets
`role` and the window stylesheet does the rest, so a component never hardcodes
colours and every component gets light/dark for free.

Run:  python3 tools/build_library.py
"""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "paperloom", "components", "library")

# name, qt class, include, category, role, source, tags, description,
# properties [(name,type,default,control)], quick [names], signals [(name,stub)],
# extra_py (lines), extra_cpp (lines)
SPECS = [
    # ---------------- buttons ----------------
    ("button", "Button", "QPushButton", "buttons", "button_secondary", "default",
     ["button", "click", "action", "plain"], "A standard button.",
     [("text", "string", "Button", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("primary_button", "Primary button", "QPushButton", "buttons", "button_primary", "default",
     ["button", "primary", "cta", "submit"], "The main call-to-action button.",
     [("text", "string", "Continue", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("pill_button", "Pill button", "QPushButton", "buttons", "button_pill", "default",
     ["button", "rounded", "pill", "cta"], "A fully rounded button.",
     [("text", "string", "Button", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("ghost_button", "Ghost button", "QPushButton", "buttons", "button_ghost", "default",
     ["button", "ghost", "text", "subtle"], "A borderless text button.",
     [("text", "string", "Learn more", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("danger_button", "Danger button", "QPushButton", "buttons", "button_danger", "default",
     ["button", "danger", "delete", "destructive"], "A destructive action button.",
     [("text", "string", "Delete", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("icon_button", "Icon button", "QPushButton", "buttons", "button_icon", "default",
     ["button", "icon", "square", "compact"], "A compact square icon button.",
     [("text", "string", "+", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),

    ("toggle_button", "Toggle button", "QPushButton", "buttons", "button_secondary", "default",
     ["button", "toggle", "checkable", "state"], "A button that stays pressed.",
     [("text", "string", "Toggle", "text"), ("checked", "bool", False, "checkbox")],
     ["text"], [("toggled", "on_{name}_toggled")],
     ['self.{name}.setCheckable(True)', 'self.{name}.setChecked({checked_py})'],
     ['{name}->setCheckable(true);', '{name}->setChecked({checked_cpp});']),

    # ---------------- inputs ----------------
    ("text_box", "Text box", "QLineEdit", "inputs", "input", "default",
     ["input", "text", "field", "entry"], "A single-line text input.",
     [("placeholder", "string", "Enter text...", "text")], ["placeholder"],
     [("textChanged", "on_{name}_text_changed")], [], []),

    ("password_box", "Password box", "QLineEdit", "inputs", "input", "default",
     ["input", "password", "secret", "login"], "A masked password input.",
     [("placeholder", "string", "Password", "text")], ["placeholder"],
     [("textChanged", "on_{name}_text_changed")],
     ['self.{name}.setEchoMode(QLineEdit.EchoMode.Password)'],
     ['{name}->setEchoMode(QLineEdit::Password);']),

    ("search_bar", "Search bar", "QLineEdit", "inputs", "search", "default",
     ["search", "find", "filter", "query"], "A rounded search field.",
     [("placeholder", "string", "Search...", "text")], ["placeholder"],
     [("textChanged", "on_{name}_text_changed")],
     ['self.{name}.setClearButtonEnabled(True)'],
     ['{name}->setClearButtonEnabled(true);']),

    ("text_area", "Text area", "QPlainTextEdit", "inputs", "input", "default",
     ["input", "multiline", "textarea", "notes"], "A multi-line text area.",
     [("placeholder", "string", "Write something...", "text")], ["placeholder"],
     [("textChanged", "on_{name}_text_changed")], [], []),

    ("spin_box", "Number input", "QSpinBox", "inputs", "input", "default",
     ["input", "number", "spin", "integer"], "A numeric stepper input.",
     [("value", "int", 0, "number")], ["value"], [("valueChanged", "on_{name}_value_changed")],
     ['self.{name}.setRange(-99999, 99999)'], ['{name}->setRange(-99999, 99999);']),

    ("combo_box", "Dropdown", "QComboBox", "inputs", "select", "default",
     ["combo", "dropdown", "select", "picker"], "A dropdown selection box.",
     [("items", "string", "One, Two, Three", "text")], ["items"],
     [("currentIndexChanged", "on_{name}_changed")], [], []),

    ("date_picker", "Date picker", "QDateEdit", "inputs", "input", "default",
     ["date", "calendar", "picker", "input"], "A date selection field.",
     [], [], [("dateChanged", "on_{name}_date_changed")],
     ['self.{name}.setCalendarPopup(True)'], ['{name}->setCalendarPopup(true);']),

    ("checkbox", "Checkbox", "QCheckBox", "inputs", "checkbox", "default",
     ["checkbox", "check", "boolean", "tick"], "A labelled checkbox.",
     [("text", "string", "Enable", "text"), ("checked", "bool", False, "checkbox")],
     ["text"], [("toggled", "on_{name}_toggled")],
     ['self.{name}.setChecked({checked_py})'], ['{name}->setChecked({checked_cpp});']),

    ("switch", "Switch", "QCheckBox", "inputs", "switch", "default",
     ["switch", "toggle", "onoff", "setting"], "An on/off switch.",
     [("text", "string", "Notifications", "text"), ("checked", "bool", True, "checkbox")],
     ["text"], [("toggled", "on_{name}_toggled")],
     ['self.{name}.setChecked({checked_py})'], ['{name}->setChecked({checked_cpp});']),

    ("radio", "Radio button", "QRadioButton", "inputs", "radio", "default",
     ["radio", "option", "choice"], "A single radio option.",
     [("text", "string", "Option", "text")], ["text"], [("toggled", "on_{name}_toggled")], [], []),

    ("slider", "Slider", "QSlider", "inputs", "slider", "default",
     ["slider", "range", "value", "seek"], "A horizontal value slider.",
     [("value", "int", 50, "number")], ["value"], [("valueChanged", "on_{name}_value_changed")],
     ['self.{name}.setOrientation(Qt.Orientation.Horizontal)', 'self.{name}.setRange(0, 100)'],
     ['{name}->setOrientation(Qt::Horizontal);', '{name}->setRange(0, 100);']),

    ("dial", "Knob", "QDial", "inputs", "dial", "default",
     ["dial", "knob", "rotary", "control", "audio"], "A rotary knob control.",
     [("value", "int", 40, "number")], ["value"], [("valueChanged", "on_{name}_value_changed")],
     ['self.{name}.setRange(0, 100)', 'self.{name}.setNotchesVisible(True)'],
     ['{name}->setRange(0, 100);', '{name}->setNotchesVisible(true);']),

    # ---------------- display ----------------
    ("label", "Label", "QLabel", "display", "label", "default",
     ["label", "text", "caption"], "A static text label.",
     [("text", "string", "Label", "text")], ["text"], [], [], []),

    ("title", "Title", "QLabel", "display", "title", "default",
     ["title", "heading", "h1", "header"], "A large page title.",
     [("text", "string", "Page title", "text")], ["text"], [], [], []),

    ("subtitle", "Subtitle", "QLabel", "display", "subtitle", "default",
     ["subtitle", "heading", "h2", "section"], "A section heading.",
     [("text", "string", "Section", "text")], ["text"], [], [], []),

    ("caption", "Caption", "QLabel", "display", "caption", "default",
     ["caption", "hint", "small", "help"], "Small muted helper text.",
     [("text", "string", "Helper text", "text")], ["text"], [], [], []),

    ("badge", "Badge", "QLabel", "display", "badge", "default",
     ["badge", "pill", "count", "status", "tag"], "A small accent badge.",
     [("text", "string", "New", "text")], ["text"], [],
     ['self.{name}.setAlignment(Qt.AlignmentFlag.AlignCenter)'],
     ['{name}->setAlignment(Qt::AlignCenter);']),

    ("avatar", "Avatar", "QLabel", "display", "avatar", "default",
     ["avatar", "user", "profile", "initials"], "A circular user avatar.",
     [("text", "string", "AB", "text")], ["text"], [],
     ['self.{name}.setAlignment(Qt.AlignmentFlag.AlignCenter)'],
     ['{name}->setAlignment(Qt::AlignCenter);']),

    ("image", "Image", "QLabel", "display", "image", "default",
     ["image", "picture", "photo", "asset"], "An image placeholder.",
     [("text", "string", "Image", "text")], ["text"], [],
     ['self.{name}.setAlignment(Qt.AlignmentFlag.AlignCenter)'],
     ['{name}->setAlignment(Qt::AlignCenter);']),

    ("progress_bar", "Progress bar", "QProgressBar", "display", "progress", "default",
     ["progress", "bar", "loading", "percent"], "A horizontal progress indicator.",
     [("value", "int", 60, "number")], ["value"], [],
     ['self.{name}.setTextVisible(False)'], ['{name}->setTextVisible(false);']),

    ("divider", "Divider", "QFrame", "display", "divider", "default",
     ["divider", "separator", "rule", "line"], "A horizontal rule.",
     [], [], [],
     ['self.{name}.setFrameShape(QFrame.Shape.HLine)'],
     ['{name}->setFrameShape(QFrame::HLine);']),

    # ---------------- containers ----------------
    ("card", "Card", "QFrame", "containers", "card", "default",
     ["card", "panel", "surface", "container", "box"], "A raised content card.",
     [], [], [], [], []),

    ("panel", "Panel", "QFrame", "containers", "panel", "default",
     ["panel", "section", "container", "group"], "A subtle grouping panel.",
     [], [], [], [], []),

    ("group_box", "Group box", "QGroupBox", "containers", "group", "default",
     ["group", "fieldset", "box", "container"], "A titled group container.",
     [("title", "string", "Group", "text")], ["title"], [], [], []),

    ("tabs", "Tabs", "QTabWidget", "containers", "tabs", "default",
     ["tabs", "tabbed", "sections", "navigation"], "A tabbed container.",
     [], [], [("currentChanged", "on_{name}_tab_changed")],
     ['self.{name}.addTab(QWidget(), "First")', 'self.{name}.addTab(QWidget(), "Second")'],
     ['{name}->addTab(new QWidget(), "First");', '{name}->addTab(new QWidget(), "Second");']),

    ("scroll_area", "Scroll area", "QScrollArea", "containers", "scroll", "default",
     ["scroll", "area", "overflow", "container"], "A scrollable region.",
     [], [], [],
     ['self.{name}.setWidgetResizable(True)'], ['{name}->setWidgetResizable(true);']),

    # ---------------- data ----------------
    ("list_view", "List", "QListWidget", "data", "list", "default",
     ["list", "items", "rows", "collection"], "A simple item list.",
     [("items", "string", "First item, Second item, Third item", "text")], ["items"],
     [("currentRowChanged", "on_{name}_row_changed")], [], []),

    ("tree_view", "Tree", "QTreeWidget", "data", "tree", "default",
     ["tree", "hierarchy", "nested", "explorer"], "A hierarchical tree view.",
     [], [], [("itemSelectionChanged", "on_{name}_selection_changed")],
     ['self.{name}.setHeaderLabels(["Name"])'],
     ['{name}->setHeaderLabels(QStringList("Name"));']),

    ("table_view", "Table", "QTableWidget", "data", "table", "default",
     ["table", "grid", "rows", "data", "spreadsheet"], "A data table.",
     [], [], [],
     ['self.{name}.setColumnCount(3)', 'self.{name}.setRowCount(4)',
      'self.{name}.setHorizontalHeaderLabels(["A", "B", "C"])'],
     ['{name}->setColumnCount(3);', '{name}->setRowCount(4);']),


    # ---------------- media ----------------
    ("image_frame", "Image frame", "QLabel", "media", "media_frame", "default",
     ["image", "picture", "photo", "asset", "png", "jpg", "media"],
     "Displays an image asset. Pick an asset by name and it renders here.",
     [("asset", "asset", "", "asset"), ("fit", "string", "contain", "text")],
     ["asset"], [], [], []),

    ("gif_frame", "Animated image", "QLabel", "media", "media_frame", "default",
     ["gif", "animation", "animated", "media", "movie"],
     "Plays an animated GIF asset via QMovie.",
     [("asset", "asset", "", "asset")], ["asset"], [], [], []),

    ("video_frame", "Video frame", "QWidget", "media", "media_frame", "default",
     ["video", "mp4", "player", "media"],
     "A video surface backed by QMediaPlayer.",
     [("asset", "asset", "", "asset")], ["asset"], [], [], []),

    ("audio_player", "Audio player", "QWidget", "media", "card", "default",
     ["audio", "mp3", "wav", "sound", "player", "media"],
     "An audio playback strip backed by QMediaPlayer.",
     [("asset", "asset", "", "asset")], ["asset"], [], [], []),

    # ---------------- overlays ----------------
    ("overlay_scrim", "Overlay scrim", "QWidget", "overlays", "scrim", "default",
     ["overlay", "scrim", "modal", "dim", "backdrop"],
     "A dimming backdrop that sits over the page.",
     [], [], [], [], []),

    ("modal_dialog", "Modal dialog", "QFrame", "overlays", "modal", "default",
     ["modal", "dialog", "popup", "overlay", "prompt"],
     "A centred modal dialog surface.",
     [("title", "string", "Are you sure?", "text")], ["title"], [], [], []),

    ("toast", "Toast", "QFrame", "overlays", "toast", "default",
     ["toast", "snackbar", "notification", "overlay", "message"],
     "A transient notification toast.",
     [("text", "string", "Saved", "text")], ["text"], [], [], []),

    ("tooltip_bubble", "Tooltip bubble", "QFrame", "overlays", "tooltip", "default",
     ["tooltip", "hint", "bubble", "overlay", "popover"],
     "A small pointing tooltip bubble.",
     [("text", "string", "Hint", "text")], ["text"], [], [], []),

    ("drawer", "Drawer", "QWidget", "overlays", "sidebar", "default",
     ["drawer", "panel", "slide", "overlay", "sheet"],
     "A slide-in side drawer surface.",
     [], [], [], [], []),

    ("popover_menu", "Popover menu", "QFrame", "overlays", "card", "default",
     ["popover", "menu", "dropdown", "overlay", "context"],
     "A floating menu surface.",
     [], [], [], [], []),

    # ---------------- more inputs ----------------
    ("double_spin", "Decimal input", "QDoubleSpinBox", "inputs", "input", "default",
     ["decimal", "float", "number", "input"], "A decimal number input.",
     [("value", "int", 0, "number")], ["value"], [("valueChanged", "on_{name}_value_changed")],
     [], []),

    ("time_picker", "Time picker", "QTimeEdit", "inputs", "input", "default",
     ["time", "clock", "picker", "input"], "A time selection field.",
     [], [], [("timeChanged", "on_{name}_time_changed")], [], []),
    # ---------------- app chrome ----------------
    ("app_bar", "App bar", "QWidget", "chrome", "appbar", "default",
     ["appbar", "header", "topbar", "toolbar", "chrome"], "A top app bar surface.",
     [], [], [], [], []),

    ("sidebar", "Sidebar", "QWidget", "chrome", "sidebar", "default",
     ["sidebar", "nav", "drawer", "chrome"], "A side navigation surface.",
     [], [], [], [], []),

    ("status_strip", "Status strip", "QWidget", "chrome", "statusbar", "default",
     ["status", "footer", "strip", "chrome"], "A bottom status strip.",
     [], [], [], [], []),

    ("theme_toggle", "Theme toggle", "QPushButton", "chrome", "button_icon", "default",
     ["theme", "dark", "light", "moon", "sun", "toggle"],
     "A sun/moon button that switches the app between light and dark.",
     [("text", "string", "☾", "text")], ["text"], [("clicked", "on_{name}_clicked")], [], []),
]


PY_HEADER = """self.{name} = {qt}(MainWindow)
self.{name}.setObjectName("{name}")
self.{name}.setProperty("role", "{role}")
self.{name}.setGeometry({{{{ x }}}}, {{{{ y }}}}, {{{{ width }}}}, {{{{ height }}}})
"""

CPP_HEADER = """{name} = new {qt}(MainWindow);
{name}->setObjectName("{name}");
{name}->setProperty("role", "{role}");
{name}->setGeometry({{{{ x }}}}, {{{{ y }}}}, {{{{ width }}}}, {{{{ height }}}});
"""


def build():
    os.makedirs(ROOT, exist_ok=True)
    # wipe old library so removals take effect
    for existing in os.listdir(ROOT):
        path = os.path.join(ROOT, existing)
        if os.path.isdir(path):
            for f in os.listdir(path):
                os.remove(os.path.join(path, f))
            os.rmdir(path)

    for (cid, name, qt, category, role, source, tags, desc,
         props, quick, signals, extra_py, extra_cpp) in SPECS:
        folder = os.path.join(ROOT, cid)
        os.makedirs(folder, exist_ok=True)

        meta = {
            "id": cid, "name": name, "category": category, "source": source,
            "widget_class": qt, "qt_include": qt, "style_role": role,
            "tags": tags, "description": desc,
            "properties": [
                {"name": p, "type": t, "default": d, "control": c} for p, t, d, c in props],
            "quick_properties": quick,
            "signals": [{"name": s, "stub": stub} for s, stub in signals],
        }
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            f.write("\n")

        # --- pyside template ---
        py = PY_HEADER.format(name="{{ name }}", qt=qt, role=role)
        cpp = CPP_HEADER.format(name="{{ name }}", qt=qt, role=role)
        prop_names = {p for p, _, _, _ in props}

        if "text" in prop_names:
            py += 'self.{{ name }}.setText("{{ text }}")\n'
            cpp += '{{ name }}->setText("{{ text }}");\n'
        if "title" in prop_names:
            py += 'self.{{ name }}.setTitle("{{ title }}")\n'
            cpp += '{{ name }}->setTitle("{{ title }}");\n'
        if "placeholder" in prop_names:
            py += 'self.{{ name }}.setPlaceholderText("{{ placeholder }}")\n'
            cpp += '{{ name }}->setPlaceholderText("{{ placeholder }}");\n'
        if "asset" in prop_names:
            py += 'self.{{ name }}.setProperty("asset", "{{ asset }}")\n'
            py += 'self.{{ name }}.setText("{{ asset }}" or "Image")\n'
            cpp += '{{ name }}->setProperty("asset", "{{ asset }}");\n'
        if "value" in prop_names:
            py += 'self.{{ name }}.setValue({{ value }})\n'
            cpp += '{{ name }}->setValue({{ value }});\n'
        if "items" in prop_names:
            if qt == "QComboBox":
                py += '{% for item in items.split(",") %}self.{{ name }}.addItem("{{ item.strip() }}")\n{% endfor %}'
                cpp += '{% for item in items.split(",") %}{{ name }}->addItem("{{ item.strip() }}");\n{% endfor %}'
            else:
                py += '{% for item in items.split(",") %}self.{{ name }}.addItem("{{ item.strip() }}")\n{% endfor %}'
                cpp += '{% for item in items.split(",") %}{{ name }}->addItem("{{ item.strip() }}");\n{% endfor %}'

        for line in extra_py:
            py += line.replace("{name}", "{{ name }}") \
                      .replace("{checked_py}", "{{ 'True' if checked else 'False' }}") + "\n"
        for line in extra_cpp:
            cpp += line.replace("{name}", "{{ name }}") \
                       .replace("{checked_cpp}", "{{ 'true' if checked else 'false' }}") + "\n"

        with open(os.path.join(folder, "template.pyside.jinja"), "w", encoding="utf-8") as f:
            f.write(py)
        with open(os.path.join(folder, "template.cpp.jinja"), "w", encoding="utf-8") as f:
            f.write(cpp)

    print(f"built {len(SPECS)} components into {os.path.relpath(ROOT)}")


if __name__ == "__main__":
    build()
