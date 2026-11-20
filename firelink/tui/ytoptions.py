from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..formats import Offer
from ..youtube import (
    AUDIO_CHOICES,
    AUDIO_CONTAINERS,
    DEFAULTS,
    SUB_CHOICES,
    VIDEO_CHOICES,
    VIDEO_CONTAINERS,
    Choices,
)

LANGS = ("en", "fa", "ar", "tr", "fr", "es", "de", "ru", "hi", "ja")
HINT = "↑↓ field    ←→ change    ⏎ continue    esc cancel"

LABELS = {
    "video": "Video quality",
    "audio": "Audio quality",
    "subs": "Subtitles",
    "sub_lang": "Subtitle language",
    "container": "Format",
}
SHOWN = {
    "best": "best available",
    "none": "audio only",
    "off": "off",
    "soft": "soft — selectable track",
    "hard": "hard — burned into the picture",
}


class YouTubeOptionsScreen(ModalScreen[Choices | None]):
    """Quality, subtitles and container for one YouTube download.

    Appears before the destination picker: what gets downloaded is decided
    first, where it lands second.
    """

    BINDINGS = [
        ("escape", "cancel", "cancel"),
        Binding("up", "previous_field", "up", priority=True),
        Binding("down", "next_field", "down", priority=True),
        Binding("left", "previous_value", "left", priority=True),
        Binding("right", "next_value", "right", priority=True),
        Binding("enter", "accept", "continue", priority=True),
    ]

    FIELDS = ("video", "audio", "subs", "sub_lang", "container")

    def __init__(
        self,
        title: str,
        choices: Choices = DEFAULTS,
        can_burn: bool = True,
        offer: Offer | None = None,
    ):
        super().__init__()
        self.video_title = title
        self.can_burn = can_burn
        self.offer = offer
        self.values = dict(
            video=choices.video,
            audio=choices.audio,
            subs=choices.subs,
            sub_lang=choices.sub_lang,
            container=choices.container,
        )
        self.field = 0
        self.body = ""
        self.head = f"  ▶  {title}"

    @property
    def audio_only(self) -> bool:
        return self.values["video"] == "none"

    @property
    def known(self) -> Offer | None:
        """What the probe found, once it has found anything worth using."""
        if self.offer is None or self.offer.empty:
            return None
        return self.offer

    def options_for(self, field: str) -> tuple[str, ...]:
        known = self.known
        if field == "video":
            if known and known.heights:
                return ("best", *(str(h) for h in known.heights), "none")
            return VIDEO_CHOICES
        if field == "audio":
            if known and known.bitrates:
                return ("best", *(str(b) for b in known.bitrates))
            return AUDIO_CHOICES
        if field == "subs":
            return SUB_CHOICES
        if field == "sub_lang":
            return known.subtitles if known and known.subtitles else LANGS
        return AUDIO_CONTAINERS if self.audio_only else VIDEO_CONTAINERS

    def visible_fields(self) -> tuple[str, ...]:
        """Subtitles are meaningless without a picture, and the language only
        matters once subtitles are on.

        Choosing audio-only keeps the video row, so the choice can be undone.
        A site with no video at all loses the row: there is nothing to go
        back to.
        """
        known = self.known
        no_video = known is not None and known.audio_only
        fields = [] if no_video else ["video"]
        fields.append("audio")
        silent = known is not None and not known.subtitles
        if not no_video and not self.audio_only and not silent:
            fields.append("subs")
            if self.values["subs"] != "off":
                fields.append("sub_lang")
        fields.append("container")
        return tuple(fields)

    def apply_offer(self, offer: Offer) -> None:
        """Take up what the probe found, without overruling a choice made
        while it was still running.

        Settling values on a screen nobody will see is harmless; drawing on
        one is not, which _repaint handles for itself.
        """
        if offer.empty:
            return
        self.offer = offer
        if offer.audio_only:
            self.values["video"] = "none"
        for field in self.FIELDS:
            self.values[field] = self._nearest(field, self.values[field])
        self.field = min(self.field, len(self.visible_fields()) - 1)
        self._repaint()

    def _nearest(self, field: str, current: str) -> str:
        options = self.options_for(field)
        if current in options:
            return current
        numeric = [o for o in options if o.isdigit()]
        if current.isdigit() and numeric:
            return min(numeric, key=lambda o: abs(int(o) - int(current)))
        return options[0]

    def compose(self) -> ComposeResult:
        with Vertical(id="yt-box"):
            yield Static(self.head, id="yt-head")
            yield Static("", id="yt-list")
            yield Static(HINT, id="yt-hint")

    def on_mount(self) -> None:
        self._repaint()

    def _repaint(self) -> None:
        rows = []
        for index, field in enumerate(self.visible_fields()):
            value = self.values[field]
            shown = SHOWN.get(value, value)
            if field == "video" and value not in ("best", "none"):
                shown = f"{value}p"
            if field == "audio" and value != "best":
                shown = f"{value} kbps"
            marker = "▌" if index == self.field else " "
            rows.append(f"{marker} {LABELS[field]:<20} ‹ {shown} ›")
        if self.values["subs"] == "hard" and not self.can_burn:
            rows.append("")
            # Naming the wrong remedy is worse than naming none: homebrew-core
            # has no libass, so `brew reinstall ffmpeg` rebuilds the same thing.
            rows.append("  ⚠  this ffmpeg cannot burn in subtitles (built without")
            rows.append("     libass) — soft subtitles will still work")
            rows.append("     for hard subs: brew install homebrew-ffmpeg/ffmpeg/ffmpeg")
        self.body = "\n".join(rows)
        # The probe can land after the screen was dismissed. Textual removes
        # the composed children then but leaves is_mounted true, so the only
        # reliable question is whether the target is still there.
        listing = self.query("#yt-list")
        if listing:
            listing.first(Static).update(self.body)

    def _current_field(self) -> str:
        fields = self.visible_fields()
        return fields[min(self.field, len(fields) - 1)]

    def _step(self, delta: int) -> None:
        field = self._current_field()
        options = self.options_for(field)
        position = options.index(self.values[field]) if self.values[field] in options else 0
        self.values[field] = options[(position + delta) % len(options)]
        if field == "video":
            self._settle_container()
        self.field = min(self.field, len(self.visible_fields()) - 1)
        self._repaint()

    def _settle_container(self) -> None:
        """Switching to audio-only leaves an impossible container behind."""
        allowed = self.options_for("container")
        if self.values["container"] not in allowed:
            self.values["container"] = allowed[0]

    def action_next_field(self) -> None:
        self.field = (self.field + 1) % len(self.visible_fields())
        self._repaint()

    def action_previous_field(self) -> None:
        self.field = (self.field - 1) % len(self.visible_fields())
        self._repaint()

    def action_next_value(self) -> None:
        self._step(1)

    def action_previous_value(self) -> None:
        self._step(-1)

    def action_accept(self) -> None:
        self.dismiss(Choices(**self.values))

    def action_cancel(self) -> None:
        self.dismiss(None)
