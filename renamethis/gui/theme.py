"""Tema visual do RenameThis: paletas clara/escura, folha de estilo (QSS) e ícones.

- O estilo base é sempre o *Fusion*, para a folha de estilo ficar igual em
  Windows, macOS e Linux.
- O modo claro/escuro segue o sistema (e acompanha a troca em tempo real).
  ``RENAMETHIS_THEME=light|dark`` força um dos dois.
- Os ícones são SVGs embutidos aqui, coloridos conforme a paleta e convertidos
  em PNG com o QtSvg. Assim funcionam no executável do PyInstaller sem depender
  de plugins de imagem.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

STYLE_FILE = Path(__file__).with_name("styles") / "theme.qss"

FONT_FAMILIES = [
    "Segoe UI Variable Text",
    "Segoe UI",
    "SF Pro Text",
    "Helvetica Neue",
    "Inter",
    "Noto Sans",
    "Ubuntu",
    "Cantarell",
    "DejaVu Sans",
    "Arial",
]


@dataclass(frozen=True)
class ThemePalette:
    """Cores do tema. Os nomes viram ``{{chave}}`` dentro de ``theme.qss``."""

    dark: bool
    window: str  # fundo da janela
    window2: str  # segunda cor do degradê de fundo
    card: str  # painéis (group boxes)
    card_border: str
    surface: str  # campos, tabela, lista
    surface_alt: str  # linhas alternadas, hover
    border: str
    border_focus: str
    text: str
    text_muted: str
    text_on_accent: str
    accent: str  # cor principal
    accent2: str  # segunda cor do degradê
    accent3: str  # terceira cor do degradê
    accent_hover: str
    accent_hover2: str
    accent_pressed: str
    accent_soft: str  # fundo suave (seleção, títulos)
    selection: str
    selection_text: str
    header1: str  # degradê do cabeçalho (menu + barra da pasta)
    header2: str
    header3: str
    header_text: str
    header_input: str
    header_input_border: str
    danger: str
    danger2: str
    danger_hover: str
    danger_soft: str
    ok: str
    ok_soft: str
    warning: str
    warning_soft: str
    error: str
    error_soft: str
    skipped: str
    skipped_soft: str
    disabled_bg: str
    disabled_text: str
    scrollbar: str
    scrollbar_hover: str
    tooltip_bg: str
    tooltip_text: str


LIGHT = ThemePalette(
    dark=False,
    window="#eef2ff",
    window2="#e0f2fe",
    card="#ffffff",
    card_border="#dbe3f5",
    surface="#ffffff",
    surface_alt="#f5f7ff",
    border="#cfd8ee",
    border_focus="#5b5bf0",
    text="#1e2440",
    text_muted="#66708f",
    text_on_accent="#ffffff",
    accent="#5b5bf0",
    accent2="#3b82f6",
    accent3="#0ea5e9",
    accent_hover="#6d6df5",
    accent_hover2="#22b8f0",
    accent_pressed="#4338ca",
    accent_soft="#e8e9ff",
    selection="#dfe3ff",
    selection_text="#1e1b4b",
    header1="#1e1b4b",
    header2="#3730a3",
    header3="#0369a1",
    header_text="#ffffff",
    header_input="#ffffff",
    header_input_border="#a5b4fc",
    danger="#f43f5e",
    danger2="#f97316",
    danger_hover="#fb7185",
    danger_soft="#ffe4e8",
    ok="#059669",
    ok_soft="#d1fae5",
    warning="#c2410c",
    warning_soft="#ffedd5",
    error="#dc2626",
    error_soft="#fee2e2",
    skipped="#64748b",
    skipped_soft="#e2e8f0",
    disabled_bg="#e5e9f5",
    disabled_text="#9aa3bd",
    scrollbar="#c3cbe6",
    scrollbar_hover="#8f9bd6",
    tooltip_bg="#1e1b4b",
    tooltip_text="#f5f7ff",
)

DARK = ThemePalette(
    dark=True,
    window="#11132a",
    window2="#0b1a2e",
    card="#1a1d3a",
    card_border="#2a2f5a",
    surface="#14162f",
    surface_alt="#1c1f40",
    border="#323866",
    border_focus="#818cf8",
    text="#e8ebff",
    text_muted="#9aa3d0",
    text_on_accent="#ffffff",
    accent="#7c6cf6",
    accent2="#4f7cf7",
    accent3="#22b8e8",
    accent_hover="#8f82ff",
    accent_hover2="#3cc8f5",
    accent_pressed="#5b4bd8",
    accent_soft="#262a5c",
    selection="#33397a",
    selection_text="#ffffff",
    header1="#1b1650",
    header2="#2e2a8a",
    header3="#075985",
    header_text="#ffffff",
    header_input="#14162f",
    header_input_border="#5b61b8",
    danger="#fb7185",
    danger2="#fb923c",
    danger_hover="#fda4af",
    danger_soft="#4a1d2c",
    ok="#34d399",
    ok_soft="#123b33",
    warning="#fbbf24",
    warning_soft="#3f2f12",
    error="#f87171",
    error_soft="#4a1c24",
    skipped="#94a3b8",
    skipped_soft="#272d45",
    disabled_bg="#22254a",
    disabled_text="#5d6493",
    scrollbar="#363c70",
    scrollbar_hover="#5b63a8",
    tooltip_bg="#e8ebff",
    tooltip_text="#1e1b4b",
)

_current: ThemePalette = LIGHT


def current() -> ThemePalette:
    """Paleta em uso (para quem desenha cores no código, como a tabela)."""
    return _current


# ---------------------------------------------------------------- ícones (SVG)
_SVG = {
    "check": '<path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="{c}" stroke-width="3"'
    ' stroke-linecap="round" stroke-linejoin="round"/>',
    "dash": '<path d="M6 12h12" stroke="{c}" stroke-width="3" stroke-linecap="round"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6" fill="none" stroke="{c}" stroke-width="2.4"'
    ' stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6" fill="none" stroke="{c}" stroke-width="2.4"'
    ' stroke-linecap="round" stroke-linejoin="round"/>',
    "arrow-up": '<path d="M12 19V5M5.5 11.5L12 5l6.5 6.5" fill="none" stroke="{c}"'
    ' stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "arrow-down": '<path d="M12 5v14M5.5 12.5L12 19l6.5-6.5" fill="none" stroke="{c}"'
    ' stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="3" fill="none" stroke="{c}"'
    ' stroke-width="2.2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"'
    ' fill="none" stroke="{c}" stroke-width="2.2"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12'
    'M9 7V4h6v3" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round"'
    ' stroke-linejoin="round"/>',
    "clear": '<path d="M4 6h11M4 11h8M4 16h6" stroke="{c}" stroke-width="2.2"'
    ' stroke-linecap="round"/><path d="M15 14l5 5M20 14l-5 5" stroke="{c}" stroke-width="2.2"'
    ' stroke-linecap="round"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" fill="none" stroke="{c}"'
    ' stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1'
    '-2-2z" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>',
    "undo": '<path d="M9 14L4 9l5-5" fill="none" stroke="{c}" stroke-width="2.4"'
    ' stroke-linecap="round" stroke-linejoin="round"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11'
    'H11" fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>',
    "sparkles": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" fill="{c}"/>'
    '<path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" fill="{c}"/>',
    "plus": '<path d="M12 5v14M5 12h14" stroke="{c}" stroke-width="2.6" stroke-linecap="round"/>',
    "ok": '<circle cx="12" cy="12" r="10" fill="{c}"/><path d="M7.5 12.5l3 3 6-6.5"'
    ' fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"'
    ' stroke-linejoin="round"/>',
    "warning": '<path d="M12 3L2 20h20z" fill="{c}" stroke="{c}" stroke-width="2"'
    ' stroke-linejoin="round"/><path d="M12 9.5v4.5" stroke="#fff" stroke-width="2.4"'
    ' stroke-linecap="round"/><circle cx="12" cy="17" r="1.4" fill="#fff"/>',
    "error": '<circle cx="12" cy="12" r="10" fill="{c}"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"'
    ' stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>',
    "skip": '<circle cx="12" cy="12" r="10" fill="{c}"/><path d="M7.5 12h9" stroke="#fff"'
    ' stroke-width="2.6" stroke-linecap="round"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="{c}"/>',
}


def _render_svg(body: str, color: str, size: int) -> QImage:
    from PySide6.QtSvg import QSvgRenderer

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        + body.replace("{c}", color)
        + "</svg>"
    )
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def icon(name: str, color: str | None = None) -> QIcon:
    """Ícone vetorial colorido. ``color`` padrão: cor do texto do tema."""
    color = color or _current.text_muted
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        result.addPixmap(QPixmap.fromImage(_render_svg(_SVG[name], color, size)))
    return result


def _asset_dir(palette: ThemePalette) -> Path:
    """Gera os PNGs usados dentro da QSS (indicadores, setas) num cache temporário."""
    specs = {
        "check": ("check", palette.text_on_accent, 16),
        "dash": ("dash", palette.text_on_accent, 16),
        "chevron-down": ("chevron-down", palette.text_muted, 14),
        "chevron-up": ("chevron-up", palette.text_muted, 14),
        "chevron-down-accent": ("chevron-down", palette.accent, 14),
        "chevron-up-accent": ("chevron-up", palette.accent, 14),
        "chevron-down-disabled": ("chevron-down", palette.disabled_text, 14),
        "chevron-up-disabled": ("chevron-up", palette.disabled_text, 14),
        "chevron-down-light": ("chevron-down", palette.header_text, 14),
    }
    key = hashlib.sha1(repr(sorted(specs.items())).encode()).hexdigest()[:12]
    folder = Path(tempfile.gettempdir()) / f"renamethis-theme-{key}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, (shape, color, size) in specs.items():
        for scale, suffix in ((1, ""), (2, "@2x")):
            path = folder / f"{name}{suffix}.png"
            if not path.exists():
                tmp = path.with_suffix(f".{os.getpid()}.tmp.png")
                _render_svg(_SVG[shape], color, size * scale).save(str(tmp), "PNG")
                os.replace(tmp, path)
    return folder


# ---------------------------------------------------------------- QSS
def build_stylesheet(palette: ThemePalette) -> str:
    template = STYLE_FILE.read_text(encoding="utf-8")
    values = {k: v for k, v in asdict(palette).items() if isinstance(v, str)}
    values["assets"] = _asset_dir(palette).as_posix()

    def sub(match: re.Match[str]) -> str:
        return values[match.group(1)]

    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def _qt_palette(p: ThemePalette) -> QPalette:
    pal = QPalette()
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    colors = {
        role.Window: p.window,
        role.WindowText: p.text,
        role.Base: p.surface,
        role.AlternateBase: p.surface_alt,
        role.Text: p.text,
        role.Button: p.card,
        role.ButtonText: p.text,
        role.BrightText: p.text_on_accent,
        role.Highlight: p.accent,
        role.HighlightedText: p.text_on_accent,
        role.ToolTipBase: p.tooltip_bg,
        role.ToolTipText: p.tooltip_text,
        role.PlaceholderText: p.text_muted,
        role.Link: p.accent2,
        role.Light: p.surface,
        role.Midlight: p.surface_alt,
        role.Mid: p.border,
        role.Dark: p.border,
        role.Shadow: "#000000",
    }
    for r, c in colors.items():
        pal.setColor(r, QColor(c))
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(group.Disabled, r, QColor(p.disabled_text))
    return pal


def system_prefers_dark(app: QGuiApplication | None = None) -> bool:
    forced = os.environ.get("RENAMETHIS_THEME", "").strip().lower()
    if forced in ("dark", "escuro"):
        return True
    if forced in ("light", "claro"):
        return False
    app = app or QGuiApplication.instance()
    hints = app.styleHints() if app else None
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        value = scheme()
        if value == Qt.ColorScheme.Dark:
            return True
        if value == Qt.ColorScheme.Light:
            return False
    # Sem informação do sistema: usa a paleta padrão do estilo
    return QApplication.style().standardPalette().color(QPalette.ColorRole.Window).lightness() < 128


def apply_theme(app: QApplication, dark: bool | None = None) -> ThemePalette:
    """Aplica o tema completo. ``dark=None`` segue o sistema."""
    global _current
    if dark is None:
        dark = system_prefers_dark(app)
    palette = DARK if dark else LIGHT
    _current = palette
    if not app.property("renamethis_fusion"):
        # (com folha de estilo ativa, app.style() vira um "proxy" sem nome)
        app.setStyle("Fusion")
        app.setProperty("renamethis_fusion", True)
    font = QFont(app.font())
    font.setFamilies(FONT_FAMILIES)
    app.setFont(font)
    app.setPalette(_qt_palette(palette))
    app.setStyleSheet(build_stylesheet(palette))
    app.setProperty("renamethis_dark", dark)
    return palette


def follow_system_theme(app: QApplication, on_change=None) -> None:
    """Reaplica o tema quando o sistema troca entre claro e escuro."""
    hints = app.styleHints()
    signal = getattr(hints, "colorSchemeChanged", None)
    if signal is None or os.environ.get("RENAMETHIS_THEME"):
        return

    def changed(*_args) -> None:
        apply_theme(app)
        if on_change:
            on_change()

    signal.connect(changed)
